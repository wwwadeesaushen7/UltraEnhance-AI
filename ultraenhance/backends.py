"""Find external engines; inspect their advertised CLI before each job."""
from dataclasses import dataclass, field
import ctypes
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys

import psutil

from .config import Settings
from .process import capture, ProcessingError


SOURCES = {
    "realesrgan": "https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases",
    "video2x": "https://github.com/k4yt3x/video2x/releases",
    "ffmpeg": "https://ffmpeg.org/download.html",
    "ffprobe": "https://ffmpeg.org/download.html",
}
NAMES = {"realesrgan": "realesrgan-ncnn-vulkan", "video2x": "video2x", "ffmpeg": "ffmpeg", "ffprobe": "ffprobe"}


@dataclass
class Engine:
    name: str
    path: str = ""
    help: str = ""
    available: bool = False
    message: str = "Not installed"
    models: list[str] = field(default_factory=list)
    models_dir: str = ""


class BackendManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engines = {}

    def locate(self, key):
        override = getattr(self.settings, key)
        if override:
            path = Path(override).expanduser()
            return str(path.resolve()) if path.is_file() else ""
        filename = NAMES[key] + (".exe" if os.name == "nt" else "")
        roots = [Path(sys.executable).parent, Path(__file__).resolve().parent.parent]
        if getattr(sys, "frozen", False):
            roots.append(Path(sys._MEIPASS))
        for root in roots:
            for relative in (Path("engines") / key / filename, Path("engines") / filename):
                candidate = root / relative
                if candidate.is_file():
                    return str(candidate.resolve())
        return shutil.which(filename) or ""

    def scan(self):
        for key in NAMES:
            path = self.locate(key)
            engine = Engine(key, path)
            if path:
                args = [path, "-h"] if key == "realesrgan" else [path, "--help"]
                if key in ("ffmpeg", "ffprobe"):
                    args = [path, "-version"]
                engine.help = capture(args)
                required = {"realesrgan": ["-i", "-o", "-s", "-t", "-m", "-n", "-g", "-j", "-f"],
                            "video2x": ["--input", "--output", "--processor", "--scaling-factor", "--codec"],
                            "ffmpeg": ["ffmpeg version"], "ffprobe": ["ffprobe version"]}[key]
                engine.available = all(word in engine.help for word in required)
                engine.message = "Ready" if engine.available else "Unrecognized CLI or unable to run. Check the executable and its dependencies."
                if key == "realesrgan":
                    directory = Path(self.settings.models_dir) if self.settings.models_dir else Path(path).parent / "models"
                    engine.models_dir = str(directory)
                    engine.models = sorted({p.stem for p in directory.glob("*.param") if p.with_suffix(".bin").is_file()})
                    if not engine.models:
                        engine.message = "CLI found; matching .param/.bin models are missing."
            elif getattr(self.settings, key):
                engine.message = "Configured executable does not exist."
            self.engines[key] = engine
        return self

    def require(self, key, flags=()):
        engine = self.engines.get(key)
        if engine is None or not engine.available:
            raise ProcessingError(f"{NAMES[key]} is unavailable. {engine.message if engine else ''}\nInstall from {SOURCES[key]} and select its executable in Settings.")
        for flag in flags:
            if flag not in engine.help:
                raise ProcessingError(f"This {NAMES[key]} build does not advertise {flag}. Use a compatible build from {SOURCES[key]}.")
        return engine


def hardware_info():
    """Best-effort hardware data; a Vulkan loader alone is never labeled a working GPU."""
    data = {"cpu": platform.processor() or platform.machine(),
            "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
            "gpus": [], "vulkan": "Not detected; engine execution remains the final compatibility check."}
    if os.name == "nt":
        script = "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"
        text = capture(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])
        try:
            devices = json.loads(text)
            for device in devices if isinstance(devices, list) else [devices]:
                memory = device.get("AdapterRAM")
                data["gpus"].append(f"{device['Name']} (reported VRAM: {round(memory / 1024**3, 1)} GB)" if memory else device["Name"])
        except (ValueError, TypeError, KeyError):
            pass
    smi = shutil.which("nvidia-smi")
    if smi:
        report = capture([smi, "--query-gpu=name,memory.total", "--format=csv,noheader"])
        if "exited with code" not in report:
            data["gpus"].extend(report.splitlines())
    info = shutil.which("vulkaninfo")
    if info:
        report = capture([info, "--summary"])
        devices = re.findall(r"deviceName\s*=\s*(.+)", report)
        if devices:
            data["gpus"].extend(devices)
            data["vulkan"] = "Devices enumerated by vulkaninfo; compatibility depends on the model and engine."
    else:
        try:
            ctypes.CDLL("vulkan-1.dll" if os.name == "nt" else "libvulkan.so.1")
            data["vulkan"] = "Vulkan loader found; GPU support has not been verified."
        except OSError:
            pass
    data["gpus"] = list(dict.fromkeys(data["gpus"]))
    return data
