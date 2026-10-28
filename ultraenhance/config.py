"""Validated, atomic user configuration; never stores files beside the executable."""
from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import tempfile


def config_dir() -> Path:
    root = os.environ.get("ULTRAENHANCE_CONFIG_DIR")
    if root:
        return Path(root)
    return Path(os.environ.get("APPDATA", os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))) / "UltraEnhanceAI"


@dataclass
class Settings:
    output_dir: str = str(Path.home() / "Pictures" / "UltraEnhance")
    temp_dir: str = ""
    realesrgan: str = ""
    video2x: str = ""
    ffmpeg: str = ""
    ffprobe: str = ""
    models_dir: str = ""
    gpu_id: int = -1  # -1 means automatic; explicit CPU is selected in JobOptions.
    tile_size: int = 128
    preset: str = "Balanced"
    image_format: str = "PNG"
    video_format: str = "MP4"
    codec: str = "libx264"
    crf: int = 18
    max_jobs: int = 1

    def validate(self):
        if self.tile_size != 0 and not 32 <= self.tile_size <= 2048:
            raise ValueError("Tile size must be 0 (automatic) or 32–2048.")
        if self.gpu_id < -1 or self.gpu_id > 31:
            raise ValueError("GPU ID must be automatic (-1) or 0–31.")
        if self.preset not in PRESETS:
            raise ValueError("Unknown processing preset.")
        if self.image_format not in ("PNG", "JPG", "WEBP"):
            raise ValueError("Unknown image format.")
        if self.video_format not in ("MP4", "MKV"):
            raise ValueError("Unknown video container.")
        if self.codec not in ("libx264", "libx265") or not 0 <= self.crf <= 40:
            raise ValueError("Unsupported codec or CRF.")
        if self.max_jobs != 1:
            raise ValueError("This release processes one demanding job at a time for memory safety.")


# These configure real resource/encoding parameters. No preset changes AI into CPU silently.
PRESETS = {
    "Fast": {"tile": 64, "tta": False, "threads": "1:1:1", "encoder": "veryfast"},
    "Balanced": {"tile": 128, "tta": False, "threads": "1:1:1", "encoder": "medium"},
    "Maximum Quality": {"tile": 256, "tta": True, "threads": "1:1:1", "encoder": "slow"},
}


def load_settings() -> Settings:
    path = config_dir() / "settings.json"
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        allowed = {f.name for f in fields(Settings)}
        settings = Settings(**{k: v for k, v in data.items() if k in allowed})
        settings.validate()
        return settings
    except (ValueError, TypeError, OSError) as exc:
        raise ValueError(f"Cannot read {path}. Fix or rename this settings file.\n{exc}") from exc


def save_settings(settings: Settings):
    settings.validate()
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="settings-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(asdict(settings), stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, directory / "settings.json")
    finally:
        Path(name).unlink(missing_ok=True)
