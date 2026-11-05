"""In-bundle diagnostic; never uses the caller's HOME, XDG roots or applications."""

import os
import tempfile
from pathlib import Path


def isolated_environment(*, x11=False):
    temporary = tempfile.TemporaryDirectory(prefix="desktop-theming-smoke-")
    root = Path(temporary.name)
    binaries = root / "bin"
    binaries.mkdir()
    kitty = binaries / "kitty"
    kitty.write_text("#!/bin/sh\nexit 0\n")
    kitty.chmod(0o700)
    os.environ.update(HOME=str(root), XDG_CONFIG_HOME=str(root / "config"),
                      XDG_DATA_HOME=str(root / "data"),
                      XDG_STATE_HOME=str(root / "state"), XDG_CACHE_HOME=str(root / "cache"),
                      XDG_RUNTIME_DIR=str(root / "runtime"), PATH=str(binaries),
                      QT_QPA_PLATFORM="xcb" if x11 else "offscreen",
                      QT_QUICK_BACKEND="rhi" if x11 else "software")
    if x11:
        os.environ["QSG_RHI_BACKEND"] = "opengl"
    (root / "runtime").mkdir(mode=0o700)
    original = root / "dotfiles/kitty.conf"
    original.parent.mkdir()
    original.write_text("font_size 16\nbackground #101010\n")
    config = root / "config/kitty/kitty.conf"
    config.parent.mkdir(parents=True)
    config.symlink_to(original)
    from PIL import Image

    images = root / "images #1"
    images.mkdir()
    for name in ("a #1.png", "b.JPG", "c.webp"):
        Image.new("RGB", (120, 80), "#95a78d").save(images / name)
    (images / "notes.txt").write_text("Not an image")
    return temporary


def exercise(app, engine, controller):
    from PySide6.QtCore import QMetaObject, QTimer, QUrl

    timer = QTimer(controller)
    timer.setInterval(50)
    state = {"step": 0, "ticks": 0}

    def tick():
        state["ticks"] += 1
        try:
            if state["ticks"] > 600:
                raise ValueError("Diagnostic timed out")
            s = controller.state
            if s["busy"] or controller.timer.isActive():
                return
            if s["error"]:
                raise ValueError(s["error"])
            step = state["step"]
            if step == 0:
                if not s["loaded"] or not s["palette"]:
                    raise ValueError("Initial preview is missing")
                if controller.paths.profile.exists() or controller.paths.state.exists():
                    raise ValueError("Discovery wrote local data")
                QMetaObject.invokeMethod(engine.rootObjects()[0], "openWallpaperPicker")
            elif step == 1:
                QMetaObject.invokeMethod(engine.rootObjects()[0], "closeWallpaperPicker")
                QMetaObject.invokeMethod(engine.rootObjects()[0], "openFolderPicker")
            elif step == 2:
                QMetaObject.invokeMethod(engine.rootObjects()[0], "closeFolderPicker")
                controller.chooseFolder(QUrl.fromLocalFile(str(controller.paths.home / "images #1")).toString())
            elif step == 3:
                images = controller.imageFolder["images"]
                if len(images) != 3 or engine.rootObjects()[0].property("folderImageCount") != 3:
                    raise ValueError("Folder image list is missing")
                if not s["profile"]["set_wallpaper"]:
                    raise ValueError("Wallpaper checkbox is not enabled by default")
                controller.chooseWallpaper(images[0]["fileUrl"])
            elif step == 4:
                if not s["profile"]["wallpaper"].endswith("a #1.png") or not s["palette"]:
                    raise ValueError("Folder image preview failed")
                if controller.paths.profile.exists() or controller.paths.state.exists():
                    raise ValueError("Image selection wrote profile or transaction data")
                if not (controller.paths.config / "desktop-theming/navigation.ini").exists():
                    raise ValueError("Navigation settings were not saved")
                controller.setWallpaperEnabled(False)
            elif step == 5:
                controller.selectComponent("kitty", True)
            elif step == 6:
                if not s["connection"].get("linked") or not s["connection"].get("existingColors"):
                    raise ValueError("Required connection decisions were not presented")
                if s["profile"]["components"] or controller.paths.profile.exists():
                    raise ValueError("Selection changed before consent")
                controller.confirmConnection(True, True)
            elif step == 7:
                controller.review()
            elif step == 8:
                if not s["review"]["changes"] or controller.paths.profile.exists():
                    raise ValueError("Review did not remain read-only")
                controller.approve()
            elif step == 9:
                if not controller.paths.profile.exists():
                    raise ValueError("Application did not create the profile")
                controller.reviewUndo(s["overview"]["history"][0]["id"], False)
            elif step == 10:
                controller.approve()
            elif step == 11:
                if controller.paths.profile.exists():
                    raise ValueError("Undo did not restore the previous state")
                if not (controller.paths.config / "kitty/kitty.conf").is_symlink():
                    raise ValueError("Undo did not restore the original link")
                if (controller.paths.home / "dotfiles/kitty.conf").read_text() != "font_size 16\nbackground #101010\n":
                    raise ValueError("The original linked file changed")
                controller.renderExport("ghostty")
            else:
                if "palette = 0=" not in s["exportText"]:
                    raise ValueError("Standalone export failed")
                if not engine.rootObjects():
                    raise ValueError("QML window is missing")
                print("PASS: QML, image/folder dialogs, thumbnails, guided connection, preview, review, apply, reviewed undo and export (isolated HOME/XDG).")
                timer.stop()
                app.exit(0)
                return
            state["step"] += 1
        except Exception as exc:
            import traceback

            traceback.print_exc()
            print(f"FAIL: {exc}")
            timer.stop()
            app.exit(1)

    timer.timeout.connect(tick)
    timer.start()
