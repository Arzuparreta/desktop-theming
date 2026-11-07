"""Isolated startup diagnostic. These are observations, not performance promises."""

import json
import time

from PySide6.QtCore import QTimer


def observe(app, window, controller, started):
    """Measure local milestones; the caller must first isolate HOME/XDG/PATH."""
    marks = {"window_created_ms": round((time.perf_counter() - started) * 1000, 1)}
    timer = QTimer(controller)
    timer.setInterval(5)

    def first_frame():
        marks.setdefault("first_frame_ms", round((time.perf_counter() - started) * 1000, 1))

    window.frameSwapped.connect(first_frame)

    def tick():
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        state = controller.state
        if state["palette"]:
            marks.setdefault("first_palette_ms", elapsed)
        if not state["scanning"] and state["overview"]["components"]:
            marks.setdefault("inventory_ms", elapsed)
        if "first_frame_ms" in marks and "first_palette_ms" in marks and not state["folderLoading"]:
            marks["usable_ms"] = elapsed
            marks["inventory_pending"] = state["scanning"]
            marks["scope"] = "isolated fixture; in-process milestones exclude interpreter and AppImage mount/extraction"
            print("DESKTOP_THEMING_TIMING " + json.dumps(marks, sort_keys=True), flush=True)
            timer.stop()
            app.exit(0)
        elif elapsed > 15000:
            print("DESKTOP_THEMING_TIMING " + json.dumps(dict(marks, error=state["error"] or "Startup diagnostic timed out")), flush=True)
            timer.stop()
            app.exit(1)

    timer.timeout.connect(tick)
    timer.start()
    return timer
