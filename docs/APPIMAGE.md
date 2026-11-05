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

The host must provide `libstdc++.so.6` compatible with Qt 6.8 (GCC 10+).
We deliberately exclude this library from the bundle: a build runner's older
C++ runtime can prevent newer host Mesa/GLX drivers from loading, even when an
offscreen smoke test passes. Qt and host graphics drivers use the same host C++
runtime.
CI also installs the Qt X11 dependencies on the build runner so PyInstaller can
bundle them, and tests the AppImage through X11/OpenGL before publication.

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
# Exercise X11/OpenGL with the host's graphics drivers, also in temporary HOME/XDG.
# Requires an accessible X11 display; CI uses Xvfb and Mesa's software GL driver.
APPIMAGE_EXTRACT_AND_RUN=1 dist/DesktopTheming-x86_64.AppImage --smoke-test-x11
sha256sum dist/DesktopTheming-x86_64.AppImage
```

FUSE is needed for normal mounting. AppImage extract-and-run is the fallback.
Graphics drivers, fonts, the compositor and baseline system libraries remain host
responsibilities. Keep Qt libraries dynamically linked and retain dependency
license notices. See `packaging/THIRD_PARTY.md` for upstream licensing/source
references. Revalidate the QML hook and bundled dialogs when changing Qt versions.

### Release 0.1.0 startup failure on newer Mesa systems

The original 0.1.0 release bundles Ubuntu 22.04's `libstdc++`. On newer systems
this can produce `GLIBCXX_3.4.32 not found` while loading a host graphics driver,
followed by `Could not initialize GLX`. The file can have correct permissions and
a matching checksum and still fail to open. Local builds can work because they
bundle a newer runtime. The packaging fix above is included in 0.1.1 and later;
published 0.1.0 assets remain unchanged.

On x86_64 Arch/CachyOS, a temporary workaround for that original release is:

```sh
LD_PRELOAD=/usr/lib/libstdc++.so.6 ./DesktopTheming-x86_64.AppImage
```

This selects the installed system runtime for that invocation only. The path
varies on other distributions. Updated builds do not require this workaround.

Upstream references: [AppImage concepts](https://docs.appimage.org/introduction/concepts.html),
[compatibility practices](https://docs.appimage.org/reference/best-practices.html),
and [Qt deployment with PyInstaller](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html).

## GitHub Releases

The **AppImage** workflow still builds and smoke-tests artifacts on pushes and
pull requests. A manual dispatch on `main` additionally publishes a GitHub Release
with the tested AppImage and its SHA-256 file. No rebuild occurs during publication.
Only the publication job has repository write permission. Failed validation,
builds or smoke tests prevent publication.

To cut a release:

1. Update `desktop_theming.__version__` if necessary, run the required checks,
   and commit and push all completed changes to `main`.
2. Fetch GitHub's current `main` and launch:
   `gh workflow run appimage.yml --ref main -f version=0.1.1`
   (replace the version with the source version).
3. Wait for the workflow to finish. Verify the public release tag resolves to
   the built source commit, download both assets, check the SHA-256 and run
   `APPIMAGE_EXTRACT_AND_RUN=1 ./DesktopTheming-x86_64.AppImage --smoke-test`.
   With an accessible X11 display, also run `--smoke-test-x11` on the downloaded
   asset to verify host graphics initialization.
4. Report the public release URL and verification results.

The workflow rejects dispatches from other branches, version mismatches and
existing tags. It checks `main` before building and again before publishing;
if `main` advanced, dispatch again to build the new head. Published releases are
never overwritten; subsequent releases need a new source version. Publication
uses the exact tested commit, with no dependency on the caller's local checkout.
