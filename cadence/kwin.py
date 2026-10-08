"""KWin ignores stay-on-top hints from native Wayland surfaces, so pin windows through a KWin script."""
import json
import logging

from . import APP_ID, gdbus, paths
from .gdbus import GLib, Variant

log = logging.getLogger("cadence.kwin")

_TEMPLATE = """
const klass = %(klass)s;
const caption = %(caption)s;
const on = %(on)s;
workspace.windowList().forEach(function (w) {
  if (w.resourceClass === klass && w.caption.indexOf(caption) === 0) {
    w.keepAbove = on;
  }
});
"""


def set_keep_above(caption: str, on: bool) -> bool:
    name = "cadence-pin-" + caption.replace(" ", "-").lower()
    file = paths.RUNTIME / (name + ".js")
    try:
        paths.RUNTIME.mkdir(parents=True, exist_ok=True)
        file.write_text(_TEMPLATE % {
            "klass": json.dumps(APP_ID), "caption": json.dumps(caption), "on": "true" if on else "false"})
        conn = gdbus.session_bus()
        for method, args in (
            ("unloadScript", Variant("(s)", (name,))),
            ("loadScript", Variant("(ss)", (str(file), name))),
            ("start", None),
        ):
            try:
                conn.call_sync("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", method, args,
                               None, 0, 1500, None)
            except GLib.Error:
                if method != "unloadScript":
                    raise
        return True
    except (OSError, GLib.Error):
        log.debug("kwin pin failed", exc_info=True)
        return False
