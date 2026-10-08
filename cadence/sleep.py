import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .player import Player

FADE_SECONDS = 12.0


class SleepTimer(QObject):
    changed = pyqtSignal()

    def __init__(self, player: Player, parent=None):
        super().__init__(parent)
        self.p = player
        self._deadline = None
        self._end_of_track = False
        self._base_volume = 1.0
        self._fading = False
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)

    @property
    def active(self):
        return self._deadline is not None or self._end_of_track

    def remaining(self):
        if self._deadline is None:
            return None
        return max(0.0, self._deadline - time.monotonic())

    def describe(self):
        if self._end_of_track:
            return "End of track"
        r = self.remaining()
        if r is None:
            return "Off"
        m, s = divmod(int(r), 60)
        return "%d:%02d left" % (m, s)

    def start(self, minutes):
        self.cancel(quiet=True)
        self._deadline = time.monotonic() + minutes * 60
        self._timer.start()
        self.changed.emit()

    def start_end_of_track(self):
        self.cancel(quiet=True)
        self._end_of_track = True
        self._timer.start()
        self.changed.emit()

    def cancel(self, quiet=False):
        if self._fading:
            self.p.set_volume(self._base_volume, persist=False)
        self._fading = False
        self._deadline = None
        self._end_of_track = False
        self._timer.stop()
        if not quiet:
            self.changed.emit()

    def _tick(self):
        if self._end_of_track:
            d = self.p.duration
            if self.p.playing and d > 0 and d - self.p.position() < 0.8:
                self.p.pause()
                self.cancel()
            return
        rem = self.remaining()
        if rem is None:
            return
        if rem <= FADE_SECONDS and self.p.playing:
            if not self._fading:
                self._fading = True
                self._base_volume = self.p.volume
            self.p.set_volume(self._base_volume * rem / FADE_SECONDS, persist=False)
        if rem <= 0:
            self.p.pause()
            base = self._base_volume
            was_fading = self._fading
            self._fading = False
            self.cancel()
            if was_fading:
                QTimer.singleShot(1200, lambda: self.p.set_volume(base, persist=False))
        else:
            self.changed.emit() if int(rem * 4) % 4 == 0 else None
