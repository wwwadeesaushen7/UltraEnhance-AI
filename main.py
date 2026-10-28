"""UltraEnhance AI desktop entry point (Python 3.11+)."""
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from ultraenhance.config import load_settings
from ultraenhance.ui.window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("UltraEnhance AI")
    app.setOrganizationName("UltraEnhance")
    app.setStyle("Fusion")
    try:
        window = MainWindow(load_settings())
        window.show()
    except Exception as exc:
        QMessageBox.critical(None, "Unable to start", str(exc))
        return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
