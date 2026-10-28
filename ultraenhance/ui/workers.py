from pathlib import Path
import threading
import tempfile

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from ..backends import BackendManager, hardware_info
from ..jobs import execute_job
from ..media import analyze, load_image, probe
from ..process import Cancelled, run_process


def qt_image(image):
    image = image.convert("RGBA")
    return QImage(image.tobytes(), image.width, image.height, image.width * 4, QImage.Format_RGBA8888).copy()


class ScanWorker(QThread):
    ready = Signal(object, object)
    failed = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def run(self):
        try:
            self.ready.emit(BackendManager(self.settings).scan(), hardware_info())
        except Exception as exc:
            self.failed.emit(str(exc))


class ImportWorker(QThread):
    item = Signal(object, object, object)
    failed = Signal(str)

    def __init__(self, paths, backends):
        super().__init__()
        self.paths = paths
        self.backends = backends
        self.cancel = threading.Event()

    def run(self):
        for path in self.paths:
            if self.cancel.is_set():
                break
            try:
                info = probe(path, self.backends, self.cancel)
                if info.kind == "image":
                    image = load_image(path)
                else:
                    ffmpeg = self.backends.require("ffmpeg").path
                    with tempfile.TemporaryDirectory(prefix="ultraenhance-thumb-") as directory:
                        thumbnail = Path(directory) / "thumb.png"
                        run_process([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-i", path,
                                     "-frames:v", "1", "-vf", "scale=1280:1280:force_original_aspect_ratio=decrease", str(thumbnail)], self.cancel, timeout=30)
                        image = load_image(thumbnail)
                stats = analyze(image)
                image.thumbnail((512, 512))
                self.item.emit(info, qt_image(image), stats)
            except Cancelled:
                break
            except Exception as exc:
                self.failed.emit(f"{Path(path).name}: {exc}")


class PreviewWorker(QThread):
    ready = Signal(str, object)
    failed = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            self.ready.emit(self.path, qt_image(load_image(self.path)))
        except Exception as exc:
            self.failed.emit(str(exc))


class JobWorker(QThread):
    progress = Signal(str, object, object)
    succeeded = Signal(str, object, object, object)
    failed = Signal(str, bool)

    def __init__(self, job, backends, preview_directory):
        super().__init__()
        self.job = job
        self.backends = backends
        self.preview_directory = preview_directory
        self.cancel = threading.Event()

    def run(self):
        try:
            output, size = execute_job(self.job, self.backends, self.cancel, self.progress.emit, self.preview_directory)
            image = QImage()
            original_region = QImage()
            if Path(output).suffix.lower() in (".png", ".jpg", ".webp"):
                image = qt_image(load_image(output))
                if self.job.preview and self.job.region:
                    original_region = qt_image(load_image(self.job.source).crop(self.job.region))
            self.succeeded.emit(output, size, image, original_region)
        except Cancelled as exc:
            self.failed.emit(str(exc), True)
        except Exception as exc:
            self.failed.emit(str(exc), False)
