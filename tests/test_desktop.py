import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtWidgets import QApplication

from ultraenhance.config import Settings
from ultraenhance.ui.window import MainWindow


def wait_until(app, predicate, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            app.processEvents()
            return
        time.sleep(.01)
    raise AssertionError("Timed out waiting for the desktop workflow")


def test_native_import_auto_enhance_and_queued_export(tmp_path, monkeypatch):
    monkeypatch.setenv("ULTRAENHANCE_CONFIG_DIR", str(tmp_path / "config"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Settings(output_dir=str(tmp_path / "exports")))
    window.show()
    try:
        wait_until(app, lambda: window.scan_worker.isFinished())
        source = tmp_path / "dark.png"; Image.new("RGB", (48, 32), (30, 35, 40)).save(source)
        window.import_paths([str(source)])
        wait_until(app, lambda: bool(window.media) and window.import_worker.isFinished())
        if window.preview_worker:
            wait_until(app, lambda: window.preview_worker.isFinished())
        window.auto_enhance()
        assert window.sliders["brightness"].value() > 0
        window.engine_combo.setCurrentIndex(1)
        window.add_selected()
        window.enhance_selected()
        wait_until(app, lambda: len(window.jobs) == 2 and all(j.status in ("Completed", "Failed") for j in window.jobs))
        assert window.jobs[0].status == "Completed", window.jobs[0].error
        assert window.jobs[1].status == "Completed", window.jobs[1].error
        assert window.jobs[0].output != window.jobs[1].output
        assert Image.open(window.jobs[0].output).size == (96, 64)
        assert window.compare.result.width() == 96
        wait_until(app, lambda: window.job_worker.isFinished())
        window.selected_region = (4, 4, 20, 20)
        window.preview_selected()
        wait_until(app, lambda: len(window.jobs) == 3 and window.jobs[-1].status in ("Completed", "Failed"))
        assert window.jobs[-1].status == "Completed", window.jobs[-1].error
        assert window.preview_dialogs
        assert Image.open(window.jobs[-1].output).size == (32, 32)
        wait_until(app, lambda: window.job_worker.isFinished())
        window.navigate(3)
        assert window.pages.currentIndex() == 1
        window.navigate(4)
        assert window.pages.currentIndex() == 2
    finally:
        if window.job_worker and window.job_worker.isRunning():
            window.job_worker.cancel.set()
            wait_until(app, lambda: window.job_worker.isFinished())
        window.close()
        app.processEvents()
