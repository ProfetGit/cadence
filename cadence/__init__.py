import os as _os

__version__ = "1.0.0"
APP_NAME = "Cadence"
APP_ID = "cadence"
DESKTOP_ID = _os.environ.get("CADENCE_DESKTOP_ID", "cadence")
BUS_NAME = "org.cadence.Cadence" + _os.environ.get("CADENCE_BUS_SUFFIX", "")
BUS_PATH = "/org/cadence/Cadence"
YTM_HOME = "https://music.youtube.com/"
