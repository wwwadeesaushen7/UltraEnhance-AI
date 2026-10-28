"""Media metadata and bounded image-quality analysis."""
from dataclasses import dataclass
from fractions import Fraction
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .process import run_process, ProcessingError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


@dataclass
class MediaInfo:
    path: str
    kind: str
    width: int
    height: int
    duration: float = 0
    fps: float = 0
    frames: int = 0
    audio: bool = False
    rotation: int = 0
    variable_fps: bool = False
    exact_frames: bool = False
    has_b_frames: int = 0
    sample_aspect_ratio: float = 1.0


def load_image(path):
    with Image.open(path) as image:
        if image.width * image.height > 80_000_000 or max(image.size) > 16384:
            raise ProcessingError("Source image exceeds the 80 megapixel / 16,384 pixel safety limit.")
        image.load()
        return ImageOps.exif_transpose(image).convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")


def rational(value, default=0):
    try:
        result = float(Fraction(str(value)))
        return result if math.isfinite(result) else default
    except (ValueError, ZeroDivisionError):
        return default


def probe(path, backends, cancel=None):
    path = Path(path).resolve()
    if not path.is_file():
        raise ProcessingError(f"File not found: {path}")
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        image = load_image(path)
        return MediaInfo(str(path), "image", *image.size)
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ProcessingError(f"Unsupported file type: {path.suffix}")
    engine = backends.require("ffprobe")
    output = run_process([engine.path, "-v", "error", "-show_streams", "-show_format", "-of", "json=compact=1", str(path)], cancel, timeout=30)
    try:
        data = json.loads(output)
        stream = next(s for s in data["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic"))
        width, height = int(stream["width"]), int(stream["height"])
        sar = rational(stream.get("sample_aspect_ratio", "1:1").replace(":", "/"), 1)
        width = round(width * (sar or 1))
        rotation = int(stream.get("tags", {}).get("rotate", 0))
        for side in stream.get("side_data_list", []):
            rotation = int(side.get("rotation", rotation))
        if abs(rotation) % 180 == 90:
            width, height = height, width
        duration = rational(stream.get("duration", data.get("format", {}).get("duration", 0)))
        fps = rational(stream.get("avg_frame_rate")) or rational(stream.get("r_frame_rate"))
        nominal = rational(stream.get("r_frame_rate"))
        frames = int(stream.get("nb_frames", 0) or 0) if str(stream.get("nb_frames", "0")).isdigit() else 0
        frames = frames or round(duration * fps)
        return MediaInfo(str(path), "video", width, height, duration, fps, frames,
                         any(s.get("codec_type") == "audio" for s in data["streams"]), rotation,
                         bool(nominal and fps and abs(nominal - fps) > 0.05),
                         str(stream.get("nb_frames", "0")).isdigit() and int(stream.get("nb_frames", 0) or 0) > 0,
                         int(stream.get("has_b_frames", 0)), sar or 1)
    except (ValueError, KeyError, StopIteration, TypeError) as exc:
        raise ProcessingError(f"Cannot read a playable video stream in {path.name}: {exc}") from exc


def analyze(image):
    sample = image.convert("RGB")
    sample.thumbnail((768, 768))
    rgb = np.array(sample)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    brightness = float(gray.mean()) / 255
    contrast = float(gray.std()) / 255
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    residual = gray.astype(np.float32) - cv2.medianBlur(gray, 3).astype(np.float32)
    noise = float(np.median(np.abs(residual))) * 1.4826
    return {"brightness": brightness, "contrast": contrast, "sharpness": sharpness, "noise": noise,
            "recommended": {"brightness": round(max(-0.2, min(0.2, 0.45 - brightness)), 2),
                            "contrast": 1.12 if contrast < 0.15 else 1.0,
                            "denoise": min(10, round(noise)),
                            "sharpness": 0.3 if sharpness < 100 else 0.0}}


def target_size(width, height, target="2×", custom=(3840, 2160), preserve=True, even=False):
    if target in ("2×", "3×", "4×"):
        factor = int(target[0]); size = (width * factor, height * factor)
    else:
        sizes = {"1080p": (1920, 1080), "1440p": (2560, 1440), "4K": (3840, 2160)}
        box = custom if target == "Custom" else sizes.get(target)
        if box is None:
            raise ProcessingError("Unknown target resolution.")
        if target != "Custom" and height > width:
            box = box[::-1]
        if min(box) < 2:
            raise ProcessingError("Output dimensions must be at least 2 pixels.")
        ratio = min(box[0] / width, box[1] / height)
        size = (max(1, round(width * ratio)), max(1, round(height * ratio))) if preserve else box
    if even:
        size = tuple(max(2, round(d / 2) * 2) for d in size)
    if max(size) > 16384 or size[0] * size[1] > 80_000_000:
        raise ProcessingError("Output exceeds this release's safety limit: 16,384 pixels per side / 80 megapixels.")
    return size
