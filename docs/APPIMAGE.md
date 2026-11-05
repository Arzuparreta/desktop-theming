# AppImage packaging

AppImage fits this local control center: the payload contains Python, the engine,
Pillow, PySide6, Qt libraries/QML modules and platform plugins. It uses the host's
PATH and HOME/XDG directories without a broker or sandbox. Opening it only reads
configuration; changes still require review and approval in the GUI.

AppImage is a distribution container, not a universal Linux ABI. Build on the
oldest supported base and test the result on each intended distribution. The CI
build uses Ubuntu 22.04 and Python 3.11, targeting x86_64 Linux with glibc 2.35+;
this is a build target, not a claim that every distribution has been verified.
Local builds inherit their build host's minimum library requirements. musl-based
systems and other architectures are not covered by this build.

## Build

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt
APPIMAGETOOL=/absolute/path/to/verified/appimagetool \
APPIMAGE_RUNTIME=/absolute/path/to/verified/runtime-x86_64 \
scripts/build-appimage.sh
```

The script requires an explicitly supplied tool and type-2 runtime and never downloads or installs
anything. CI downloads appimagetool 1.9.1 and checks its SHA-256 before executing
it, and pins the runtime by SHA-256 as well. See `.github/workflows/appimage.yml` for the exact asset and digest. Builds
write only to this checkout's ignored `build/` and `dist/` directories. The final
AppImage is published by rename so running copies retain their original payload.

PyInstaller builds a relocatable **one-directory** payload. Appimagetool wraps
that directory once, avoiding a second self-extracting Python archive. The custom
QtQml hook includes the modules used by the application and file dialogs with the
Basic style. It excludes unused WebEngine, 3D and other style modules before
binary dependency analysis. X11 and Wayland plugins remain included. Resources
are loaded relative to the bundled module, not a source checkout or `/usr`.
The palette resource `bin/walltheme` is included for its pure palette functions;
its legacy application entry point and apply hooks are never invoked.

```sh
# This diagnostic always uses a fresh temporary HOME/XDG, including in the bundle.
APPIMAGE_EXTRACT_AND_RUN=1 dist/DesktopTheming-x86_64.AppImage --smoke-test
sha256sum dist/DesktopTheming-x86_64.AppImage
```

FUSE is needed for normal mounting. AppImage extract-and-run is the fallback.
Graphics drivers, fonts, the compositor and baseline system libraries remain host
responsibilities. Keep Qt libraries dynamically linked and retain dependency
license notices. See `packaging/THIRD_PARTY.md` for upstream licensing/source
references. Revalidate the QML hook and bundled dialogs when changing Qt versions.

Upstream references: [AppImage concepts](https://docs.appimage.org/introduction/concepts.html),
[compatibility practices](https://docs.appimage.org/reference/best-practices.html),
and [Qt deployment with PyInstaller](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html).
