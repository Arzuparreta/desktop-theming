# Build a relocatable directory, then wrap it once in an AppImage.
from importlib.metadata import distribution
from pathlib import Path

root = Path(SPECPATH).parent
notices = [(str(root / 'packaging/THIRD_PARTY.md'), 'licenses')]
for package in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'Pillow', 'PyInstaller'):
    package_info = distribution(package)
    for resource in package_info.files or []:
        if resource.name == 'METADATA' or any('license' in part.lower() or part == 'COPYING.txt'
                                              for part in resource.parts):
            source = Path(package_info.locate_file(resource))
            if source.is_file():
                notices.append((str(source), f'licenses/{package}/{resource.parent}'))
analysis = Analysis(
    [str(root / 'packaging/launcher.py')],
    pathex=[str(root)],
    hookspath=[str(root / "packaging/hooks")],
    datas=[(str(root / 'desktop_theming/ui'), 'desktop_theming/ui'),
           (str(root / 'bin/walltheme'), 'bin')] + notices,
    hiddenimports=['PIL.Image', 'PIL.ImageOps', 'PIL.ImageStat'],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineQuick',
              'PySide6.QtWebEngineWidgets', 'tkinter'],
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
          name='desktop-theming', console=True, strip=False, upx=False)
coll = COLLECT(exe, analysis.binaries, analysis.datas,
               strip=False, upx=False, name='desktop-theming')
