"""Qt adapter. All engine work is serialized away from the GUI thread."""

import copy
import os
from pathlib import Path

from PySide6.QtCore import Property, QObject, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication

from . import changes, presentation, service, theme
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
                       "review": {}, "exportText": "", "exportComponent": "", "wallpaperUrl": "", "connection": {}, "problem": {}, "activity": ""}
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

    def start(self, operation, complete, *, clear_notice=True, context="refresh"):
        if self._state["busy"]:
            return
        self.timer.stop()
        self._context = context
        self.publish(busy=True, error="", problem={}, activity={
            "preview": "Building palette…", "review": "Checking changes…",
            "apply": "Applying reviewed changes…", "restore": "Checking restoration…",
            "export": "Saving theme…", "refresh": "Checking desktop…",
        }[context], **({"notice": ""} if clear_notice else {}))
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
            self.publish(error=error, problem=presentation.problem(self._context, error), review={})
        else:
            try:
                self._complete(result)
            except Exception as exc:
                self.publish(error=str(exc), problem=presentation.problem(self._context, str(exc)))
        self.changed.emit()

    @Slot()
    def refresh(self):
        draft = (copy.deepcopy(self._state["profile"]) if self._state["loaded"] and
                 self._state["profile"] != self._state["overview"].get("profile") else None)

        def complete(result):
            self._review = None
            self.publish(overview=result, profile=draft or copy.deepcopy(result["profile"]),
                         review={}, connection={}, loaded=True, exportText="", palette={},
                         notice="Desktop checked. Pending choices kept." if draft else "")
            self.timer.start()
        self.start(lambda: service.overview(self.paths), complete)

    def edit(self, profile):
        if self._state["busy"] or not self._state["loaded"]:
            return
        self._review = None
        self.publish(profile=service.validate_profile(profile), review={}, palette={},
                     exportText="", exportComponent="", error="", problem={}, notice="")
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
        if self._state["busy"] or not self._state["loaded"]:
            return
        if selected:
            def complete(info):
                if info["blocked"] or info["linked"] or info["existingColors"]:
                    self.publish(connection=dict(info, continueReview=False), review={})
                else:
                    self.select_ready(component)
            self.start(lambda: presentation.connection(self.paths, component), complete, context="review")
        else:
            profile = copy.deepcopy(self._state["profile"])
            profile["components"] = [c for c in profile["components"] if c != component]
            self.edit(profile)

    def select_ready(self, component):
        profile = copy.deepcopy(self._state["profile"])
        profile["components"] = sorted(set(profile["components"]) | {component})
        self.edit(profile)

    @Slot(bool, bool)
    def confirmConnection(self, local_copy, replace_colors):
        info = self._state["connection"]
        if (not info or self._state["busy"] or info["blocked"]
                or info["linked"] and not local_copy or info["existingColors"] and not replace_colors):
            return
        profile = copy.deepcopy(self._state["profile"])
        profile["components"] = sorted(set(profile["components"]) | {info["id"]})
        profile["resolutions"][info["id"]] = {
            "symlink": "detach" if info["linked"] and local_copy else "preserve",
            "replace_colors": info["existingColors"] and replace_colors,
        }
        self.publish(connection={})
        self.edit(profile)
        if info["continueReview"]:
            self.review()

    @Slot()
    def cancelConnection(self):
        if not self._state["busy"]:
            self.publish(connection={})
            if self._state["loaded"] and not self._state["palette"]:
                self.timer.start()

    @Slot()
    def preview(self):
        if not self._state["loaded"]:
            return
        profile = copy.deepcopy(self._state["profile"])
        self.start(lambda: theme.palette(profile), lambda result: self.publish(palette=result), clear_notice=False, context="preview")

    @Slot()
    def review(self):
        if not self._state["loaded"]:
            return
        profile = copy.deepcopy(self._state["profile"])

        def operation():
            for component in profile["components"]:
                info = presentation.connection(self.paths, component)
                if presentation.needs_decision(info, profile):
                    return {"connection": dict(info, continueReview=True)}
            previous = service.load_profile(self.paths)
            plan = service.make_plan(self.paths, profile)
            return {"plan": plan, "summary": presentation.review_summary(self.paths, plan, previous)}

        def complete(result):
            if "connection" in result:
                self._review = None
                self.publish(connection=result["connection"], review={})
                return
            plan = result["plan"]
            self._review = ("apply", plan)
            files = [dict(item, label=presentation.describe_file(self.paths, item)) for item in plan["changes"]]
            self.publish(review={"kind": "apply", "title": "Review changes", "summary": result["summary"],
                                 "changes": files, "warnings": plan["warnings"]}, palette=plan["palette"])
        self.start(operation, complete, context="review")

    @Slot(str, bool)
    def reviewUndo(self, ident, recover):
        def complete(plan):
            self._review = ("undo", plan)
            self.publish(review={"kind": "undo", "title": "Recover changes" if recover else "Undo changes",
                                 "changes": [dict(item, label=presentation.describe_file(self.paths, item)) for item in plan["changes"]],
                                 "summary": ["Restore the previous configuration shown below. Later edits are preserved."],
                                 "warnings": []})
        self.start(lambda: changes.review_undo(self.paths, ident, recover=recover), complete, context="restore")

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
        self.start(operation, complete, context="apply" if kind == "apply" else "restore")

    @Slot(str)
    def renderExport(self, component):
        if self._state["busy"]:
            return
        self.publish(exportText="", exportComponent="")
        profile = copy.deepcopy(self._state["profile"])
        def operation():
            value = theme.palette(profile)
            return value, theme.render(component, value)

        def complete(result):
            value, text = result
            self.publish(palette=value, exportText=text, exportComponent=component)
        self.start(operation, complete, context="preview")

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
        self.start(operation, lambda value: self.publish(notice=f"Theme saved to {value}"), context="export")
