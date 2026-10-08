import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

REPEAT_MODES = ("NONE", "ALL", "ONE")
LIKES = ("INDIFFERENT", "LIKE", "DISLIKE")


def _str(v, limit=400):
    return v[:limit] if isinstance(v, str) else ""


def _num(v, lo=0.0, hi=1e7, default=0.0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x:
        return default
    return max(lo, min(hi, x))


class Player(QObject):
    changed = pyqtSignal()
    trackChanged = pyqtSignal()
    metadataChanged = pyqtSignal()
    playingChanged = pyqtSignal(bool)
    seeked = pyqtSignal(float)
    userVolume = pyqtSignal(float)
    command = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_id = ""
        self.title = ""
        self.artist = ""
        self.album = ""
        self.art_url = ""
        self.duration = 0.0
        self.playing = False
        self.volume = 1.0
        self.muted = False
        self.repeat = "NONE"
        self.shuffle = False
        self.like = "INDIFFERENT"
        self.is_ad = False
        self.is_video = False
        self.can_next = True
        self.can_prev = True
        self.url = ""
        self.connected = False
        self.prev_end = (0.0, 0.0)
        self.last_cmd = ("", 0.0)
        self._pos = 0.0
        self._pos_ts = time.monotonic()
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(450)
        self._settle.timeout.connect(self._emit_track)

    @property
    def available(self):
        return bool(self.video_id)

    @property
    def display_title(self):
        return "Advertisement" if self.is_ad else self.title

    def position(self):
        p = self._pos
        if self.playing:
            p += time.monotonic() - self._pos_ts
        if self.duration > 0:
            p = min(p, self.duration)
        return max(0.0, p)

    def apply_position(self, pos, seeked=False):
        self._pos = _num(pos)
        self._pos_ts = time.monotonic()
        if seeked:
            self.seeked.emit(self._pos)

    def apply_state(self, s):
        if not isinstance(s, dict):
            return
        old = (
            self.video_id, self.title, self.artist, self.album, self.art_url,
            self.duration, self.playing, self.volume, self.muted, self.repeat,
            self.shuffle, self.like, self.is_ad, self.is_video, self.can_next, self.can_prev,
        )
        old_id, old_playing = self.video_id, self.playing
        if str(s.get("videoId") or "") != old_id and old_id:
            self.prev_end = (self.position(), self.duration)
        old_meta = (self.title, self.artist, self.album, self.art_url, self.duration)

        self.video_id = _str(s.get("videoId"), 40)
        self.title = _str(s.get("title"))
        self.artist = _str(s.get("artist"))
        self.album = _str(s.get("album"))
        self.art_url = _str(s.get("art"), 1000)
        self.duration = _num(s.get("duration"))
        self.playing = bool(s.get("playing"))
        self.volume = _num(s.get("volume"), 0.0, 1.0, self.volume)
        self.muted = bool(s.get("muted"))
        rep = s.get("repeat")
        self.repeat = rep if rep in REPEAT_MODES else "NONE"
        if isinstance(s.get("shuffle"), bool):
            self.shuffle = s["shuffle"]
        lk = s.get("like")
        self.like = lk if lk in LIKES else "INDIFFERENT"
        self.is_ad = bool(s.get("isAd"))
        self.is_video = bool(s.get("isVideo"))
        self.can_next = bool(s.get("canNext", True))
        self.can_prev = bool(s.get("canPrev", True))
        self.url = _str(s.get("url"), 600)
        if "pos" in s:
            self.apply_position(s["pos"])

        new = (
            self.video_id, self.title, self.artist, self.album, self.art_url,
            self.duration, self.playing, self.volume, self.muted, self.repeat,
            self.shuffle, self.like, self.is_ad, self.is_video, self.can_next, self.can_prev,
        )
        if new == old:
            return
        if self.video_id != old_id:
            if self.video_id:
                self._settle.start()
        elif (self.title, self.artist, self.album, self.art_url, self.duration) != old_meta:
            if self._settle.isActive():
                self._settle.start()
            else:
                self.metadataChanged.emit()
        if self.playing != old_playing:
            self.playingChanged.emit(self.playing)
        self.changed.emit()

    def _emit_track(self):
        self.trackChanged.emit()

    def _cmd(self, name, arg=None):
        self.last_cmd = (name, time.monotonic())
        self.command.emit(name, arg)

    def play(self):
        self._cmd("play")

    def pause(self):
        self._cmd("pause")

    def toggle(self):
        self._cmd("toggle")

    def stop(self):
        self._cmd("pause")
        self.seek(0)

    def next(self):
        self._cmd("next")

    def prev(self):
        self._cmd("prev")

    def seek(self, sec):
        sec = _num(sec, 0.0, self.duration or 1e7)
        self.apply_position(sec)
        self._cmd("seek", sec)
        self.changed.emit()

    def seek_by(self, delta):
        self.seek(self.position() + delta)

    def set_volume(self, v, persist=True):
        v = _num(v, 0.0, 1.0)
        self.volume = v
        if v > 0:
            self.muted = False
        self._cmd("volume", v)
        if persist:
            self.userVolume.emit(v)
        self.changed.emit()

    def volume_step(self, delta_pct):
        self.set_volume(self.volume + delta_pct / 100.0)

    def toggle_mute(self):
        self.muted = not self.muted
        self._cmd("mute", self.muted)
        self.changed.emit()

    def cycle_repeat(self):
        self.repeat = REPEAT_MODES[(REPEAT_MODES.index(self.repeat) + 1) % 3]
        self._cmd("repeat")
        self.changed.emit()

    def set_repeat(self, mode):
        if mode not in REPEAT_MODES:
            return
        for _ in range(3):
            if self.repeat == mode:
                break
            self.cycle_repeat()

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self._cmd("shuffle")
        self.changed.emit()

    def set_shuffle(self, on):
        if bool(on) != self.shuffle:
            self.toggle_shuffle()

    def toggle_like(self):
        self.like = "INDIFFERENT" if self.like == "LIKE" else "LIKE"
        self._cmd("like")
        self.changed.emit()

    def toggle_dislike(self):
        self.like = "INDIFFERENT" if self.like == "DISLIKE" else "DISLIKE"
        self._cmd("dislike")
        self.changed.emit()

    def status(self):
        return {
            "status": "Playing" if self.playing else ("Paused" if self.available else "Stopped"),
            "title": self.display_title,
            "artist": self.artist,
            "album": self.album,
            "video_id": self.video_id,
            "url": f"https://music.youtube.com/watch?v={self.video_id}" if self.video_id else "",
            "art_url": self.art_url,
            "position": round(self.position(), 2),
            "duration": round(self.duration, 2),
            "volume": round(self.volume, 3),
            "muted": self.muted,
            "repeat": self.repeat,
            "shuffle": self.shuffle,
            "like": self.like,
            "ad": self.is_ad,
        }
