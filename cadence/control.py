import json
import logging

from . import BUS_NAME, BUS_PATH, gdbus
from .gdbus import DBusFail, Variant

log = logging.getLogger("cadence.control")
IFACE = "org.cadence.Cadence"

XML = """
<node>
 <interface name="org.cadence.Cadence">
  <method name="Activate"/>
  <method name="Command">
   <arg type="s" name="name" direction="in"/>
   <arg type="s" name="arg" direction="in"/>
   <arg type="s" name="result" direction="out"/>
  </method>
  <method name="Status"><arg type="s" name="json" direction="out"/></method>
  <method name="Open"><arg type="s" name="url" direction="in"/></method>
  <method name="Eval">
   <arg type="s" name="js" direction="in"/>
   <arg type="s" name="result" direction="out"/>
  </method>
  <method name="Screenshot">
   <arg type="s" name="path" direction="in"/>
   <arg type="b" name="ok" direction="out"/>
  </method>
 </interface>
</node>
"""


class ControlService:
    """Session-bus control surface: single-instance activation, the `cadence ctl` CLI, scripts."""

    def __init__(self, app):
        self.app = app
        self._obj = None

    def start(self):
        conn = gdbus.session_bus()
        self._obj = gdbus.Exported(conn, BUS_PATH, XML, self)
        self._name = gdbus.own_name(conn, BUS_NAME)

    def dbus_async(self, iface, name, args, invocation):
        if name == "Eval":
            if not self.app.debug:
                raise DBusFail("org.cadence.Error.Disabled", "start with --debug to enable Eval")
            self.app.bridge.eval(
                args[0], lambda r: invocation.return_value(Variant("(s)", (json.dumps(r, default=str),)))
            )
            return True
        if name == "Screenshot":
            if not self.app.debug:
                raise DBusFail("org.cadence.Error.Disabled", "start with --debug to enable Screenshot")
            target = args[0]
            widget = self.app.window
            if target.startswith("mini:"):
                widget, target = self.app.mini, target[5:]
            elif target.startswith("lyrics:"):
                widget, target = self.app.window.lyrics, target[7:]
            elif target.startswith("settings:"):
                self.app.open_settings()
                widget, target = self.app._settings_dialog, target[9:]
            ok = widget.grab().save(target)
            invocation.return_value(Variant("(b)", (bool(ok),)))
            return True
        return False

    def dbus_method(self, iface, name, args):
        if name == "Activate":
            self.app.show_window()
        elif name == "Command":
            return Variant("(s)", (self.app.handle_command(args[0], args[1]),))
        elif name == "Status":
            return Variant("(s)", (json.dumps(self.app.player.status()),))
        elif name == "Open":
            self.app.open_url(args[0])
        return None

    def dbus_get(self, iface, prop):
        raise KeyError(prop)

    def dbus_set(self, iface, prop, value):
        return False
