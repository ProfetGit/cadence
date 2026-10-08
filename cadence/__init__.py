__version__ = "1.0.0"
APP_NAME = "Cadence"
APP_ID = "cadence"
import os as _os

BUS_NAME = "org.cadence.Cadence" + _os.environ.get("CADENCE_BUS_SUFFIX", "")
BUS_PATH = "/org/cadence/Cadence"
YTM_HOME = "https://music.youtube.com/"
