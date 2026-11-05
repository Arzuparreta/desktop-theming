"""In-bundle diagnostic; never uses the caller's HOME, XDG roots or applications."""

import os
import tempfile
from pathlib import Path


def isolated_environment():
    temporary = tempfile.TemporaryDirectory(prefix="desktop-theming-smoke-")
    root = Path(temporary.name)
    binaries = root / "bin"
    binaries.mkdir()
    kitty = binaries / "kitty"
    kitty.write_text("#!/bin/sh\nexit 0\n")
    kitty.chmod(0o700)
    os.environ.update(HOME=str(root), XDG_CONFIG_HOME=str(root / "config"),
                      XDG_STATE_HOME=str(root / "state"), XDG_CACHE_HOME=str(root / "cache"),
                      XDG_RUNTIME_DIR=str(root / "runtime"), PATH=str(binaries),
                      QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
    (root / "runtime").mkdir(mode=0o700)
    return temporary


def exercise(app, engine, controller):
    from PySide6.QtCore import QMetaObject, QTimer

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
                if controller.paths.config.exists() or controller.paths.state.exists():
                    raise ValueError("Discovery wrote local data")
                QMetaObject.invokeMethod(engine.rootObjects()[0], "openWallpaperPicker")
            elif step == 1:
                QMetaObject.invokeMethod(engine.rootObjects()[0], "closeWallpaperPicker")
                controller.selectComponent("kitty", True)
            elif step == 2:
                controller.review()
            elif step == 3:
                if not s["review"]["changes"] or controller.paths.profile.exists():
                    raise ValueError("Review did not remain read-only")
                controller.approve()
            elif step == 4:
                if not controller.paths.profile.exists():
                    raise ValueError("Application did not create the profile")
                controller.reviewUndo(s["overview"]["history"][0]["id"], False)
            elif step == 5:
                controller.approve()
            elif step == 6:
                if controller.paths.profile.exists():
                    raise ValueError("Undo did not restore the previous state")
                controller.renderExport("ghostty")
            else:
                if "palette = 0=" not in s["exportText"]:
                    raise ValueError("Standalone export failed")
                if not engine.rootObjects():
                    raise ValueError("QML window is missing")
                print("PASS: QML, preview, review, apply, reviewed undo and export (isolated HOME/XDG).")
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
