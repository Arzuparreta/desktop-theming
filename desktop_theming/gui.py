"""Qt adapter. All engine work is serialized away from the GUI thread."""

import copy
import os
from pathlib import Path

from PySide6.QtCore import Property, QObject, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication

from . import changes, service, theme
from .paths import Paths


class WorkSignals(QObject):
    finished = Signal(object, str)


class Work(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = WorkSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.operation(), "")
        except Exception as exc:
            self.signals.finished.emit(None, str(exc) or type(exc).__name__)


class Controller(QObject):
    changed = Signal()

    def __init__(self, paths=None):
        super().__init__()
        self.paths = paths or Paths.current()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._state = {"busy": False, "loaded": False, "error": "", "notice": "",
                       "overview": {"components": [], "history": [], "session": {}},
                       "profile": copy.deepcopy(service.DEFAULT_PROFILE), "palette": {},
                       "review": {}, "exportText": "", "wallpaperUrl": ""}
        self._review = None
        self._work = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self.preview)

    @Property("QVariantMap", notify=changed)
    def state(self):
        return self._state

    def publish(self, **values):
        if "profile" in values:
            image = values["profile"]["wallpaper"]
            values["wallpaperUrl"] = QUrl.fromLocalFile(image).toString() if image else ""
        self._state.update(values)
        self.changed.emit()

    def start(self, operation, complete, *, clear_notice=True):
        if self._state["busy"]:
            return
        self.timer.stop()
        self.publish(busy=True, error="", **({"notice": ""} if clear_notice else {}))
        self._work = Work(operation)
        self._complete = complete
        self._work.signals.finished.connect(self.finished)
        self.pool.start(self._work)

    @Slot(object, str)
    def finished(self, result, error):
        self._work = None
        self._state["busy"] = False
        if error:
            self._review = None
            self.publish(error=error, review={})
        else:
            try:
                self._complete(result)
            except Exception as exc:
                self.publish(error=str(exc))
        self.changed.emit()

    @Slot()
    def refresh(self):
        def complete(result):
            self._review = None
            self.publish(overview=result, profile=copy.deepcopy(result["profile"]),
                         review={}, loaded=True, exportText="", palette={})
            self.timer.start()
        self.start(lambda: service.overview(self.paths), complete)

    def edit(self, profile):
        if self._state["busy"] or not self._state["loaded"]:
            return
        self._review = None
        self.publish(profile=service.validate_profile(profile), review={}, palette={},
                     exportText="", error="", notice="")
        self.timer.start()

    @Slot(str, str)
    def setOption(self, key, value):
        if key not in ("mode", "polarity", "wallpaper"):
            return
        profile = copy.deepcopy(self._state["profile"])
        profile[key] = value
        self.edit(profile)

    @Slot(str)
    def chooseWallpaper(self, url):
        self.setOption("wallpaper", QUrl(url).toLocalFile())

    @Slot(str, bool)
    def selectComponent(self, component, selected):
        profile = copy.deepcopy(self._state["profile"])
        items = set(profile["components"])
        if selected:
            items.add(component)
        else:
            items.discard(component)
        profile["components"] = sorted(items)
        self.edit(profile)

    @Slot(str, str, bool)
    def resolve(self, component, option, enabled):
        profile = copy.deepcopy(self._state["profile"])
        resolution = profile["resolutions"].setdefault(component, {})
        if option == "replace_colors":
            resolution[option] = enabled
        elif option == "symlink":
            resolution[option] = "detach" if enabled else "preserve"
        self.edit(profile)

    @Slot()
    def preview(self):
        if not self._state["loaded"]:
            return
        profile = copy.deepcopy(self._state["profile"])
        self.start(lambda: theme.palette(profile), lambda result: self.publish(palette=result), clear_notice=False)

    @Slot()
    def review(self):
        profile = copy.deepcopy(self._state["profile"])

        def complete(plan):
            self._review = ("apply", plan)
            self.publish(review={"kind": "apply", "title": "Review changes",
                                 "changes": plan["changes"], "warnings": plan["warnings"]},
                         palette=plan["palette"])
        self.start(lambda: service.make_plan(self.paths, profile), complete)

    @Slot(str, bool)
    def reviewUndo(self, ident, recover):
        def complete(plan):
            self._review = ("undo", plan)
            self.publish(review={"kind": "undo", "title": "Recover changes" if recover else "Undo changes",
                                 "changes": plan["changes"],
                                 "warnings": ["Restore these files. Later edits are never overwritten."]})
        self.start(lambda: changes.review_undo(self.paths, ident, recover=recover), complete)

    @Slot()
    def cancelReview(self):
        if not self._state["busy"]:
            self._review = None
            self.publish(review={})

    @Slot()
    def approve(self):
        if self._review is None or self._state["busy"]:
            return
        kind, plan = self._review
        self._review = None  # Approval is consumed once, including on conflict.

        def operation():
            if kind == "apply":
                result = service.apply_reviewed(self.paths, plan)
            else:
                result = changes.undo(self.paths, plan["transaction"],
                                      recover=plan["recover"], reviewed=plan)
            return result, service.overview(self.paths)

        def complete(value):
            result, overview = value
            self.publish(overview=overview, profile=copy.deepcopy(overview["profile"]),
                         review={}, palette={}, exportText="",
                         notice=("Changes applied. Reopen your terminal or use its reload action."
                                 if result["status"] == "applied" else "Previous configuration restored."))
            # Keep the completion notice while regenerating the preview.
            self.timer.start()
        self.start(operation, complete)

    @Slot(str)
    def renderExport(self, component):
        profile = copy.deepcopy(self._state["profile"])
        self.start(lambda: theme.render(component, theme.palette(profile)),
                   lambda text: self.publish(exportText=text))

    @Slot(str)
    def copyText(self, text):
        QGuiApplication.clipboard().setText(text)

    @Slot(str)
    def saveExport(self, url):
        text = self._state["exportText"]
        if not text or self._state["busy"]:
            return
        path = Path(QUrl(url).toLocalFile())

        def operation():
            # Export creates a new standalone file; never overwrites a config or link.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(text)
            return str(path)
        self.start(operation, lambda value: self.publish(notice=f"Theme saved to {value}"))
