from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..player import Player
from .widgets import ArtLabel, ElidedLabel, IconButton, RoundButton, SeekBar, fmt_time, themed, DEFAULT_ACCENT


class PlayerBar(QWidget):
    openNowPlaying = pyqtSignal()
    lyricsToggled = pyqtSignal(bool)
    miniRequested = pyqtSignal()
    queueRequested = pyqtSignal()
    sleepRequested = pyqtSignal()

    def __init__(self, player: Player, parent=None):
        super().__init__(parent)
        self.p = player
        self._accent = QColor(DEFAULT_ACCENT)
        self._seeking = False
        self._radius = 0
        self.setFixedHeight(88)
        self.setAutoFillBackground(False)

        self.art = ArtLabel(60, 9)
        self.title = ElidedLabel("Nothing playing")
        f = self.title.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 0.5)
        self.title.setFont(f)
        self.artist = ElidedLabel("")
        self.artist.setStyleSheet("color: palette(placeholder-text);")
        self.like = IconButton("rating-unrated", "Like", 20)
        self.dislike = IconButton("rating-unrated", "Dislike", 18)
        self.like.set_glyph("heart")
        self.dislike.set_glyph("thumb-down")

        info = QVBoxLayout()
        info.setSpacing(1)
        info.addStretch()
        info.addWidget(self.title)
        info.addWidget(self.artist)
        info.addStretch()
        left = QHBoxLayout()
        left.setSpacing(12)
        left.addWidget(self.art)
        left.addLayout(info, 1)
        left.addWidget(self.like)
        left.addWidget(self.dislike)
        leftw = QWidget()
        leftw.setLayout(left)

        self.shuffle = IconButton(["media-playlist-shuffle"], "Shuffle", 18, checkable=True)
        self.prev = IconButton(["media-skip-backward"], "Previous", 22)
        self.play = RoundButton(42)
        self.next = IconButton(["media-skip-forward"], "Next", 22)
        self.repeat = IconButton(["media-playlist-repeat"], "Repeat", 18, checkable=True)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addStretch()
        for w in (self.shuffle, self.prev, self.play, self.next, self.repeat):
            buttons.addWidget(w)
        buttons.addStretch()

        self.pos_lbl = QLabel("0:00")
        self.dur_lbl = QLabel("0:00")
        for l in (self.pos_lbl, self.dur_lbl):
            l.setStyleSheet("color: palette(placeholder-text);")
            l.setMinimumWidth(38)
        self.pos_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.seek = SeekBar()
        seekrow = QHBoxLayout()
        seekrow.setSpacing(6)
        seekrow.addWidget(self.pos_lbl)
        seekrow.addWidget(self.seek, 1)
        seekrow.addWidget(self.dur_lbl)

        center = QVBoxLayout()
        center.setSpacing(0)
        center.addStretch()
        center.addLayout(buttons)
        center.addLayout(seekrow)
        center.addStretch()
        centerw = QWidget()
        centerw.setLayout(center)
        centerw.setMaximumWidth(620)

        self.vol_btn = IconButton(["audio-volume-high"], "Mute", 18)
        self.vol = SeekBar()
        self.vol.setFixedWidth(96)
        self.queue_btn = IconButton(["view-media-playlist", "format-list-unordered"], "Queue / Up next", 18)
        self.lyrics_btn = IconButton(["view-media-lyrics", "text-x-generic"], "Lyrics", 18, checkable=True)
        self.sleep_btn = IconButton(["chronometer", "appointment-soon"], "Sleep timer", 18)
        self.mini_btn = IconButton(["window-pip-enter", "view-restore"], "Mini player", 18)
        right = QHBoxLayout()
        right.setSpacing(2)
        right.addStretch()
        for w in (self.sleep_btn, self.queue_btn, self.lyrics_btn, self.mini_btn, self.vol_btn, self.vol):
            right.addWidget(w)
        rightw = QWidget()
        rightw.setLayout(right)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 6, 16, 6)
        row.setSpacing(16)
        row.addWidget(leftw, 3)
        row.addWidget(centerw, 4)
        row.addWidget(rightw, 3)

        self.play.clicked.connect(self.p.toggle)
        self.next.clicked.connect(self.p.next)
        self.prev.clicked.connect(self.p.prev)
        self.shuffle.clicked.connect(self.p.toggle_shuffle)
        self.repeat.clicked.connect(self.p.cycle_repeat)
        self.like.clicked.connect(self.p.toggle_like)
        self.dislike.clicked.connect(self.p.toggle_dislike)
        self.vol_btn.clicked.connect(self.p.toggle_mute)
        self.vol.moved.connect(self.p.set_volume)
        self.vol.enable_wheel()
        self.vol.wheeled.connect(lambda n: self.p.volume_step(5 * n))
        self.seek.moved.connect(self._seek_moved)
        self.seek.released.connect(self._seek_released)
        self.art.clicked.connect(self.openNowPlaying)
        self.title.clicked.connect(self.openNowPlaying)
        self.queue_btn.clicked.connect(self.queueRequested)
        self.sleep_btn.clicked.connect(self.sleepRequested)
        self.mini_btn.clicked.connect(self.miniRequested)
        self.lyrics_btn.toggled.connect(self.lyricsToggled)

        self.p.changed.connect(self.refresh)
        self._tick = QTimer(self)
        self._tick.setInterval(250)
        self._tick.timeout.connect(self._update_position)
        self._tick.start()
        self.refresh()

    def set_image(self, img: QImage | None):
        self.art.set_image(img)

    def set_radius(self, r):
        self._radius = r
        self.update()

    def set_accent(self, c: QColor):
        self._accent = QColor(c)
        self.seek.set_accent(c)
        self.vol.set_accent(c)
        self.play.set_accent(c)
        self.refresh()
        self.update()

    def _seek_moved(self, frac):
        self._seeking = True
        self.pos_lbl.setText(fmt_time(frac * self.p.duration))

    def _seek_released(self, frac):
        self._seeking = False
        if self.p.duration > 0 and not self.p.is_ad:
            self.p.seek(frac * self.p.duration)

    def _update_position(self):
        if self._seeking:
            return
        d = self.p.duration
        pos = self.p.position()
        self.pos_lbl.setText(fmt_time(pos))
        self.seek.set_value(pos / d if d > 0 else 0.0)

    def refresh(self):
        p = self.p
        has = p.available
        self.title.setText(p.display_title if has else "Nothing playing")
        self.artist.setText(p.artist if has else "Pick something in the library")
        self.dur_lbl.setText(fmt_time(p.duration))
        self.play.set_playing(p.playing)
        self.play.setToolTip("Pause" if p.playing else "Play")
        liked, disliked = p.like == "LIKE", p.like == "DISLIKE"
        self.like.set_glyph("heart-fill" if liked else "heart", self._accent if liked else None)
        self.like.setToolTip("Remove like" if liked else "Like")
        self.dislike.set_glyph("thumb-down-fill" if disliked else "thumb-down", self._accent if disliked else None)
        self.dislike.setToolTip("Remove dislike" if disliked else "Dislike")
        self.shuffle.setChecked(p.shuffle)
        self.repeat.setChecked(p.repeat != "NONE")
        self.repeat.set_icon_name("media-playlist-repeat-song" if p.repeat == "ONE" else "media-playlist-repeat",
                                  "media-playlist-repeat")
        self.repeat.setToolTip({"NONE": "Repeat: off", "ALL": "Repeat: all", "ONE": "Repeat: one"}[p.repeat])
        vol = 0.0 if p.muted else p.volume
        if not self.vol._drag:
            self.vol.set_value(vol)
        self.vol_btn.set_icon_name(
            "audio-volume-muted" if vol <= 0.001 else "audio-volume-low" if vol < 0.34
            else "audio-volume-medium" if vol < 0.67 else "audio-volume-high", "audio-volume-high")
        for w in (self.play, self.next, self.prev, self.shuffle, self.repeat, self.like, self.dislike):
            w.setEnabled(has)
        self.next.setEnabled(has and p.can_next)
        self.prev.setEnabled(has and p.can_prev)
        self.seek.setEnabled(has and p.duration > 0 and not p.is_ad)
        self._update_position()

    def paintEvent(self, e):
        pnt = QPainter(self)
        pnt.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._radius
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), r, r)
        if r:
            sq = QPainterPath()
            sq.addRect(QRectF(0, 0, self.width(), self.height() / 2))
            path = path.united(sq)
        pnt.setClipPath(path)
        base = self.palette().window().color()
        pnt.fillRect(self.rect(), base.darker(112))
        g = QLinearGradient(0, 0, self.width() * 0.55, 0)
        c1 = QColor(self._accent)
        c1.setAlpha(34)
        c2 = QColor(self._accent)
        c2.setAlpha(0)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        pnt.fillRect(self.rect(), g)
        line = QColor(self.palette().text().color())
        line.setAlpha(26)
        pnt.fillRect(QRectF(0, 0, self.width(), 1), line)
