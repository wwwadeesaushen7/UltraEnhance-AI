"""Bounded video pipeline: Video2X streaming inference and FFmpeg finalization."""
import math
from pathlib import Path
import re
import tempfile

from .config import PRESETS
from .media import probe, target_size
from .process import check_cancel, ProcessingError, run_process, capture


def video2x_cwd(engine):
    binary_dir = Path(engine.path).resolve().parent
    for directory in (binary_dir, binary_dir.parent / "share" / "video2x", binary_dir.parent):
        if (directory / "models").is_dir():
            return str(directory)
    # Some system installations resolve compiled-in resource paths themselves.
    return str(binary_dir)


def video2x_command(engine, source, output, options, size, source_size, processor="realesrgan", multiplier=0):
    no_copy = ["--no-copy-streams"] if "--no-copy-streams" in engine.help else ["--no-copy-audio-streams", "--no-copy-subtitle-streams"]
    required = ["--extra-encoder-option", "--pix-fmt"] + no_copy
    if processor == "realesrgan":
        required += ["--realesrgan-model", "--scaling-factor"]
    else:
        required += ["--rife-model", "--frame-rate-mul"]
    if options.gpu_id >= 0:
        required += ["--device"]
    for flag in required:
        if flag not in engine.help:
            raise ProcessingError(f"This Video2X build does not support {flag}; Video2X 6.x CLI is required.")
    args = [engine.path, "--input", str(source), "--output", str(output), "--processor", processor,
            "--codec", "libx264", "--pix-fmt", "yuv420p", *no_copy,
            "--extra-encoder-option", "crf=0", "preset=veryfast"]
    if options.gpu_id >= 0:
        args += ["--device", str(options.gpu_id)]
    if processor == "rife":
        args += ["--frame-rate-mul", str(multiplier), "--rife-model", "rife-v4.6"]
        return args, 1
    models = {"realesrgan-x4plus": "realesrgan-plus", "realesrgan-x4plus-anime": "realesrgan-plus-anime",
              "realesr-animevideov3": "realesr-animevideov3"}
    model = models.get(options.model)
    if not model:
        raise ProcessingError("This model has no verified Video2X equivalent.")
    if model not in engine.help:
        raise ProcessingError(f"Video2X does not advertise model {model}.")
    factor = max(2, min(4, math.ceil(max(size[0] / source_size[0], size[1] / source_size[1])))) if model == "realesr-animevideov3" else 4
    if max(size[0] / source_size[0], size[1] / source_size[1]) > factor + .01:
        raise ProcessingError(f"Target exceeds this model's {factor}× inference scale.")
    args += ["--scaling-factor", str(factor), "--realesrgan-model", model]
    return args, factor


def traditional_filters(options, size):
    filters = [f"scale={size[0]}:{size[1]}:flags=lanczos", "setsar=1"]
    if options.stabilize:
        filters.append("deshake")
    if options.denoise or options.artifact_reduction:
        strength = max(options.denoise / 3, 1 if options.artifact_reduction else 0)
        filters.append(f"hqdn3d={strength:.3f}:{strength:.3f}:{strength * 1.5:.3f}:{strength * 1.5:.3f}")
    if options.brightness or options.contrast != 1 or options.saturation != 1:
        filters.append(f"eq=brightness={options.brightness:.3f}:contrast={options.contrast:.3f}:saturation={options.saturation:.3f}")
    if options.sharpness:
        filters.append(f"unsharp=5:5:{options.sharpness:.3f}:5:5:0")
    return ",".join(filters)


def ffmpeg_callback(stage, duration, progress):
    frames = 0
    def update(line):
        nonlocal frames
        if line.startswith("frame="):
            try:
                frames = int(line.partition("=")[2])
            except ValueError:
                pass
        elif line.startswith("out_time_us="):
            try:
                seconds = max(0, int(line.partition("=")[2])) / 1_000_000
                progress(stage, min(100, seconds / duration * 100) if duration else None, frames)
            except ValueError:
                pass
    return update


def v2x_callback(stage, progress):
    def update(line):
        match = re.search(r"frame=(\d+)/(\d+)\s*\(([\d.]+)%\)", line)
        if match:
            progress(stage, min(100, float(match[3])) if int(match[2]) else None, int(match[1]))
    return update


def enhance_video(source, destination, options, backends, cancel, progress, preview=False):
    options.validate()
    ffmpeg = backends.require("ffmpeg").path
    info = probe(source, backends, cancel)
    size = target_size(info.width, info.height, options.target, (options.width, options.height), options.preserve, even=True)
    if options.color_correct:
        raise ProcessingError("Automatic per-channel white balance is available for images only.")
    codec_help = capture([ffmpeg, "-hide_banner", "-h", f"encoder={options.codec}"])
    if f"Encoder {options.codec}" not in codec_help:
        raise ProcessingError(f"This FFmpeg build does not provide {options.codec}.")
    if options.stabilize and "Filter deshake" not in capture([ffmpeg, "-hide_banner", "-h", "filter=deshake"]):
        raise ProcessingError("This FFmpeg build does not include the deshake stabilization filter.")
    multiplier = 0
    if options.interpolation:
        ratio = options.interpolation / info.fps if info.fps else 0
        multiplier = round(ratio)
        if info.variable_fps or multiplier not in (2, 3, 4) or abs(ratio - multiplier) > 0.0001:
            raise ProcessingError(f"RIFE target {options.interpolation} FPS requires a constant source FPS with an exact 2×, 3× or 4× ratio. Source is {info.fps:.4f} FPS. Select Original FPS for this file.")
    if options.engine == "AI" and info.variable_fps:
        raise ProcessingError("Video2X uses a fixed output frame rate. This file appears variable-rate; normalize it to constant FPS before AI processing, or choose CPU non-AI mode.")
    duration = min(5., info.duration) if preview and info.duration else info.duration
    temp_parent = backends.settings.temp_dir or None
    if temp_parent:
        Path(temp_parent).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ultraenhance-video-", dir=temp_parent) as directory:
        directory = Path(directory)
        audio_source = Path(source)
        work_source = Path(source)
        if preview:
            progress("Preparing five-second preview", None, None)
            audio_source = work_source = directory / "preview-source.mkv"
            run_process([ffmpeg, "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", str(source), "-t", "5",
                         "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "0",
                         "-c:a", "copy", "-fps_mode", "passthrough", str(work_source)], cancel)
        # Video2X 6.4.0 does not drain reordered decoder frames at EOF. Normalize
        # B-frame inputs to a lossless zero-delay stream before either AI processor.
        work_info = probe(work_source, backends, cancel)
        if (options.engine == "AI" or multiplier) and (work_info.rotation or work_info.has_b_frames or work_info.sample_aspect_ratio != 1):
            normalized = directory / "normalized.mkv"
            progress("Preparing lossless zero-delay video for Video2X", None, None)
            run_process([ffmpeg, "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", str(work_source), "-map", "0:v:0", "-an",
                         "-vf", f"scale={info.width // 2 * 2}:{info.height // 2 * 2},setsar=1", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-bf", "0", "-crf", "0", str(normalized)], cancel)
            work_source = normalized
        check_cancel(cancel)
        if options.engine == "AI":
            engine = backends.require("video2x")
            upscaled = directory / "upscaled.mkv"
            args, factor = video2x_command(engine, work_source, upscaled, options, size, (info.width, info.height))
            progress(f"Video2X Real-ESRGAN · {factor}×", None, None)
            run_process(args, cancel, v2x_callback("Video2X Real-ESRGAN", progress), cwd=video2x_cwd(engine))
            work_source = upscaled
        if multiplier:
            engine = backends.require("video2x")
            interpolated = directory / "interpolated.mkv"
            args, _ = video2x_command(engine, work_source, interpolated, options, size, (info.width, info.height), "rife", multiplier)
            progress(f"RIFE interpolation · {options.interpolation} FPS", None, None)
            run_process(args, cancel, v2x_callback("RIFE interpolation", progress), cwd=video2x_cwd(engine))
            work_source = interpolated
        stage = "Encoding enhanced video" if options.engine == "AI" else "CPU Lanczos + FFmpeg filters · non-AI"
        progress(stage, None, None)
        args = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", str(work_source), "-i", str(audio_source),
                "-map", "0:v:0", "-map", "1:a?", "-map_metadata", "1", "-vf", traditional_filters(options, size),
                "-c:v", options.codec, "-preset", PRESETS[options.preset]["encoder"], "-crf", str(options.crf),
                "-pix_fmt", "yuv420p", "-c:a", "copy", "-fps_mode", "passthrough", "-metadata:s:v:0", "rotate=0"]
        if options.video_format == "MP4":
            args += ["-movflags", "+faststart"]
        args += ["-progress", "pipe:1", "-nostats", str(destination)]
        callback = ffmpeg_callback(stage, duration, progress)
        try:
            run_process(args, cancel, callback)
        except ProcessingError as exc:
            if not any(token in str(exc) for token in ("not currently supported in container", "Could not find tag", "codec not supported")):
                raise
            progress("Audio requires AAC for this container", None, None)
            i = args.index("-c:a")
            args[i + 1] = "aac"
            args[i + 2:i + 2] = ["-b:a", "192k"]
            run_process(args, cancel, callback)
        check_cancel(cancel)
        progress("Validating complete video", None, None)
        result = probe(destination, backends, cancel)
        if (result.width, result.height) != size:
            raise ProcessingError(f"Unexpected video dimensions {result.width}×{result.height}; expected {size[0]}×{size[1]}.")
        if info.audio and not result.audio:
            raise ProcessingError("Source audio is missing from the result.")
        if duration and abs(result.duration - duration) > max(0.5, duration * 0.01):
            raise ProcessingError(f"Output duration {result.duration:.2f}s does not match {duration:.2f}s.")
        expected_fps = options.interpolation or info.fps
        if expected_fps and not info.variable_fps and abs(result.fps - expected_fps) > 0.05:
            raise ProcessingError(f"Output FPS {result.fps:g} does not match expected {expected_fps:g}.")
        decoded_frames = []
        validation_progress = ffmpeg_callback("Validating complete video", duration, progress)
        def validation_line(line):
            validation_progress(line)
            if line.startswith("frame="):
                try:
                    decoded_frames.append(int(line.partition("=")[2]))
                except ValueError:
                    pass
        run_process([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-xerror", "-i", str(destination),
                     "-map", "0:v:0", "-map", "0:a?", "-progress", "pipe:1", "-f", "null", "-"],
                    cancel, validation_line)
        if info.exact_frames and not info.variable_fps:
            expected_frames = round(duration * info.fps) if preview else info.frames
            if multiplier:
                expected_frames *= multiplier
            if not decoded_frames or decoded_frames[-1] != expected_frames:
                raise ProcessingError(f"Frame-count validation failed: expected {expected_frames}, decoded {decoded_frames[-1] if decoded_frames else 0}. No partial export was committed.")
    return size
