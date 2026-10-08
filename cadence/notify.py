import logging

from PyQt6.QtCore import QObject

from . import APP_ID, APP_NAME, gdbus
from .gdbus import Gio, GLib, Variant

log = logging.getLogger("cadence.notify")

NAME = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"


class Notifier(QObject):
    def __init__(self, on_action, parent=None):
        super().__init__(parent)
        self._on_action = on_action
        self._last_id = 0
        self._conn = None
        self._sub = None

    def _bus(self):
        if self._conn is None:
            self._conn = gdbus.session_bus()
            self._sub = self._conn.signal_subscribe(
                NAME, NAME, "ActionInvoked", PATH, None, Gio.DBusSignalFlags.NONE, self._action_cb
            )
        return self._conn

    def _action_cb(self, conn, sender, path, iface, signal, params):
        nid, key = params.unpack()
        if nid == self._last_id:
            self._on_action(key)

    def track(self, title, artist, album, image_path=""):
        body = artist if not album else "%s — %s" % (artist, album)
        log.info("notification: %s / %s", title, body)
        hints = {
            "desktop-entry": Variant("s", APP_ID),
            "transient": Variant("b", True),
            "urgency": Variant("y", 0),
            "category": Variant("s", "x-kde.music"),
        }
        if image_path:
            hints["image-path"] = Variant("s", image_path)
        args = Variant(
            "(susssasa{sv}i)",
            (APP_NAME, self._last_id, APP_ID, title, body, ["prev", "Previous", "next", "Next"], hints, 4000),
        )
        try:
            self._bus().call(
                NAME, PATH, NAME, "Notify", args, GLib.VariantType("(u)"),
                Gio.DBusCallFlags.NONE, 1500, None, self._done,
            )
        except GLib.Error:
            log.debug("notify failed", exc_info=True)

    def _done(self, src, res):
        try:
            self._last_id = src.call_finish(res).unpack()[0]
        except GLib.Error:
            log.debug("notify call failed", exc_info=True)
