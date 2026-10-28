"""Real NCNN inference followed by explicitly conventional image adjustments."""
from dataclasses import dataclass
import math
from pathlib import Path
import re
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from .config import PRESETS
from .media import load_image, target_size
from .process import check_cancel, ProcessingError, run_process


@dataclass
class JobOptions:
    engine: str = "AI"
    model: str = "realesrgan-x4plus"
    preset: str = "Balanced"
    target: str = "2×"
    width: int = 3840
    height: int = 2160
    preserve: bool = True
    denoise: int = 0
    sharpness: float = 0
    contrast: float = 1
    brightness: float = 0
    saturation: float = 1
    color_correct: bool = False
    artifact_reduction: bool = False
    image_format: str = "PNG"
    quality: int = 95
    video_format: str = "MP4"
    codec: str = "libx264"
    crf: int = 18
    interpolation: int = 0
    stabilize: bool = False
    tile: int = 128
    gpu_id: int = -1
    output_dir: str = ""

    def validate(self):
        if self.engine not in ("AI", "CPU") or self.preset not in PRESETS:
            raise ProcessingError("Unknown engine or processing preset.")
        if not 0 <= self.denoise <= 20 or not 0 <= self.sharpness <= 2:
            raise ProcessingError("Noise reduction / sharpness is out of range.")
        if not -0.5 <= self.brightness <= 0.5 or not 0.5 <= self.contrast <= 2 or not 0 <= self.saturation <= 2:
            raise ProcessingError("Color adjustment is out of range.")
        if self.tile != 0 and not 32 <= self.tile <= 2048:
            raise ProcessingError("Tile size must be 0 or 32–2048.")
        if self.gpu_id < -1 or self.gpu_id > 31:
            raise ProcessingError("Invalid GPU device ID.")
        if self.image_format not in ("PNG", "JPG", "WEBP") or not 1 <= self.quality <= 100:
            raise ProcessingError("Invalid image export settings.")
        if self.video_format not in ("MP4", "MKV") or self.codec not in ("libx264", "libx265") or not 0 <= self.crf <= 40:
            raise ProcessingError("Invalid video export settings.")
        if self.interpolation not in (0, 30, 60):
            raise ProcessingError("Interpolation target must be Original, 30 or 60 FPS.")


def ncnn_command(engine, source, destination, options, size, source_size):
    name = options.model
    # Only animevideov3 has dedicated 2x / 3x weights. x4 models always infer at 4x.
    factor = min(4, max(2, math.ceil(max(size[0] / source_size[0], size[1] / source_size[1])))) if name == "realesr-animevideov3" else 4
    if name == "realesr-animevideov3":
        model_file = f"{name}-x{factor}"
    else:
        model_file = name
    if model_file not in engine.models:
        raise ProcessingError(f"Model {model_file} is missing from {engine.models_dir}. Install its matching .param and .bin files.")
    if max(size[0] / source_size[0], size[1] / source_size[1]) > factor + 0.01:
        raise ProcessingError(f"This target needs more than {factor}×. Choose a smaller output; additional non-AI enlargement is not applied silently.")
    args = [engine.path, "-i", str(source), "-o", str(destination), "-m", engine.models_dir,
            "-n", name, "-s", str(factor), "-t", str(options.tile),
            "-j", PRESETS[options.preset]["threads"], "-f", "png"]
    if options.gpu_id >= 0:
        args += ["-g", str(options.gpu_id)]
    if PRESETS[options.preset]["tta"]:
        if "-x" not in engine.help:
            raise ProcessingError("This Real-ESRGAN build does not support test-time augmentation (-x).")
        args += ["-x"]
    return args, factor


def conventional_adjustments(image, options):
    alpha = image.getchannel("A") if image.mode == "RGBA" else None
    rgb = image.convert("RGB")
    if options.denoise or options.artifact_reduction:
        array = np.array(rgb)
        if options.artifact_reduction:
            array = cv2.bilateralFilter(array, 5, 20, 20)
        if options.denoise:
            array = cv2.fastNlMeansDenoisingColored(array, None, options.denoise, options.denoise, 7, 21)
        rgb = Image.fromarray(array)
    if options.color_correct:
        array = np.asarray(rgb, dtype=np.float32)
        means = array.mean(axis=(0, 1))
        gains = np.clip(means.mean() / np.maximum(means, 1), 0.8, 1.2)
        rgb = Image.fromarray(np.clip(array * gains, 0, 255).astype(np.uint8))
    if options.brightness:
        rgb = ImageEnhance.Brightness(rgb).enhance(1 + options.brightness)
    if options.contrast != 1:
        rgb = ImageEnhance.Contrast(rgb).enhance(options.contrast)
    if options.saturation != 1:
        rgb = ImageEnhance.Color(rgb).enhance(options.saturation)
    if options.sharpness:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.5, percent=round(options.sharpness * 100), threshold=3))
    if alpha is not None:
        rgb.putalpha(alpha)
    return rgb


def enhance_image(source, destination, options, backends, cancel, progress, region=None):
    options.validate()
    check_cancel(cancel)
    progress("Reading image", None, None)
    image = load_image(source)
    full_size = image.size
    desired = target_size(*full_size, options.target, (options.width, options.height), options.preserve)
    if region:
        image = image.crop(region)
        desired = (max(1, round(image.width * desired[0] / full_size[0])), max(1, round(image.height * desired[1] / full_size[1])))
    # Denoise before scaling: bounded memory and fewer redundant filter operations.
    progress("Applying conventional filters", None, None)
    image = conventional_adjustments(image, options)
    check_cancel(cancel)
    alpha = image.getchannel("A") if image.mode == "RGBA" else None
    if options.engine == "AI":
        engine = backends.require("realesrgan")
        parent = backends.settings.temp_dir or None
        if parent:
            Path(parent).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ultraenhance-image-", dir=parent) as directory:
            input_file, output_file = Path(directory) / "input.png", Path(directory) / "inferred.png"
            image.convert("RGB").save(input_file)
            args, factor = ncnn_command(engine, input_file, output_file, options, desired, image.size)
            progress(f"Real-ESRGAN inference · {factor}×", None, None)

            def engine_progress(line):
                match = re.search(r"(\d+(?:\.\d+)?)%", line)
                if match:
                    progress(f"Real-ESRGAN inference · {factor}×", min(100, float(match[1])), None)

            run_process(args, cancel, engine_progress, cwd=str(Path(engine.path).parent))
            check_cancel(cancel)
            if not output_file.is_file():
                raise ProcessingError("Real-ESRGAN returned without producing an image.")
            result = load_image(output_file)
            if result.size != (image.width * factor, image.height * factor):
                raise ProcessingError(f"Unexpected AI output dimensions: {result.size}. No export was committed.")
    else:
        progress("CPU Lanczos scaling · non-AI", None, None)
        result = image
    check_cancel(cancel)
    if result.size != desired:
        result = result.resize(desired, Image.Resampling.LANCZOS)
    if alpha is not None:
        result.putalpha(alpha.resize(desired, Image.Resampling.LANCZOS))
    progress("Encoding image", None, None)
    if options.image_format == "JPG":
        if result.mode == "RGBA":
            background = Image.new("RGB", result.size, "white")
            background.paste(result, mask=result.getchannel("A"))
            result = background
        result.save(destination, format="JPEG", quality=options.quality, subsampling=0)
    elif options.image_format == "WEBP":
        result.save(destination, format="WEBP", quality=options.quality, method=4)
    else:
        result.save(destination, format="PNG", compress_level=6)
    check_cancel(cancel)
    with Image.open(destination) as exported:
        exported.verify()
    with Image.open(destination) as exported:
        if exported.size != desired:
            raise ProcessingError("Export dimensions failed validation.")
    return desired
