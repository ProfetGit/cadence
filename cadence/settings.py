import json
import os
import tempfile

from PyQt6.QtCore import QObject, pyqtSignal

from . import paths

DEFAULTS = {
    "close_to_tray": True,
    "start_hidden": False,
    "autostart": False,
    "notifications": True,
    "notify_only_unfocused": True,
    "restore_last": True,
    "resume_playing": False,
    "native_bar": True,
    "custom_titlebar": True,
    "hide_web_logo": True,
    "auto_accent": True,
    "zoom": 1.0,
    "lyrics_enabled": True,
    "lyrics_panel": False,
    "mini_lyrics": False,
    "scrobble": True,
    "listenbrainz_token": "",
    "mpris": True,
    "status_file": True,
    "volume_step": 5,
    "volume": -1.0,
    "mini_pinned": True,
    "mini_opacity": 0.96,
    "last_url": "",
    "geometry": "",
    "mini_geometry": "",
    "debug": False,
}


class Settings(QObject):
    changed = pyqtSignal(str)

    def __init__(self, path=None):
        super().__init__()
        self._path = path or paths.SETTINGS_FILE
        self._data = dict(DEFAULTS)
        self._load()

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        for k, v in raw.items():
            if k not in DEFAULTS:
                continue
            d = DEFAULTS[k]
            if isinstance(d, bool):
                ok = isinstance(v, bool)
            elif isinstance(d, float):
                ok = isinstance(v, (int, float)) and not isinstance(v, bool)
            elif isinstance(d, int):
                ok = isinstance(v, int) and not isinstance(v, bool)
            else:
                ok = isinstance(v, str)
            if ok:
                self._data[k] = float(v) if isinstance(d, float) else v

    def get(self, key):
        return self._data[key]

    __getitem__ = get

    def set(self, key, value):
        if key not in DEFAULTS:
            raise KeyError(key)
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self.changed.emit(key)
        self.save()

    __setitem__ = set

    def save(self):
        try:
            paths.CONFIG.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(paths.CONFIG), prefix=".settings-")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, sort_keys=True)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        except OSError:
            pass
