"""Native desktop workspace; every long-running operation lives off the UI thread."""
from dataclasses import replace
import math
from pathlib import Path
import tempfile
import time

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSlider,
    QSpinBox, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..backends import BackendManager, SOURCES
from ..config import PRESETS, Settings, save_settings
from ..image_engine import JobOptions
from ..jobs import Job, load_queue, save_queue
from ..media import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, target_size
from .compare import CompareView
from .theme import STYLE
from .workers import ImportWorker, JobWorker, PreviewWorker, ScanWorker


def label(text, name="", wrap=False):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback, name=""):
    widget = QPushButton(text)
    widget.setObjectName(name)
    widget.clicked.connect(callback)
    return widget


def combo(items, current=None):
    widget = QComboBox()
    widget.addItems(items)
    if current:
        widget.setCurrentText(current)
    return widget


def row(*widgets):
    box = QWidget()
    layout = QHBoxLayout(box); layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget)
    return box


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.backends = BackendManager(settings)
        self.media = {}
        self.current_path = ""
        self.current_kind = "image"
        self.selected_region = None
        self.job_worker = None
        self.scan_worker = None
        self.import_worker = None
        self.preview_worker = None
        self.pending_preview = ""
        self.queue_running = False
        self.active_job = None
        self.stage_start = time.monotonic()
        self.last_stage = ""
        self.preview_directory = tempfile.TemporaryDirectory(prefix="ultraenhance-session-")
        self.preview_dialogs = []
        self.setWindowTitle("UltraEnhance AI — Local enhancement studio")
        self.resize(1440, 900)
        self.setMinimumSize(1040, 680)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        self.jobs = []
        history_error = ""
        try:
            self.jobs = load_queue()
        except Exception as exc:
            history_error = str(exc)
        self.build_ui()
        self.render_queue()
        self.scan_backends()
        if history_error:
            QTimer.singleShot(0, lambda: self.show_error(history_error))
        self.statusBar().showMessage("Local processing · no cloud uploads · one active job at a time")

    def build_ui(self):
        root = QWidget(); outer = QVBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        body = QWidget(); layout = QHBoxLayout(body); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(202)
        nav = QVBoxLayout(sidebar); nav.setContentsMargins(16, 29, 16, 22); nav.setSpacing(7)
        monogram = label("UE", "badge"); monogram.setFixedWidth(38); monogram.setAlignment(Qt.AlignCenter)
        nav.addWidget(row(monogram, label("UltraEnhance", "brand")))
        nav.addWidget(label("L O C A L   A I   S T U D I O", "eyebrow")); nav.addSpacing(35)
        nav.addWidget(label("WORKSPACE", "eyebrow")); nav.addSpacing(8)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = []
        for index, text in enumerate(["◈   Image Enhancer", "▷   Video Enhancer", "▦   Batch Processing", "≡   Processing Queue", "⚙   Settings"]):
            item = button(text, lambda checked=False, i=index: self.navigate(i), "nav")
            item.setCheckable(True); self.nav_group.addButton(item, index); nav.addWidget(item); self.nav_buttons.append(item)
        self.nav_buttons[0].setChecked(True)
        nav.addStretch()
        nav.addWidget(label("BUILT TO WORK LOCALLY", "eyebrow"))
        nav.addWidget(label("Your files. Your hardware.\nNo subscriptions.", "muted"))
        nav.addSpacing(20)
        self.engine_badge = label("Checking engines…", "badge", True); nav.addWidget(self.engine_badge)
        nav.addWidget(label("UltraEnhance AI   /   0.1.0", "muted"))
        self.pages = QStackedWidget()
        self.studio = self.build_studio(); self.queue_page = self.build_queue(); self.settings_page = self.build_settings()
        self.pages.addWidget(self.studio); self.pages.addWidget(self.queue_page); self.pages.addWidget(self.settings_page)
        layout.addWidget(sidebar); layout.addWidget(self.pages, 1)
        outer.addWidget(body, 1)
        footer = QWidget(); fl = QVBoxLayout(footer); fl.setContentsMargins(20, 10, 20, 10)
        self.progress_label = label("Ready to create a clearer picture", "muted")
        self.cancel_button = button("Cancel current", self.cancel_current); self.cancel_button.setEnabled(False)
        self.cancel_button.setFixedWidth(150)
        fl.addWidget(row(self.progress_label, self.cancel_button))
        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0); self.progress_bar.setTextVisible(False); fl.addWidget(self.progress_bar)
        outer.addWidget(footer)
        self.setCentralWidget(root)
        action = QAction("Import files", self); action.setShortcut("Ctrl+O"); action.triggered.connect(self.choose_files); self.addAction(action)

    def build_studio(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(24, 26, 24, 18); layout.setSpacing(18)
        header = QHBoxLayout()
        titles = QVBoxLayout(); titles.addWidget(label("MAKE MORE OF EVERY PIXEL", "eyebrow"))
        self.page_title = label("Image Enhancer", "title"); titles.addWidget(self.page_title)
        self.page_subtitle = label("Restore clarity. Reveal texture. Keep it natural.", "muted"); titles.addWidget(self.page_subtitle)
        header.addLayout(titles); header.addStretch()
        self.import_button = button("＋  Import files", self.choose_files, "primary"); header.addWidget(self.import_button)
        layout.addLayout(header)
        splitter = QSplitter(Qt.Horizontal)
        file_panel = QWidget(); fp = QVBoxLayout(file_panel); fp.setContentsMargins(0, 0, 0, 0)
        self.file_count = label("YOUR FILES   ·   0", "eyebrow"); fp.addWidget(self.file_count)
        self.files = QListWidget(); self.files.setIconSize(QSize(80, 54)); self.files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.files.currentItemChanged.connect(self.select_media); fp.addWidget(self.files, 1)
        fp.addWidget(button("Remove selected", self.remove_files))
        file_panel.setMinimumWidth(135); file_panel.setMaximumWidth(240)
        splitter.addWidget(file_panel)
        center = QWidget(); cp = QVBoxLayout(center); cp.setContentsMargins(14, 0, 14, 0); cp.setSpacing(12)
        self.file_heading = label("PREVIEW WORKSPACE", "eyebrow"); cp.addWidget(self.file_heading)
        self.source_info = label("Import a file to inspect its resolution and quality.", "muted", True); cp.addWidget(self.source_info)
        self.compare = CompareView(); cp.addWidget(self.compare, 1)
        self.compare.regionChanged.connect(self.set_region)
        self.comparison_mode = combo(["Slider", "Side by side"]); self.comparison_mode.currentTextChanged.connect(self.compare.set_mode)
        self.region_button = button("Select region", self.toggle_region); self.region_button.setCheckable(True)
        cp.addWidget(row(self.comparison_mode, button("Fit", self.compare.fit), button("100%", self.compare.actual_size), self.region_button))
        self.analysis_text = label("SMART ASSIST\nQuality recommendations appear when you import a file.", "muted", True)
        self.auto_button = button("✧  Auto Enhance", self.auto_enhance); self.auto_button.setEnabled(False)
        cp.addWidget(row(self.analysis_text, self.auto_button))
        self.preview_note = label("Preview uses the selected engine. No artificial detail-recovery claims.", "muted", True); cp.addWidget(self.preview_note)
        splitter.addWidget(center)
        panel = QFrame(); panel.setObjectName("panel"); panel.setMinimumWidth(278); panel.setMaximumWidth(360)
        right = QVBoxLayout(panel); right.setContentsMargins(16, 18, 16, 16)
        right.addWidget(label("ENHANCEMENT SETTINGS", "eyebrow"))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); form = QVBoxLayout(content); form.setContentsMargins(0, 8, 8, 8); form.setSpacing(10)
        form.addWidget(label("Processing engine"))
        self.engine_combo = QComboBox(); self.engine_combo.addItem("Real-ESRGAN · AI", "AI"); self.engine_combo.addItem("Lanczos · CPU (non-AI)", "CPU"); form.addWidget(self.engine_combo)
        self.engine_combo.currentIndexChanged.connect(self.update_estimate)
        form.addWidget(label("Content model"))
        self.model_combo = QComboBox()
        for title, name in [("Photograph · x4plus", "realesrgan-x4plus"), ("Illustration / anime · x4plus", "realesrgan-x4plus-anime"), ("Anime video · v3", "realesr-animevideov3")]:
            self.model_combo.addItem(title, name)
        form.addWidget(self.model_combo)
        form.addWidget(label("Processing quality"))
        self.preset_combo = combo(list(PRESETS), self.settings.preset); form.addWidget(self.preset_combo)
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        self.quality_note = label("Balanced settings for everyday work.", "muted", True); form.addWidget(self.quality_note)
        form.addSpacing(8); form.addWidget(label("OUTPUT RESOLUTION", "eyebrow"))
        self.target_combo = combo(["2×", "3×", "4×", "1080p", "1440p", "4K", "Custom"]); form.addWidget(self.target_combo)
        self.target_combo.currentTextChanged.connect(self.update_estimate)
        self.custom_width = QSpinBox(); self.custom_height = QSpinBox()
        for spin, value in ((self.custom_width, 3840), (self.custom_height, 2160)):
            spin.setRange(2, 16384); spin.setValue(value); spin.valueChanged.connect(self.update_estimate)
        self.custom_box = row(self.custom_width, label("×"), self.custom_height); form.addWidget(self.custom_box); self.custom_box.hide()
        self.aspect = QCheckBox("Preserve original aspect ratio"); self.aspect.setChecked(True); self.aspect.toggled.connect(self.update_estimate); form.addWidget(self.aspect)
        self.resolution_label = label("—", "badge"); form.addWidget(self.resolution_label)
        form.addSpacing(10); form.addWidget(label("CONVENTIONAL ADJUSTMENTS", "eyebrow"))
        self.sliders = {}
        for key, title, low, high, initial in [("denoise", "Noise reduction", 0, 20, 0), ("sharpness", "Sharpness", 0, 200, 0),
                ("brightness", "Brightness", -50, 50, 0), ("contrast", "Contrast", 50, 200, 100), ("saturation", "Saturation", 0, 200, 100)]:
            value = label(str(initial), "muted"); value.setAlignment(Qt.AlignRight)
            form.addWidget(row(label(title), value))
            slider = QSlider(Qt.Horizontal); slider.setRange(low, high); slider.setValue(initial)
            slider.valueChanged.connect(lambda v, lab=value: lab.setText(str(v)))
            form.addWidget(slider); self.sliders[key] = slider
        self.color_correct = QCheckBox("Gentle gray-world white balance"); form.addWidget(self.color_correct)
        self.artifacts = QCheckBox("Reduce compression artifacts"); form.addWidget(self.artifacts)
        self.video_options = QWidget(); vl = QVBoxLayout(self.video_options); vl.setContentsMargins(0, 8, 0, 8)
        vl.addWidget(label("VIDEO OPTIONS", "eyebrow")); self.fps_combo = combo(["Original FPS", "30 FPS · RIFE", "60 FPS · RIFE"]); vl.addWidget(self.fps_combo)
        self.stabilize = QCheckBox("Stabilize · FFmpeg deshake"); vl.addWidget(self.stabilize)
        vl.addWidget(label("RIFE requires a compatible Video2X build, model and exact FPS multiplier.", "muted", True)); form.addWidget(self.video_options); self.video_options.hide()
        form.addSpacing(10); form.addWidget(label("EXPORT", "eyebrow"))
        self.format_combo = combo(["PNG", "JPG", "WEBP"], self.settings.image_format); form.addWidget(self.format_combo)
        self.codec_combo = QComboBox(); self.codec_combo.addItem("H.264", "libx264"); self.codec_combo.addItem("H.265", "libx265"); form.addWidget(self.codec_combo); self.codec_combo.hide()
        self.export_quality = QSpinBox(); self.export_quality.setRange(1, 100); self.export_quality.setValue(95); self.export_quality.setPrefix("Image quality: "); form.addWidget(self.export_quality)
        self.crf = QSpinBox(); self.crf.setRange(0, 40); self.crf.setValue(self.settings.crf); self.crf.setPrefix("Encoding CRF: "); form.addWidget(self.crf); self.crf.hide()
        self.output_edit = QLineEdit(self.settings.output_dir); self.output_edit.setPlaceholderText("Output folder")
        form.addWidget(row(self.output_edit, button("…", self.choose_output)))
        form.addWidget(label("Existing files are preserved. Exports receive unique names.", "muted", True))
        scroll.setWidget(content); right.addWidget(scroll, 1)
        self.preview_button = button("Preview selected region", self.preview_selected); right.addWidget(self.preview_button)
        self.queue_button = button("Add to queue", self.add_selected); right.addWidget(self.queue_button)
        self.export_button = button("Enhance & export  ↗", self.enhance_selected, "primary"); right.addWidget(self.export_button)
        self.preview_button.setEnabled(False); self.queue_button.setEnabled(False); self.export_button.setEnabled(False)
        splitter.addWidget(panel); splitter.setSizes([165, 590, 310]); layout.addWidget(splitter, 1)
        return page

    def build_queue(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(30, 30, 30, 24); layout.setSpacing(18)
        layout.addWidget(label("PROCESS WITH CONFIDENCE", "eyebrow")); layout.addWidget(label("Processing Queue", "title"))
        layout.addWidget(label("One demanding job at a time. Settings are captured when each job is added.", "muted"))
        self.queue_table = QTableWidget(0, 5); self.queue_table.setHorizontalHeaderLabels(["Source", "Engine / target", "Status", "Output", "Details"])
        self.queue_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.queue_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.queue_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.queue_table.verticalHeader().hide(); self.queue_table.verticalHeader().setDefaultSectionSize(46)
        self.queue_table.itemSelectionChanged.connect(self.queue_details); self.queue_table.cellDoubleClicked.connect(lambda r, c: self.open_selected_output())
        layout.addWidget(self.queue_table, 1)
        layout.addWidget(row(button("Start queue", self.start_queue, "primary"), button("Stop after current", self.stop_queue),
                             button("Move up", lambda: self.move_job(-1)), button("Move down", lambda: self.move_job(1)), button("Cancel selected", self.cancel_selected_job)))
        layout.addWidget(row(button("Retry selected", self.retry_job), button("Open output", self.open_selected_output),
                             button("Open output folder", self.open_selected_folder), button("Clear finished", self.clear_finished)))
        self.details = QPlainTextEdit(); self.details.setReadOnly(True); self.details.setMaximumHeight(165)
        self.details.setPlaceholderText("Select a job to inspect its output path or complete error message."); layout.addWidget(self.details)
        return page

    def build_settings(self):
        page = QWidget(); outer = QVBoxLayout(page); outer.setContentsMargins(30, 30, 30, 24)
        outer.addWidget(label("YOUR HARDWARE. YOUR WORKFLOW.", "eyebrow")); outer.addWidget(label("Settings & engines", "title"))
        scroll = QScrollArea(); scroll.setWidgetResizable(True); content = QWidget(); layout = QVBoxLayout(content)
        layout.addWidget(label("BACKEND LOCATIONS", "eyebrow"))
        layout.addWidget(label("Choose extracted official engines. This app never installs graphics drivers or downloads models automatically.", "muted", True))
        form = QFormLayout(); self.settings_fields = {}
        for key, title, directory in [("realesrgan", "Real-ESRGAN executable", False), ("video2x", "Video2X 6.x executable", False),
                                     ("ffmpeg", "FFmpeg executable", False), ("ffprobe", "FFprobe executable", False),
                                     ("models_dir", "Real-ESRGAN models folder", True), ("output_dir", "Default output folder", True), ("temp_dir", "Temporary folder", True)]:
            edit = QLineEdit(getattr(self.settings, key)); edit.setPlaceholderText("Automatic detection" if not directory else "System default" if key == "temp_dir" else "Choose a folder")
            self.settings_fields[key] = edit
            form.addRow(title, row(edit, button("Browse", lambda checked=False, e=edit, d=directory: self.browse_setting(e, d))))
            if key in SOURCES:
                link = label(f'<a style="color:#c5a4fa" href="{SOURCES[key]}">Official downloads ↗</a>'); link.setOpenExternalLinks(True); form.addRow("", link)
        self.gpu_spin = QSpinBox(); self.gpu_spin.setRange(-1, 31); self.gpu_spin.setSpecialValueText("Automatic GPU"); self.gpu_spin.setValue(self.settings.gpu_id); form.addRow("Vulkan device ID", self.gpu_spin)
        self.tile_spin = QSpinBox(); self.tile_spin.setRange(0, 2048); self.tile_spin.setSingleStep(32); self.tile_spin.setSpecialValueText("Automatic tile size"); self.tile_spin.setValue(self.settings.tile_size); form.addRow("Real-ESRGAN tile size", self.tile_spin)
        self.default_preset = combo(list(PRESETS), self.settings.preset); form.addRow("Default processing quality", self.default_preset)
        self.default_image_format = combo(["PNG", "JPG", "WEBP"], self.settings.image_format); form.addRow("Default image export", self.default_image_format)
        self.default_video_format = combo(["MP4", "MKV"], self.settings.video_format); form.addRow("Default video container", self.default_video_format)
        self.default_codec = combo(["libx264", "libx265"], self.settings.codec); form.addRow("Default video codec", self.default_codec)
        self.default_crf = QSpinBox(); self.default_crf.setRange(0, 40); self.default_crf.setValue(self.settings.crf); form.addRow("Default encoding CRF", self.default_crf)
        form.addRow("Concurrent processing", label("1 job · fixed for memory safety in this release", "muted"))
        layout.addLayout(form)
        layout.addWidget(label("Smaller tiles reduce Real-ESRGAN GPU memory. Video2X manages its own tiling; this setting does not change Video2X memory use.", "muted", True))
        layout.addWidget(row(button("Save settings & check engines", self.apply_settings, "primary"), button("Check engines", self.scan_backends)))
        layout.addWidget(label("HARDWARE & BACKEND REPORT", "eyebrow")); self.backend_report = QPlainTextEdit(); self.backend_report.setReadOnly(True); self.backend_report.setMinimumHeight(240); layout.addWidget(self.backend_report)
        layout.addWidget(label("FEATURE AVAILABILITY", "eyebrow"))
        layout.addWidget(label("GFPGAN face restoration is not integrated in this release. RIFE runs through compatible Video2X 6.x builds only at exact integer FPS multipliers. Stabilization is the conventional FFmpeg deshake filter. HDR/10-bit preservation is not supported: video export is 8-bit SDR. Maximum Quality uses image TTA and slower video encoding; it can take substantially longer.", "muted", True))
        layout.addWidget(label("AI model outputs may alter textures. Inspect results before replacing originals. Source files are never modified.", "muted", True))
        scroll.setWidget(content); outer.addWidget(scroll, 1)
        return page

    def navigate(self, index):
        self.nav_buttons[index].setChecked(True)
        if index < 3:
            self.pages.setCurrentIndex(0)
            self.current_kind = ("image", "video", "all")[index]
            self.page_title.setText(("Image Enhancer", "Video Enhancer", "Batch Processing")[index])
            self.page_subtitle.setText(("Restore clarity. Reveal texture. Keep it natural.", "Bring a clearer perspective to every frame.", "Select multiple files and give them one consistent treatment.")[index])
            self.refresh_files()
        else:
            self.pages.setCurrentIndex(index - 2)
        effect = QGraphicsOpacityEffect(self.pages)
        self.pages.setGraphicsEffect(effect)
        self.page_animation = QPropertyAnimation(effect, b"opacity", self)
        self.page_animation.setDuration(160); self.page_animation.setStartValue(.85); self.page_animation.setEndValue(1.)
        self.page_animation.setEasingCurve(QEasingCurve.OutCubic); self.page_animation.start()

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Import images or videos", "", "Supported media (*.jpg *.jpeg *.png *.webp *.mp4 *.mov *.mkv *.avi *.webm);;All files (*)")
        self.import_paths(paths)

    def import_paths(self, paths):
        if not paths:
            return
        if self.import_worker and self.import_worker.isRunning():
            self.statusBar().showMessage("An import is already running. Wait for it to finish.", 5000); return
        if self.scan_worker and self.scan_worker.isRunning():
            self.statusBar().showMessage("Checking engines. Import files after this finishes.", 5000); return
        paths = list(dict.fromkeys(str(Path(p).resolve()) for p in paths if str(Path(p).resolve()) not in self.media))
        if not paths:
            return
        self.import_button.setEnabled(False)
        self.import_worker = ImportWorker(paths, self.backends)
        self.import_worker.item.connect(self.imported)
        self.import_worker.failed.connect(self.show_error)
        self.import_worker.finished.connect(lambda: self.import_button.setEnabled(True))
        self.statusBar().showMessage("Reading media and analyzing quality…")
        self.import_worker.start()

    def imported(self, info, image, stats):
        self.media[info.path] = (info, QPixmap.fromImage(image), stats)
        if self.current_kind != "all" and info.kind != self.current_kind:
            self.current_kind = info.kind; self.navigate(0 if info.kind == "image" else 1)
        self.refresh_files(info.path)
        self.statusBar().showMessage(f"Imported {Path(info.path).name} · {info.width} × {info.height}", 5000)

    def refresh_files(self, select=""):
        selected = select or self.current_path
        self.files.blockSignals(True); self.files.clear()
        current = None
        for path, (info, pixmap, stats) in self.media.items():
            if self.current_kind != "all" and info.kind != self.current_kind:
                continue
            item = QListWidgetItem(QIcon(pixmap), f"{Path(path).name}\n{info.width} × {info.height}")
            item.setData(Qt.UserRole, path); item.setToolTip(path); self.files.addItem(item)
            if path == selected:
                current = item
        self.files.blockSignals(False)
        self.file_count.setText(f"YOUR FILES   ·   {self.files.count()}")
        if current or self.files.count():
            self.files.setCurrentItem(current or self.files.item(0))
        else:
            self.current_path = ""; self.compare.set_images(QPixmap()); self.auto_button.setEnabled(False)
            self.preview_button.setEnabled(False); self.queue_button.setEnabled(False); self.export_button.setEnabled(False)

    def select_media(self, item, previous=None):
        if item is None:
            return
        self.current_path = item.data(Qt.UserRole)
        info, pixmap, stats = self.media[self.current_path]
        video = info.kind == "video"
        self.file_heading.setText(Path(info.path).name)
        suffix = f" · {info.fps:.3f} FPS · {info.duration:.1f}s · {'Audio' if info.audio else 'No audio'}" if video else ""
        self.source_info.setText(f"{info.width:,} × {info.height:,}   ·   {info.width / info.height:.3f}:1{suffix}")
        self.compare.set_images(pixmap, source_size=(info.width, info.height))
        self.pending_preview = self.current_path if not video else ""
        if not video:
            self.load_full_preview()
        self.selected_region = None; self.region_button.setChecked(False); self.compare.selecting = False
        self.region_button.setEnabled(not video)
        self.video_options.setVisible(video); self.codec_combo.setVisible(video); self.crf.setVisible(video); self.export_quality.setVisible(not video)
        self.color_correct.setEnabled(not video)
        self.format_combo.clear(); self.format_combo.addItems(["MP4", "MKV"] if video else ["PNG", "JPG", "WEBP"])
        self.format_combo.setCurrentText(self.settings.video_format if video else self.settings.image_format)
        self.codec_combo.setCurrentIndex(0 if self.settings.codec == "libx264" else 1)
        self.preview_button.setText("Preview first 5 seconds" if video else "Preview selected region")
        self.preview_note.setText("Video previews open in your default media player." if video else "Select a region to test enhancement before processing the full image.")
        self.analysis_text.setText(f"SMART ASSIST\nBrightness {stats['brightness']:.0%} · contrast {stats['contrast']:.0%}\nNoise estimate {stats['noise']:.1f} · sharpness {stats['sharpness']:.0f}")
        for control in (self.auto_button, self.preview_button, self.queue_button, self.export_button):
            control.setEnabled(True)
        self.update_estimate()

    def load_full_preview(self):
        if self.preview_worker and self.preview_worker.isRunning():
            return
        if not self.pending_preview:
            return
        path = self.pending_preview; self.pending_preview = ""
        self.preview_worker = PreviewWorker(path)
        self.preview_worker.ready.connect(self.full_preview_ready)
        self.preview_worker.failed.connect(self.show_error)
        self.preview_worker.finished.connect(self.load_full_preview)
        self.preview_worker.start()

    def full_preview_ready(self, path, image):
        if path == self.current_path and path in self.media:
            info = self.media[path][0]
            self.compare.set_images(QPixmap.fromImage(image), source_size=(info.width, info.height))

    def remove_files(self):
        for item in self.files.selectedItems():
            self.media.pop(item.data(Qt.UserRole), None)
        self.refresh_files()

    def apply_preset(self, name):
        self.tile_spin.setValue(PRESETS[name]["tile"])
        self.quality_note.setText({"Fast": "64px tiles; lightweight loading and fast video encoding.",
            "Balanced": "128px tiles; one inference worker; medium video encoding.",
            "Maximum Quality": "256px tiles + image TTA. Slower encoding; substantially more time and resources."}[name])

    def update_estimate(self, *args):
        self.custom_box.setVisible(self.target_combo.currentText() == "Custom")
        self.model_combo.setEnabled(self.engine_combo.currentData() == "AI")
        if self.current_path not in self.media:
            return
        info = self.media[self.current_path][0]
        try:
            size = target_size(info.width, info.height, self.target_combo.currentText(), (self.custom_width.value(), self.custom_height.value()), self.aspect.isChecked(), even=info.kind == "video")
            self.resolution_label.setText(f"{info.width} × {info.height}   →   {size[0]} × {size[1]}")
        except Exception as exc:
            self.resolution_label.setText(str(exc))

    def auto_enhance(self):
        if self.current_path not in self.media:
            return
        info, pixmap, stats = self.media[self.current_path]
        for key, value in stats["recommended"].items():
            self.sliders[key].setValue(round(value * (1 if key == "denoise" else 100)))
        # Avoid recommending unnecessary enlargement of an already large source.
        self.target_combo.setCurrentText("4K" if max(info.width, info.height) >= 1920 else "2×")
        self.statusBar().showMessage("Applied measured brightness, contrast, noise and sharpness recommendations. Review settings before processing.", 8000)

    def options(self, path=None):
        path = path or self.current_path
        video = self.media[path][0].kind == "video"
        opts = JobOptions(engine=self.engine_combo.currentData(), model=self.model_combo.currentData(), preset=self.preset_combo.currentText(),
            target=self.target_combo.currentText(), width=self.custom_width.value(), height=self.custom_height.value(), preserve=self.aspect.isChecked(),
            denoise=self.sliders["denoise"].value(), sharpness=self.sliders["sharpness"].value() / 100,
            brightness=self.sliders["brightness"].value() / 100, contrast=self.sliders["contrast"].value() / 100, saturation=self.sliders["saturation"].value() / 100,
            color_correct=self.color_correct.isChecked() and not video, artifact_reduction=self.artifacts.isChecked(),
            image_format=self.format_combo.currentText() if not video else self.settings.image_format,
            video_format=self.format_combo.currentText() if video else self.settings.video_format,
            quality=self.export_quality.value(), codec=self.codec_combo.currentData(), crf=self.crf.value(),
            interpolation=(0, 30, 60)[self.fps_combo.currentIndex()] if video else 0, stabilize=self.stabilize.isChecked() and video,
            tile=self.tile_spin.value(), gpu_id=self.gpu_spin.value(), output_dir=self.output_edit.text().strip())
        # A mixed batch uses the active controls for its media type and saved defaults for the other.
        if opts.image_format not in ("PNG", "JPG", "WEBP"):
            opts.image_format = self.settings.image_format
        if opts.video_format not in ("MP4", "MKV"):
            opts.video_format = self.settings.video_format
        opts.validate()
        return opts

    def add_selected(self):
        selected = [item.data(Qt.UserRole) for item in self.files.selectedItems()]
        if not selected:
            return
        try:
            for path in selected:
                self.jobs.append(Job(path, self.options(path)))
            self.persist_queue(); self.render_queue()
            self.statusBar().showMessage(f"Added {len(selected)} job(s) to the queue.", 5000)
        except Exception as exc:
            self.show_error(str(exc))

    def enhance_selected(self):
        self.add_selected(); self.start_queue()

    def preview_selected(self):
        if not self.current_path:
            return
        if self.job_worker and self.job_worker.isRunning():
            self.statusBar().showMessage("Wait for the active job before requesting a preview.", 5000); return
        if self.scan_worker and self.scan_worker.isRunning():
            self.statusBar().showMessage("Wait for the engine checks before requesting a preview.", 5000); return
        info = self.media[self.current_path][0]
        region = None
        if info.kind == "image":
            region = self.selected_region
            if region is None:
                w, h = min(256, info.width), min(256, info.height)
                x, y = (info.width - w) // 2, (info.height - h) // 2
                region = (x, y, x + w, y + h)
            if (region[2] - region[0]) * (region[3] - region[1]) > 1024 * 1024:
                self.show_error("Preview regions are limited to one megapixel. Select a smaller region."); return
        try:
            job = Job(self.current_path, self.options(), preview=True, region=region)
            self.jobs.append(job); self.launch_job(job)
        except Exception as exc:
            self.show_error(str(exc))

    def toggle_region(self, checked=False):
        self.compare.selecting = checked
        if checked:
            self.comparison_mode.setCurrentText("Slider")
            self.statusBar().showMessage("Drag a rectangle over the image to choose a preview region.", 6000)

    def set_region(self, region):
        self.selected_region = region
        self.preview_note.setText(f"Preview region: {region[2] - region[0]} × {region[3] - region[1]} source pixels.")

    def start_queue(self):
        self.queue_running = True
        if not self.job_worker or not self.job_worker.isRunning():
            self.next_job()

    def stop_queue(self):
        self.queue_running = False
        self.statusBar().showMessage("Queue will stop after the current job. Pending jobs are retained.", 5000)

    def next_job(self):
        if not self.queue_running:
            return
        job = next((j for j in self.jobs if j.status == "Queued" and not j.preview), None)
        if job:
            self.launch_job(job)
        else:
            self.queue_running = False

    def launch_job(self, job):
        if self.scan_worker and self.scan_worker.isRunning():
            self.show_error("Backend detection is still running. Start processing after it finishes."); return
        job.status = "Running"; self.active_job = job
        self.persist_queue(); self.render_queue()
        self.job_worker = JobWorker(job, self.backends, self.preview_directory.name)
        self.job_worker.progress.connect(self.job_progress)
        self.job_worker.succeeded.connect(self.job_succeeded)
        self.job_worker.failed.connect(self.job_failed)
        self.job_worker.finished.connect(self.job_finished)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setRange(0, 0); self.progress_label.setText(f"Starting {Path(job.source).name}…")
        self.last_stage = ""; self.stage_start = time.monotonic()
        self.job_worker.start()

    def job_progress(self, stage, percentage, frames):
        if stage != self.last_stage:
            self.last_stage = stage; self.stage_start = time.monotonic()
        text = stage
        if percentage is None:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 1000); self.progress_bar.setValue(round(percentage * 10)); text += f"  ·  {percentage:.1f}%"
            if 0.1 < percentage < 100:
                remaining = (time.monotonic() - self.stage_start) * (100 / percentage - 1)
                if math.isfinite(remaining):
                    text += f"  ·  ~{round(remaining)}s left in this stage"
        if frames is not None:
            text += f"  ·  {frames:,} frames"
        self.progress_label.setText(text)

    def job_succeeded(self, output, size, image, original_region):
        job = self.active_job; job.output = output; job.status = "Completed"; job.error = ""
        self.progress_label.setText(f"{'Preview ready' if job.preview else 'Export complete'}  ·  {size[0]} × {size[1]}  ·  {Path(output).name}")
        self.progress_bar.setRange(0, 100); self.progress_bar.setValue(100)
        if image.isNull():
            if job.preview:
                QDesktopServices.openUrl(QUrl.fromLocalFile(output))
        elif job.preview:
            self.show_region_preview(job, QPixmap.fromImage(image), QPixmap.fromImage(original_region))
        elif job.source == self.current_path:
            self.compare.set_result(QPixmap.fromImage(image))
        self.persist_queue(); self.render_queue()

    def show_region_preview(self, job, result, original):
        dialog = QDialog(self); dialog.setWindowTitle("Enhanced region — actual backend output"); dialog.resize(900, 640)
        layout = QVBoxLayout(dialog); view = CompareView()
        view.set_images(original, result)
        layout.addWidget(label(f"{job.options.engine} processing · region preview · {result.width()} × {result.height()}", "muted"))
        layout.addWidget(view, 1); layout.addWidget(row(button("Fit", view.fit), button("100%", view.actual_size), button("Close", dialog.close)))
        dialog.setAttribute(Qt.WA_DeleteOnClose); self.preview_dialogs.append(dialog)
        dialog.destroyed.connect(lambda: self.preview_dialogs.remove(dialog) if dialog in self.preview_dialogs else None)
        dialog.show()

    def job_failed(self, message, canceled):
        job = self.active_job; job.status = "Canceled" if canceled else "Failed"; job.error = message
        self.progress_label.setText(f"{job.status} · {Path(job.source).name} — see queue details")
        self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0)
        self.persist_queue(); self.render_queue()
        if not canceled:
            self.details.setPlainText(message)
            self.statusBar().showMessage(message.splitlines()[0], 12000)
            if job.preview:
                self.show_error(message)

    def job_finished(self):
        self.cancel_button.setEnabled(False); self.active_job = None
        QTimer.singleShot(0, self.next_job)

    def cancel_current(self):
        self.queue_running = False
        if self.job_worker and self.job_worker.isRunning():
            self.job_worker.cancel.set()
            self.progress_label.setText("Canceling subprocesses and cleaning temporary files…")
            self.cancel_button.setEnabled(False)

    def persist_queue(self):
        try:
            save_queue(self.jobs)
        except Exception as exc:
            self.statusBar().showMessage(f"Could not save queue history: {exc}", 10000)

    def render_queue(self):
        selected = self.selected_job()
        selected_id = selected.id if selected else None
        self.queue_table.setRowCount(len(self.jobs))
        for r, job in enumerate(self.jobs):
            for c, text in enumerate([Path(job.source).name, f"{job.options.engine} · {job.options.target}", job.status, job.output, job.error.splitlines()[0] if job.error else "Region / 5s preview" if job.preview else ""]):
                item = QTableWidgetItem(text); item.setData(Qt.UserRole, job.id); item.setToolTip(text)
                if c == 2:
                    item.setForeground(QColor("#a8d7b5" if job.status == "Completed" else "#e0a0a5" if job.status in ("Failed", "Interrupted") else "#c6b3e5"))
                self.queue_table.setItem(r, c, item)
            if job.id == selected_id:
                self.queue_table.selectRow(r)
        count = sum(j.status in ("Queued", "Running") for j in self.jobs)
        self.nav_buttons[3].setText(f"≡   Processing Queue{f'  ({count})' if count else ''}")

    def selected_job(self):
        if not hasattr(self, "queue_table"):
            return None
        r = self.queue_table.currentRow()
        if r < 0:
            return None
        item = self.queue_table.item(r, 0)
        return next((j for j in self.jobs if item and j.id == item.data(Qt.UserRole)), None)

    def queue_details(self):
        job = self.selected_job()
        if job:
            self.details.setPlainText(f"Source: {job.source}\nStatus: {job.status}\nOutput: {job.output or 'Not exported'}\n\n{job.error}")

    def move_job(self, direction):
        job = self.selected_job()
        if not job or job.status != "Queued":
            return
        i = self.jobs.index(job); other = i + direction
        if 0 <= other < len(self.jobs) and self.jobs[other].status == "Queued":
            self.jobs[i], self.jobs[other] = self.jobs[other], self.jobs[i]
            self.persist_queue(); self.render_queue(); self.queue_table.selectRow(other)

    def cancel_selected_job(self):
        job = self.selected_job()
        if not job:
            return
        if job.status == "Running":
            self.cancel_current()
        elif job.status == "Queued":
            job.status = "Canceled"; job.error = "Canceled before processing."
            self.persist_queue(); self.render_queue()

    def retry_job(self):
        job = self.selected_job()
        if job and job.status in ("Failed", "Canceled", "Interrupted") and not job.preview:
            self.jobs.append(Job(job.source, replace(job.options)))
            self.persist_queue(); self.render_queue()

    def clear_finished(self):
        self.jobs = [j for j in self.jobs if j.status in ("Running", "Queued")]
        self.persist_queue(); self.render_queue(); self.details.clear()

    def open_selected_output(self):
        job = self.selected_job()
        if job and job.status == "Completed" and Path(job.output).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(job.output))

    def open_selected_folder(self):
        job = self.selected_job()
        if job and job.output and Path(job.output).parent.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(job.output).parent)))

    def choose_output(self):
        directory = QFileDialog.getExistingDirectory(self, "Output folder", self.output_edit.text())
        if directory:
            self.output_edit.setText(directory)

    def browse_setting(self, edit, directory):
        path = QFileDialog.getExistingDirectory(self, "Select folder", edit.text()) if directory else QFileDialog.getOpenFileName(self, "Select executable", edit.text(), "Executables (*.exe);;All files (*)")[0]
        if path:
            edit.setText(path)

    def apply_settings(self):
        if self.job_worker and self.job_worker.isRunning():
            self.show_error("Wait for processing to finish before changing backend settings."); return
        try:
            settings = replace(self.settings, **{key: edit.text().strip() for key, edit in self.settings_fields.items()},
                               gpu_id=self.gpu_spin.value(), tile_size=self.tile_spin.value(), preset=self.default_preset.currentText(),
                               image_format=self.default_image_format.currentText(), video_format=self.default_video_format.currentText(),
                               codec=self.default_codec.currentText(), crf=self.default_crf.value())
            save_settings(settings); self.settings = settings
            self.output_edit.setText(settings.output_dir); self.preset_combo.setCurrentText(settings.preset); self.crf.setValue(settings.crf)
            self.scan_backends()
        except Exception as exc:
            self.show_error(str(exc))

    def scan_backends(self):
        if self.scan_worker and self.scan_worker.isRunning():
            return
        if self.job_worker and self.job_worker.isRunning():
            self.statusBar().showMessage("Engine checks are available after processing finishes.", 5000); return
        self.scan_worker = ScanWorker(replace(self.settings))
        self.scan_worker.ready.connect(self.backends_ready); self.scan_worker.failed.connect(self.show_error)
        self.scan_worker.finished.connect(lambda: QTimer.singleShot(0, self.next_job))
        self.backend_report.setPlainText("Checking executables and hardware…")
        self.scan_worker.start()

    def backends_ready(self, backends, hardware):
        self.backends = backends
        available = sum(e.available for e in backends.engines.values())
        self.engine_badge.setText(f"{available} / 4 engines detected")
        lines = [f"CPU: {hardware['cpu']}", f"RAM: {hardware['ram_gb']} GB", "GPUs: " + ("; ".join(hardware["gpus"]) or "No devices enumerated"), hardware["vulkan"], ""]
        for key, engine in backends.engines.items():
            lines.extend([f"{key.upper()} — {engine.message}", f"  {engine.path or 'Choose an executable or add it to PATH.'}"])
            if engine.models:
                lines.append("  Models: " + ", ".join(engine.models))
        self.backend_report.setPlainText("\n".join(lines))
        self.statusBar().showMessage("Backend checks complete. AI availability still depends on compatible hardware and models.", 7000)

    def show_error(self, message):
        box = QMessageBox(self); box.setIcon(QMessageBox.Warning); box.setWindowTitle("UltraEnhance AI")
        box.setText(str(message).splitlines()[0][:300]); box.setDetailedText(str(message)); box.setStandardButtons(QMessageBox.Ok)
        box.setAttribute(Qt.WA_DeleteOnClose); box.open()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.import_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        # Closing during active work is intentionally confirmed to avoid silent job loss.
        workers = [w for w in (self.job_worker, self.import_worker, self.scan_worker, self.preview_worker) if w and w.isRunning()]
        if workers:
            answer = QMessageBox.question(self, "Close UltraEnhance AI?", "Background work is active. Cancel it and close?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore(); return
            self.queue_running = False
            for worker in workers:
                if hasattr(worker, "cancel"):
                    worker.cancel.set()
            # Poll without blocking the Qt event loop while subprocesses clean up.
            self.hide(); event.ignore(); QTimer.singleShot(100, self.finish_close); return
        self.persist_queue(); self.preview_directory.cleanup(); event.accept()

    def finish_close(self):
        workers = [w for w in (self.job_worker, self.import_worker, self.scan_worker, self.preview_worker) if w and w.isRunning()]
        if workers:
            QTimer.singleShot(100, self.finish_close)
        else:
            self.close()
