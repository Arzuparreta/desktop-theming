#!/usr/bin/env bash
# Development build only. Never installs dependencies or touches desktop config.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON:-$repo/.venv/bin/python}"
appimage_tool="${APPIMAGETOOL:-}"
appimage_runtime="${APPIMAGE_RUNTIME:-}"
if [[ ! -x "$python_bin" ]]; then
    echo 'Create .venv and explicitly install requirements-build.txt first.' >&2
    exit 1
fi
if [[ ! -x "$appimage_tool" ]]; then
    echo 'Set APPIMAGETOOL to a verified appimagetool executable.' >&2
    exit 1
fi
if [[ ! -f "$appimage_runtime" ]]; then
    echo 'Set APPIMAGE_RUNTIME to a verified type2-runtime file.' >&2
    exit 1
fi
cd "$repo"
"$python_bin" -m PyInstaller --noconfirm --clean packaging/linux-theming.spec
appdir="$repo/build/LinuxTheming.AppDir"
# Only remove our generated directory, never a caller-supplied path.
rm -rf -- "$appdir"
mkdir -p "$appdir/usr"
cp -a dist/linux-theming "$appdir/usr/app"
install -m 644 packaging/linux-theming.desktop "$appdir/linux-theming.desktop"
# File managers and AppImage tools read .DirIcon, which the AppImage format
# expects to be a PNG. Ship it as a regular file, plus hicolor theme icons.
install -m 644 assets/icon.png "$appdir/linux-theming.png"
install -m 644 assets/icon.png "$appdir/.DirIcon"
install -D -m 644 assets/icon.png "$appdir/usr/share/icons/hicolor/256x256/apps/linux-theming.png"
install -D -m 644 linux_theming/ui/icon.svg "$appdir/usr/share/icons/hicolor/scalable/apps/linux-theming.svg"
cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
appdir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Keep the user's PATH and XDG roots: discovery must inspect the host, not the bundle.
# Qt is private to the frozen process; do not inherit another app's Qt plugins.
unset QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH QML2_IMPORT_PATH QML_IMPORT_PATH
exec "$appdir/usr/app/linux-theming" "$@"
EOF
chmod +x "$appdir/AppRun"
export ARCH="${ARCH:-$(uname -m)}"
export APPIMAGE_EXTRACT_AND_RUN=1
# Publish by rename so an already-running AppImage keeps its original inode.
artifact="$repo/dist/LinuxTheming-$ARCH.AppImage"
partial="$repo/dist/.LinuxTheming-$ARCH-$$.AppImage"
trap 'rm -f -- "$partial"' EXIT
"$appimage_tool" --runtime-file "$appimage_runtime" "$appdir" "$partial"
mv -f -- "$partial" "$artifact"
