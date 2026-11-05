"""Launch the local desktop control center."""

import sys
from pathlib import Path


def main():
    graphics_diagnostic = "--smoke-test-x11" in sys.argv[1:]
    diagnostic = "--smoke-test" in sys.argv[1:] or graphics_diagnostic
    temporary = None
    if diagnostic:
        from .smoke import isolated_environment

        temporary = isolated_environment(x11=graphics_diagnostic)

    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuickControls2 import QQuickStyle
    except ImportError:
        raise SystemExit("The GUI needs PySide6. Use the AppImage or install the documented GUI dependencies.") from None

    from .gui import Controller

    QQuickStyle.setStyle("Basic")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Desktop Theming")
    app.setOrganizationName("desktop-theming")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui/icon.svg")))
    controller = Controller()
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"controller": controller})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "ui/Main.qml")))
    if not engine.rootObjects():
        return 1
    controller.refresh()
    if diagnostic:
        from .smoke import exercise

        exercise(app, engine, controller)
    result = app.exec()
    controller.pool.waitForDone()
    from shiboken6 import delete

    delete(engine)
    if temporary is not None:
        temporary.cleanup()
    return result


if __name__ == "__main__":
    sys.exit(main())
