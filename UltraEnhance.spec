# Run with PyInstaller on Windows. Engines and weights are intentionally separate.
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH)
a = Analysis(
    [str(root / 'main.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'README.md'), '.'), (str(root / 'LICENSE'), '.'),
           (str(root / 'THIRD_PARTY_NOTICES.md'), '.'), (str(root / 'licenses'), 'licenses')]
          + sum((copy_metadata(package) for package in ['PySide6', 'PySide6_Essentials', 'shiboken6',
                 'Pillow', 'opencv-python-headless', 'numpy', 'psutil']), []),
    hiddenimports=[],
    hookspath=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtPdf',
              'matplotlib', 'tkinter', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='UltraEnhanceAI',
          debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='UltraEnhanceAI')
