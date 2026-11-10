"""Choose the Qt Quick renderer before the first window exists.

Qt Quick aborts the whole process when its OpenGL backend cannot create a
context (for example after a driver update without a reboot, when the loaded
kernel module and the GL libraries differ). Probing a context first lets the
window open with the software renderer instead.
"""

import os
import sys

# Any of these means the user or a diagnostic already chose the renderer.
EXPLICIT = ("QT_QUICK_BACKEND", "QSG_RHI_BACKEND")

NOTICE = ("OpenGL is not available ({reason}); using the software renderer. "
          "If the graphics driver was just updated, rebooting usually restores OpenGL.")


def explicit_choice(environment=None):
    environment = os.environ if environment is None else environment
    return any(environment.get(name) for name in EXPLICIT)


def opengl_available():
    from PySide6.QtGui import QOffscreenSurface, QOpenGLContext

    context = QOpenGLContext()
    if not context.create():
        return False, "cannot create a context"
    surface = QOffscreenSurface()
    surface.setFormat(context.format())
    surface.create()
    try:
        if not context.makeCurrent(surface):
            return False, "cannot activate a context"
        context.doneCurrent()
    finally:
        surface.destroy()
    return True, ""


def choose_renderer(app, environment=None):
    """Return "software" when Qt Quick must not use OpenGL, else None."""
    if explicit_choice(environment):
        return None
    if app.platformName() == "offscreen":
        return None
    available, reason = opengl_available()
    if available:
        return None
    from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
    print(NOTICE.format(reason=reason), file=sys.stderr)
    return "software"
