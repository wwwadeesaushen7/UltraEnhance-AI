STYLE = """
QWidget { background: #17181d; color: #e6e5ec; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }
QMainWindow { background: #111216; }
QFrame#sidebar { background: #111216; border-right: 1px solid #292a31; }
QFrame#panel { background: #1c1d23; border: 1px solid #30313a; border-radius: 12px; }
QLabel { background: transparent; }
QLabel#eyebrow { color: #8b889a; font-size: 10px; font-weight: 600; letter-spacing: 1px; }
QLabel#title { font-size: 26px; font-weight: 650; color: #f1eff6; }
QLabel#muted { color: #9593a3; }
QLabel#brand { font-size: 17px; font-weight: 700; }
QLabel#badge { color: #bfa8ed; background: #292333; border: 1px solid #443653; border-radius: 7px; padding: 6px 10px; font-size: 11px; }
QPushButton { background: #272830; border: 1px solid #3a3b46; border-radius: 7px; padding: 9px 14px; font-weight: 550; }
QPushButton:hover { background: #33343e; border-color: #77717f; }
QPushButton:pressed { background: #41404c; }
QPushButton:disabled { color: #6d6b79; background: #23242a; border-color: #303039; }
QPushButton#primary { background: #cbb4ff; border-color: #cbb4ff; color: #221830; font-weight: 700; }
QPushButton#primary:hover { background: #ddcdff; }
QPushButton#primary:disabled { background: #494151; color: #84798f; border-color: #494151; }
QPushButton#nav { text-align: left; background: transparent; color: #a19dac; border: 0; padding: 12px 15px; }
QPushButton#nav:checked { background: #2b2538; color: #d9c9fc; border-left: 3px solid #c2a3f8; }
QPushButton#nav:hover { background: #24232c; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #14151a; border: 1px solid #3a3a46; border-radius: 6px; padding: 8px; selection-background-color: #675482; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #ba9fea; }
QComboBox::drop-down { width: 22px; border: 0; }
QComboBox QAbstractItemView { background: #23242c; selection-background-color: #524263; padding: 5px; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #656070; border-radius: 4px; background: #17181d; }
QCheckBox::indicator:checked { background: #bea2ed; border-color: #bea2ed; image: none; }
QSlider::groove:horizontal { background: #36333e; height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #b99ae9; border-radius: 2px; }
QSlider::handle:horizontal { background: #dbc9fa; width: 12px; margin: -4px 0; border-radius: 6px; }
QScrollArea { border: 0; }
QScrollBar:vertical { background: #18191e; width: 9px; }
QScrollBar::handle:vertical { background: #45414e; border-radius: 4px; min-height: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QListWidget { background: #14151a; border: 1px solid #30313a; border-radius: 8px; padding: 5px; outline: 0; }
QListWidget::item { padding: 12px 8px; border-radius: 5px; }
QListWidget::item:selected { background: #30273e; color: #ded1f7; }
QTableWidget { background: #17181e; border: 1px solid #33323c; border-radius: 9px; gridline-color: #2f2e38; selection-background-color: #382d49; }
QHeaderView::section { background: #23232b; color: #ada6bb; border: 0; padding: 12px; font-weight: 600; }
QTableWidget::item { padding: 8px; }
QProgressBar { border: 0; background: #2b2933; border-radius: 3px; min-height: 6px; max-height: 6px; color: transparent; }
QProgressBar::chunk { background: #b69aeb; border-radius: 3px; }
QPlainTextEdit { background: #111217; border: 1px solid #36333e; border-radius: 8px; color: #bcb5c9; padding: 10px; font-family: Consolas, monospace; }
QToolTip { background: #38313f; color: #f2eafb; border: 1px solid #675675; padding: 6px; }
QSplitter::handle { background: #2c2933; width: 1px; }
QStatusBar { background: #111216; color: #9e96ad; }
"""
