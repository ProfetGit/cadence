"""Thin GDBus helpers. Qt's default Linux event dispatcher runs the GLib main context,
so Gio callbacks arrive on the Qt main thread with no extra loop plumbing."""
import logging

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

log = logging.getLogger("cadence.dbus")

Variant = GLib.Variant
Error = GLib.Error


class DBusFail(Exception):
    def __init__(self, name, message=""):
        super().__init__(message)
        self.name = name
        self.message = message


def session_bus():
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


class Exported:
    """Registers every interface in `xml` on one object path and routes to `handler`.

    handler.dbus_method(iface, name, args) -> GLib.Variant | None
    handler.dbus_get(iface, name) -> GLib.Variant
    handler.dbus_set(iface, name, value) -> bool
    """

    def __init__(self, conn, path, xml, handler):
        self.conn = conn
        self.path = path
        self.handler = handler
        self._ids = []
        self.last_sender = ""
        node = Gio.DBusNodeInfo.new_for_xml(xml)
        for iface in node.interfaces:
            self._ids.append(
                conn.register_object(path, iface, self._on_call, self._on_get, self._on_set)
            )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        self.last_sender = sender
        try:
            asyncer = getattr(self.handler, "dbus_async", None)
            if asyncer and asyncer(iface, method, params.unpack(), invocation):
                return
            result = self.handler.dbus_method(iface, method, params.unpack())
        except DBusFail as e:
            invocation.return_dbus_error(e.name, e.message or e.name)
            return
        except Exception as e:  # noqa: BLE001
            log.exception("dbus method %s.%s failed", iface, method)
            invocation.return_dbus_error("org.freedesktop.DBus.Error.Failed", str(e))
            return
        invocation.return_value(result)

    def _on_get(self, conn, sender, path, iface, prop):
        try:
            return self.handler.dbus_get(iface, prop)
        except Exception:  # noqa: BLE001
            log.exception("dbus get %s.%s failed", iface, prop)
            return None

    def _on_set(self, conn, sender, path, iface, prop, value):
        try:
            return bool(self.handler.dbus_set(iface, prop, value.unpack()))
        except Exception:  # noqa: BLE001
            log.exception("dbus set %s.%s failed", iface, prop)
            return False

    def emit_properties(self, iface, changed):
        if not changed:
            return
        self.conn.emit_signal(
            None, self.path, "org.freedesktop.DBus.Properties", "PropertiesChanged",
            Variant("(sa{sv}as)", (iface, changed, [])),
        )

    def emit(self, iface, name, args: Variant):
        self.conn.emit_signal(None, self.path, iface, name, args)

    def close(self):
        for i in self._ids:
            self.conn.unregister_object(i)
        self._ids = []


def own_name(conn, name, replace=False):
    flags = Gio.BusNameOwnerFlags.DO_NOT_QUEUE
    if replace:
        flags |= Gio.BusNameOwnerFlags.REPLACE
    return Gio.bus_own_name_on_connection(conn, name, flags, None, lambda *a: log.warning("lost bus name %s", name))


def call_sync(name, path, iface, method, args=None, timeout_ms=1500):
    conn = session_bus()
    return conn.call_sync(name, path, iface, method, args, None, Gio.DBusCallFlags.NONE, timeout_ms, None)
