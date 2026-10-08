import os
from pathlib import Path

from . import APP_ID


def _xdg(env: str, default: str) -> Path:
    return Path(os.environ.get(env) or (Path.home() / default))


_override = os.environ.get("CADENCE_HOME")
if _override:
    _base = Path(_override)
    CONFIG = _base / "config"
    DATA = _base / "data"
    CACHE = _base / "cache"
else:
    CONFIG = _xdg("XDG_CONFIG_HOME", ".config") / APP_ID
    DATA = _xdg("XDG_DATA_HOME", ".local/share") / APP_ID
    CACHE = _xdg("XDG_CACHE_HOME", ".cache") / APP_ID

RUNTIME = (_base / "run") if _override else Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/{APP_ID}-{os.getuid()}") / APP_ID
WEBENGINE = DATA / "webengine"
ART_CACHE = CACHE / "art"
LYRICS_CACHE = CACHE / "lyrics"
LOG_FILE = CACHE / "cadence.log"
SETTINGS_FILE = CONFIG / "settings.json"
STATUS_FILE = RUNTIME / "now-playing.json"
COVER_FILE = RUNTIME / "cover.jpg"


def ensure_dirs() -> None:
    for p in (CONFIG, DATA, CACHE, WEBENGINE, ART_CACHE, LYRICS_CACHE, RUNTIME):
        p.mkdir(parents=True, exist_ok=True)
    for p in (CONFIG, RUNTIME):
        try:
            p.chmod(0o700)
        except OSError:
            pass
