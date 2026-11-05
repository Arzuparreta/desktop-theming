# Bundled dependencies

The frozen payload dynamically links Qt and includes its Python bindings.
Dependency versions are recorded by the build requirements and CI logs.

- Python: PSF license. Source and notices: https://www.python.org/downloads/source/
- PySide6 / Shiboken6 6.8.3: LGPLv3/GPLv3/commercial options.
  Source: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/
- Qt 6.8.3: module-specific LGPLv3/GPLv3/commercial licenses and third-party notices.
  Source: https://download.qt.io/official_releases/qt/6.8/6.8.3/single/
  Licensing: https://doc.qt.io/qt-6/licensing.html
- Pillow: HPND and bundled codec notices.
  Source: https://github.com/python-pillow/Pillow
- PyInstaller bootloader: GPL with bootloader distribution exception.
  https://pyinstaller.org/en/stable/license.html

The AppImage is extractable (`--appimage-extract`). Qt shared libraries are in
`usr/app/_internal/PySide6/Qt/lib` inside the AppDir and can be replaced with
ABI-compatible builds. License files and package metadata shipped by the Python
wheels are included under `usr/app/_internal/licenses` where available. This
notice supplements upstream notices; it does not replace module-specific terms.
