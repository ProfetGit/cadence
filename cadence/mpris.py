import logging
import os
import re

from PyQt6.QtCore import QObject, QTimer

from . import APP_ID, APP_NAME, DESKTOP_ID, gdbus
from .gdbus import Variant
from .player import Player

log = logging.getLogger("cadence.mpris")

MPRIS_NAME = "org.mpris.MediaPlayer2." + os.environ.get("CADENCE_MPRIS_ID", APP_ID)
MPRIS_PATH = "/org/mpris/MediaPlayer2"
ROOT = "org.mpris.MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"

XML = """
<node>
 <interface name="org.mpris.MediaPlayer2">
  <method name="Raise"/>
  <method name="Quit"/>
  <property name="CanQuit" type="b" access="read"/>
  <property name="CanRaise" type="b" access="read"/>
  <property name="HasTrackList" type="b" access="read"/>
  <property name="Identity" type="s" access="read"/>
  <property name="DesktopEntry" type="s" access="read"/>
  <property name="SupportedUriSchemes" type="as" access="read"/>
  <property name="SupportedMimeTypes" type="as" access="read"/>
 </interface>
 <interface name="org.mpris.MediaPlayer2.Player">
  <method name="Next"/>
  <method name="Previous"/>
  <method name="Pause"/>
  <method name="PlayPause"/>
  <method name="Stop"/>
  <method name="Play"/>
  <method name="Seek"><arg name="Offset" type="x" direction="in"/></method>
  <method name="SetPosition">
   <arg name="TrackId" type="o" direction="in"/>
   <arg name="Position" type="x" direction="in"/>
  </method>
  <method name="OpenUri"><arg name="Uri" type="s" direction="in"/></method>
  <signal name="Seeked"><arg name="Position" type="x"/></signal>
  <property name="PlaybackStatus" type="s" access="read"/>
  <property name="LoopStatus" type="s" access="readwrite"/>
  <property name="Rate" type="d" access="readwrite"/>
  <property name="Shuffle" type="b" access="readwrite"/>
  <property name="Metadata" type="a{sv}" access="read"/>
  <property name="Volume" type="d" access="readwrite"/>
  <property name="Position" type="x" access="read"/>
  <property name="MinimumRate" type="d" access="read"/>
  <property name="MaximumRate" type="d" access="read"/>
  <property name="CanGoNext" type="b" access="read"/>
  <property name="CanGoPrevious" type="b" access="read"/>
  <property name="CanPlay" type="b" access="read"/>
  <property name="CanPause" type="b" access="read"/>
  <property name="CanSeek" type="b" access="read"/>
  <property name="CanControl" type="b" access="read"/>
 </interface>
</node>
"""

LOOP_OUT = {"NONE": "None", "ALL": "Playlist", "ONE": "Track"}
LOOP_IN = {v: k for k, v in LOOP_OUT.items()}
NO_TRACK = "/org/mpris/MediaPlayer2/TrackList/NoTrack"


def track_path(video_id: str) -> str:
    return "/org/cadence/track/" + (re.sub(r"[^A-Za-z0-9_]", "_", video_id) or "none")


class Mpris(QObject):
    def __init__(self, player: Player, on_raise, on_quit, on_open_uri, parent=None):
        super().__init__(parent)
        self.player = player
        self._raise, self._quit, self._open_uri = on_raise, on_quit, on_open_uri
        self.art_url = ""
        self._art_for = ""
        self._last = {}
        self._obj = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._flush)

    def start(self):
        conn = gdbus.session_bus()
        self._conn = conn
        self._obj = gdbus.Exported(conn, MPRIS_PATH, XML, self)
        self._name = gdbus.own_name(conn, MPRIS_NAME)
        self._last = self._snapshot()
        self.player.changed.connect(self._schedule)
        self.player.seeked.connect(self._on_seeked)

    def set_art(self, video_id: str, file_path: str):
        self._art_for = video_id
        self.art_url = "file://" + file_path if file_path else ""
        self._schedule()

    def _schedule(self):
        if not self._timer.isActive():
            self._timer.start()

    def _on_seeked(self, pos):
        if self._obj:
            self._obj.emit(PLAYER, "Seeked", Variant("(x)", (int(pos * 1e6),)))

    def _metadata(self):
        p = self.player
        if not p.available:
            return {"mpris:trackid": Variant("o", NO_TRACK)}
        md = {
            "mpris:trackid": Variant("o", track_path(p.video_id)),
            "mpris:length": Variant("x", int(p.duration * 1e6)),
            "xesam:title": Variant("s", p.display_title),
            "xesam:artist": Variant("as", [p.artist] if p.artist else []),
            "xesam:album": Variant("s", p.album),
            "xesam:url": Variant("s", "https://music.youtube.com/watch?v=" + p.video_id),
        }
        if self.art_url and self._art_for in (p.video_id, ""):
            md["mpris:artUrl"] = Variant("s", self.art_url)
        elif p.art_url.startswith("https://"):
            md["mpris:artUrl"] = Variant("s", p.art_url)
        if p.like == "LIKE":
            md["xesam:userRating"] = Variant("d", 1.0)
        elif p.like == "DISLIKE":
            md["xesam:userRating"] = Variant("d", 0.0)
        return md

    def _props(self):
        p = self.player
        return {
            "PlaybackStatus": Variant("s", "Playing" if p.playing else ("Paused" if p.available else "Stopped")),
            "LoopStatus": Variant("s", LOOP_OUT.get(p.repeat, "None")),
            "Shuffle": Variant("b", bool(p.shuffle)),
            "Metadata": Variant("a{sv}", self._metadata()),
            "Volume": Variant("d", 0.0 if p.muted else float(p.volume)),
            "CanGoNext": Variant("b", p.available and p.can_next),
            "CanGoPrevious": Variant("b", p.available and p.can_prev),
            "CanPlay": Variant("b", p.available),
            "CanPause": Variant("b", p.available),
            "CanSeek": Variant("b", p.available and p.duration > 0 and not p.is_ad),
        }

    def _snapshot(self):
        return {k: v.unpack() if k != "Metadata" else repr(sorted(v.unpack().items(), key=lambda kv: kv[0]))
                for k, v in self._props().items()}

    def _flush(self):
        if not self._obj:
            return
        props = self._props()
        snap = {k: v.unpack() if k != "Metadata" else repr(sorted(v.unpack().items(), key=lambda kv: kv[0]))
                for k, v in props.items()}
        changed = {k: props[k] for k in props if snap[k] != self._last.get(k)}
        self._last = snap
        self._obj.emit_properties(PLAYER, changed)

    def dbus_method(self, iface, name, args):
        p = self.player
        if iface == PLAYER and name != "OpenUri":
            log.info("MPRIS %s from %s", name, self._obj.last_sender if self._obj else "?")
        if iface == ROOT:
            if name == "Raise":
                self._raise()
            elif name == "Quit":
                self._quit()
            return None
        if name == "Next":
            p.next()
        elif name == "Previous":
            p.prev()
        elif name == "Pause":
            p.pause()
        elif name == "Play":
            p.play()
        elif name == "PlayPause":
            p.toggle()
        elif name == "Stop":
            p.stop()
        elif name == "Seek":
            p.seek_by(args[0] / 1e6)
        elif name == "SetPosition":
            if args[0] == track_path(p.video_id):
                p.seek(args[1] / 1e6)
        elif name == "OpenUri":
            self._open_uri(args[0])
        return None

    def dbus_get(self, iface, prop):
        if iface == ROOT:
            return {
                "CanQuit": Variant("b", True),
                "CanRaise": Variant("b", True),
                "HasTrackList": Variant("b", False),
                "Identity": Variant("s", APP_NAME),
                "DesktopEntry": Variant("s", DESKTOP_ID),
                "SupportedUriSchemes": Variant("as", ["https"]),
                "SupportedMimeTypes": Variant("as", []),
            }[prop]
        p = self.player
        if prop == "Position":
            return Variant("x", int(p.position() * 1e6))
        if prop == "Rate" or prop == "MinimumRate" or prop == "MaximumRate":
            return Variant("d", 1.0)
        if prop == "CanControl":
            return Variant("b", True)
        return self._props()[prop]

    def dbus_set(self, iface, prop, value):
        p = self.player
        if prop == "LoopStatus":
            p.set_repeat(LOOP_IN.get(value, "NONE"))
        elif prop == "Shuffle":
            p.set_shuffle(bool(value))
        elif prop == "Volume":
            p.set_volume(float(value))
        elif prop == "Rate":
            pass
        else:
            return False
        return True
