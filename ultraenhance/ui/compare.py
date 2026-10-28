"""Image comparison in image coordinates, with a synchronized split view."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class CompareView(QWidget):
    regionChanged = Signal(object)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(280, 260)
        self.setMouseTracking(True)
        self.original = QPixmap()
        self.result = QPixmap()
        self.split = 0.5
        self.zoom = 1.0
        self.pan = QPointF()
        self.mode = "Slider"
        self.drag = ""
        self.last = QPointF()
        self.selection_start = None
        self.selection = None
        self.selecting = False
        self.source_size = (0, 0)
        self.setToolTip("Drag the divider to compare. Scroll to zoom. Drag elsewhere to pan.\nRegion preview: select a rectangle with the Region tool.")

    def set_images(self, original, result=None, source_size=None):
        self.original = original
        self.result = result or QPixmap()
        self.source_size = source_size or (original.width(), original.height())
        self.zoom = 1
        self.pan = QPointF()
        self.selection = None
        self.update()

    def set_result(self, result):
        self.result = result
        self.update()

    def set_mode(self, mode):
        self.mode = mode
        self.update()

    def fit(self):
        self.zoom = 1
        self.pan = QPointF()
        self.update()

    def actual_size(self):
        if not self.original.isNull():
            # Native result pixels are used when a full enhanced image is present.
            native_width = self.result.width() if not self.result.isNull() else self.source_size[0]
            self.zoom = native_width / max(1, self.image_rect().width() / self.zoom)
            self.pan = QPointF()
            self.update()

    def image_rect(self, panel=0):
        width = self.width() / 2 if self.mode == "Side by side" else self.width()
        area = QRectF(panel * width + 20, 32, width - 40, self.height() - 64)
        if self.original.isNull():
            return area
        aspect = self.source_size[0] / max(1, self.source_size[1])
        w = min(area.width(), area.height() * aspect) * self.zoom
        h = w / aspect
        return QRectF(area.center().x() - w / 2 + self.pan.x(), area.center().y() - h / 2 + self.pan.y(), w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111216"))
        painter.setPen(QColor("#1d1e24"))
        for x in range(10, self.width(), 24):
            for y in range(10, self.height(), 24):
                painter.drawPoint(x, y)
        if self.original.isNull():
            painter.setRenderHint(QPainter.Antialiasing)
            center = self.rect().center()
            box = QRectF(center.x() - 34, center.y() - 80, 68, 56)
            painter.setPen(QPen(QColor("#6f648d"), 2))
            painter.setBrush(QColor("#24212e"))
            painter.drawRoundedRect(box, 12, 12)
            painter.drawLine(QPointF(center.x() - 18, center.y() - 40), QPointF(center.x() - 4, center.y() - 55))
            painter.drawLine(QPointF(center.x() - 4, center.y() - 55), QPointF(center.x() + 15, center.y() - 35))
            painter.setPen(QColor("#eceaf2"))
            font = painter.font(); font.setPointSize(16); font.setBold(True); painter.setFont(font)
            painter.drawText(QRectF(0, center.y(), self.width(), 34), Qt.AlignCenter, "Every detail deserves a second look.")
            font.setPointSize(10); font.setBold(False); painter.setFont(font)
            painter.setPen(QColor("#9996a6"))
            painter.drawText(QRectF(20, center.y() + 42, self.width() - 40, 45), Qt.AlignCenter | Qt.TextWordWrap,
                             "Drop an image or video here, or import your files to begin.")
            return
        painter.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom < 3)
        if self.mode == "Side by side":
            for panel, pix in enumerate((self.original, self.result)):
                painter.save()
                painter.setClipRect(QRectF(panel * self.width() / 2, 0, self.width() / 2, self.height()))
                if not pix.isNull():
                    painter.drawPixmap(self.image_rect(panel), pix, QRectF(pix.rect()))
                painter.restore()
            painter.setPen(QColor("#45414f")); painter.drawLine(self.width() // 2, 0, self.width() // 2, self.height())
        else:
            rect = self.image_rect()
            painter.drawPixmap(rect, self.original, QRectF(self.original.rect()))
            if not self.result.isNull():
                painter.save()
                painter.setClipRect(QRectF(self.width() * self.split, 0, self.width(), self.height()))
                painter.drawPixmap(rect, self.result, QRectF(self.result.rect()))
                painter.restore()
                x = round(self.width() * self.split)
                painter.setPen(QPen(QColor("#ddd4ff"), 2)); painter.drawLine(x, 0, x, self.height())
                painter.setBrush(QColor("#d2c3ff")); painter.drawRoundedRect(QRectF(x - 13, self.height() / 2 - 21, 26, 42), 8, 8)
                painter.setPen(QColor("#231c34")); painter.drawText(QRectF(x - 13, self.height() / 2 - 21, 26, 42), Qt.AlignCenter, "↔")
        painter.setPen(QColor("#e1dee9"))
        painter.drawText(16, 22, "ORIGINAL")
        if not self.result.isNull():
            painter.drawText(self.width() - 155, 22, "ENHANCED RESULT")
        if self.selection and self.mode != "Side by side":
            rect = self.image_rect()
            x1, y1, x2, y2 = self.selection
            selected = QRectF(rect.x() + x1 * rect.width(), rect.y() + y1 * rect.height(), (x2 - x1) * rect.width(), (y2 - y1) * rect.height())
            painter.setPen(QPen(QColor("#c6a8ff"), 2, Qt.DashLine)); painter.setBrush(QColor(188, 156, 255, 30))
            painter.drawRect(selected.normalized())

    def normalized_point(self, pos):
        rect = self.image_rect()
        return (max(0., min(1., (pos.x() - rect.x()) / max(1, rect.width()))),
                max(0., min(1., (pos.y() - rect.y()) / max(1, rect.height()))))

    def mousePressEvent(self, event):
        if self.original.isNull():
            return
        self.last = event.position()
        if self.selecting and self.mode == "Slider":
            self.drag = "region"; self.selection_start = self.normalized_point(event.position())
        elif self.mode == "Slider" and not self.result.isNull() and abs(event.position().x() - self.width() * self.split) < 18:
            self.drag = "split"
        else:
            self.drag = "pan"

    def mouseMoveEvent(self, event):
        if self.drag == "split":
            self.split = max(0.02, min(0.98, event.position().x() / self.width()))
        elif self.drag == "pan":
            self.pan += event.position() - self.last
        elif self.drag == "region":
            self.selection = (*self.selection_start, *self.normalized_point(event.position()))
        self.last = event.position()
        self.update()

    def mouseReleaseEvent(self, event):
        if self.drag == "region" and self.selection:
            x1, y1, x2, y2 = self.selection
            w, h = self.source_size
            region = (round(min(x1, x2) * w), round(min(y1, y2) * h), round(max(x1, x2) * w), round(max(y1, y2) * h))
            if region[2] - region[0] >= 8 and region[3] - region[1] >= 8:
                self.regionChanged.emit(region)
        self.drag = ""

    def wheelEvent(self, event):
        self.zoom = max(0.2, min(32, self.zoom * (1.15 if event.angleDelta().y() > 0 else 1 / 1.15)))
        self.update()
