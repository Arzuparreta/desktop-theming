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
    datas=[(str(root / 'linux_theming/ui'), 'linux_theming/ui'),
           (str(root / 'bin/walltheme'), 'bin')] + notices,
    hiddenimports=['PIL.Image', 'PIL.ImageOps', 'PIL.ImageStat'],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineQuick',
              'PySide6.QtWebEngineWidgets', 'tkinter'],
)
# Mesa/GLX loads host drivers into this process. An older bundled C++ runtime
# can shadow the host's and lack symbols those drivers require (GLIBCXX_*).
# Qt and the graphics drivers must share the host's libstdc++.
analysis.binaries = [item for item in analysis.binaries
                     if Path(item[0]).name != 'libstdc++.so.6']
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
          name='linux-theming', console=True, strip=False, upx=False)
coll = COLLECT(exe, analysis.binaries, analysis.datas,
               strip=False, upx=False, name='linux-theming')
