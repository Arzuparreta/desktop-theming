"""Launch the local desktop control center."""

import sys
import time
from pathlib import Path

USAGE = """Usage: linux-theming [--quick | --center]

  --quick    open the compact daily view
  --center   open the full control center
  --measure-startup  print timing milestones in an isolated diagnostic fixture
  --version  print the source version

Without either option, the daily view opens once a theme has been applied and the
control center opens on first use. Starting it again in the same session brings
the running window forward (with the requested view) instead of opening another.
"""


def launch_intent(arguments):
    quick, center = "--quick" in arguments, "--center" in arguments
    if quick and center:
        raise SystemExit("Choose either --quick or --center, not both.")
    return "quick" if quick else "center" if center else "show"


def daily_mode(intent, paths):
    if intent != "show":
        return intent == "quick"
    try:
        return paths.profile.exists()  # Returning users start with the daily view.
    except OSError:
        return False


def activated(root, controller, request, notice, token):
    from .instance import activate

    activate(root, request, token)
    if notice:
        controller.publish(notice=notice)


def main():
    arguments = sys.argv[1:]
    if "--version" in arguments:
        from . import __version__

        print(__version__)
        return 0
    if "--help" in arguments or "-h" in arguments:
        print(USAGE, end="")
        return 0
    if '--smoke-test-wallpaper' in arguments or '--smoke-test-feh' in arguments:
        from .smoke_wallpaper import run

        return run(decoder_only='--smoke-test-wallpaper' not in arguments)
    intent = launch_intent(arguments)
    graphics_diagnostic = "--smoke-test-x11" in arguments
    measuring = "--measure-startup" in arguments
    diagnostic = "--smoke-test" in arguments or graphics_diagnostic or measuring
    temporary = None
    if diagnostic:
        from .smoke import isolated_environment

        temporary = isolated_environment(x11=graphics_diagnostic)

    started = time.perf_counter()

    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuickControls2 import QQuickStyle
    except ImportError:
        raise SystemExit("The GUI needs PySide6. Use the AppImage or install the documented GUI dependencies.") from None

    from . import instance
    from .gui import Controller
    from .paths import Paths

    claimed = None
    if not diagnostic:
        # Before any window exists: a second launch only hands over navigation.
        claimed = instance.claim(Paths.current(), intent)
        if claimed.role == "forwarded":
            if claimed.message:
                print(claimed.message)
            return 0
        if claimed.role == "unresponsive":
            print(claimed.message, file=sys.stderr)
            return 1
        if claimed.role == "standalone" and claimed.message:
            print(claimed.message, file=sys.stderr)

    QQuickStyle.setStyle("Basic")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Linux Theming")
    app.setOrganizationName("linux-theming")
    # Wayland app_id / desktop matching for the registered menu entry.
    app.setDesktopFileName("linux-theming")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui/icon.svg")))
    from .graphics import choose_renderer

    choose_renderer(app)  # Before any QML window: a failed OpenGL backend aborts Qt.
    server = None
    if claimed is not None and claimed.role == "primary":
        server = instance.server_class()(claimed, app)
        if not server.listen():
            print("Could not open the single-instance endpoint; another launch will open "
                  "its own window.", file=sys.stderr)
            server.close()
            server = None
    controller = Controller()
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"controller": controller,
                                 "dailyMode": daily_mode(intent, controller.paths)})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "ui/Main.qml")))
    if not engine.rootObjects():
        if server is not None:
            server.close()
        return 1
    root = engine.rootObjects()[0]
    if server is not None:
        server.requested.connect(lambda request, notice, token:
                                 activated(root, controller, request, notice, token))
    if diagnostic and not measuring:
        from . import launcher

        try:
            print(launcher.exercise())
            print(instance.exercise(app))
        except Exception as exc:
            import traceback

            traceback.print_exc()
            print(f"FAIL: {exc}")
            return 1
    if measuring:
        from .timing import observe

        observe(app, root, controller, started)
    getattr(controller, "startup", controller.refresh)()
    if diagnostic and not measuring:
        from .smoke import exercise

        exercise(app, engine, controller)
    result = app.exec()
    if server is not None:
        server.close()
    shutdown = getattr(controller, "shutdown", None)
    if shutdown is not None:
        shutdown()  # Waits for every worker pool before QML objects are deleted.
    else:
        for name in ("pool", "preview_pool", "read_pool"):
            pool = getattr(controller, name, None)
            if pool is not None:
                pool.waitForDone()
    from shiboken6 import delete

    delete(engine)
    if temporary is not None:
        temporary.cleanup()
    return result


if __name__ == "__main__":
    sys.exit(main())
