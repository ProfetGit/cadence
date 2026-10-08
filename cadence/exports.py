import json
import os
import time

from PyQt6.QtCore import QObject, QTimer

from . import paths
from .player import Player
from .settings import Settings


class StatusExporter(QObject):
    """Writes now-playing.json (+ cover.jpg via ArtCache) in $XDG_RUNTIME_DIR/cadence for
    widgets, bars and scripts: eww, conky, waybar-style polling, Plasma command widgets."""

    def __init__(self, player: Player, settings: Settings, parent=None):
        super().__init__(parent)
        self.p = player
        self.s = settings
        self.cover_path = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.write)
        player.changed.connect(self._schedule)
        player.seeked.connect(lambda _: self._schedule())

    def set_cover(self, path):
        self.cover_path = path
        self._schedule()

    def _schedule(self):
        if self.s["status_file"] and not self._timer.isActive():
            self._timer.start()

    def write(self):
        if not self.s["status_file"]:
            return
        d = self.p.status()
        d["cover"] = str(paths.COVER_FILE) if self.cover_path else ""
        d["updated"] = int(time.time())
        try:
            paths.RUNTIME.mkdir(parents=True, exist_ok=True)
            tmp = paths.STATUS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False))
            os.replace(tmp, paths.STATUS_FILE)
        except OSError:
            pass

    def clear(self):
        for f in (paths.STATUS_FILE, paths.COVER_FILE):
            try:
                f.unlink()
            except OSError:
                pass
