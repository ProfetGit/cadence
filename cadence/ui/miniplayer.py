from PyQt6.QtCore import QEasingCurve, QRectF, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget

from .. import kwin
from .lyrics_panel import LyricsPanel
from .widgets import ArtLabel, ElidedLabel, IconButton, RoundButton, SeekBar, fmt_time, themed, DEFAULT_ACCENT

CAPTION = "Cadence Mini"
TOP_H = 118
LYRICS_H = 300


class MiniPlayer(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.p = app.player
        self._accent = QColor(DEFAULT_ACCENT)
        self._seeking = False
        self.setWindowTitle(CAPTION)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(392)
        self.setFixedHeight(TOP_H)
        self._anim = None

        self.art = ArtLabel(88, 14)
        self.title = ElidedLabel("Nothing playing")
        f = self.title.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 1)
        self.title.setFont(f)
        self.artist = ElidedLabel("")
        self.artist.setStyleSheet("color: palette(placeholder-text);")
        self.prev = IconButton("media-skip-backward", "Previous", 18)
        self.play = RoundButton(34)
        self.next = IconButton("media-skip-forward", "Next", 18)
        self.like = IconButton("rating-unrated", "Like", 16)
        self.like.set_glyph("heart")
        self.lyr_btn = IconButton("view-media-lyrics", "Lyrics", 16, checkable=True)
        self.expand = IconButton("window-restore", "Open Cadence", 12)
        self.close_btn = IconButton("window-close", "Close mini player", 12)
        self.expand.set_glyph("expand")
        self.close_btn.set_glyph("close")
        self.seek = SeekBar()
        self.pos_lbl = QLabel("0:00")
        self.pos_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 10px;")
        self.dur_lbl = QLabel("0:00")
        self.dur_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 10px;")

        controls = QHBoxLayout()
        controls.setSpacing(2)
        for w in (self.prev, self.play, self.next, self.like, self.lyr_btn):
            controls.addWidget(w)
        controls.addStretch()
        controls.addWidget(self.expand)
        controls.addWidget(self.close_btn)
        seekrow = QHBoxLayout()
        seekrow.setSpacing(4)
        seekrow.addWidget(self.pos_lbl)
        seekrow.addWidget(self.seek, 1)
        seekrow.addWidget(self.dur_lbl)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(self.title)
        col.addWidget(self.artist)
        col.addLayout(controls)
        col.addLayout(seekrow)
        top = QWidget()
        top.setFixedHeight(TOP_H)
        row = QHBoxLayout(top)
        row.setContentsMargins(14, 14, 10, 8)
        row.setSpacing(14)
        row.addWidget(self.art, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(col, 1)

        self.lyr = LyricsPanel(app.player, compact=True)
        self.lyr.set_radius(20)
        self.lyr.setVisible(False)
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 0, 1, 1)
        root.setSpacing(0)
        root.addWidget(top)
        root.addWidget(self.lyr, 1)

        self.play.clicked.connect(self.p.toggle)
        self.next.clicked.connect(self.p.next)
        self.prev.clicked.connect(self.p.prev)
        self.like.clicked.connect(self.p.toggle_like)
        self.expand.clicked.connect(lambda: (app.show_window(), None))
        self.close_btn.clicked.connect(self.hide)
        self.lyr_btn.toggled.connect(self.set_lyrics)
        self.art.clicked.connect(app.show_window)
        self.seek.moved.connect(lambda f: (setattr(self, "_seeking", True), self.pos_lbl.setText(fmt_time(f * self.p.duration))))
        self.seek.released.connect(self._released)
        self.p.changed.connect(self.refresh)
        self._tick = QTimer(self)
        self._tick.setInterval(250)
        self._tick.timeout.connect(self._position)
        self.refresh()

    def set_image(self, img: QImage | None):
        self.art.set_image(img)
        self.lyr.set_image(img)

    def set_lyrics(self, on):
        self.app.settings["mini_lyrics"] = on
        if self.lyr_btn.isChecked() != on:
            self.lyr_btn.setChecked(on)
            return
        if on:
            self.lyr.setVisible(True)
            self.app.fetch_lyrics()
        if self._anim is not None:
            self._anim.stop()
        a = QVariantAnimation(self)
        a.setDuration(340)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.setStartValue(self.height())
        a.setEndValue(TOP_H + LYRICS_H if on else TOP_H)
        a.valueChanged.connect(lambda v: self.setFixedHeight(int(v)))
        if not on:
            a.finished.connect(lambda: self.lyr.setVisible(False))
        self._anim = a
        a.start()

    def set_accent(self, c: QColor):
        self._accent = QColor(c)
        self.seek.set_accent(c)
        self.play.set_accent(c)
        self.lyr.set_accent(c)
        self.refresh()
        self.update()

    def _released(self, frac):
        self._seeking = False
        if self.p.duration > 0 and not self.p.is_ad:
            self.p.seek(frac * self.p.duration)

    def _position(self):
        if self._seeking or not self.isVisible():
            return
        d = self.p.duration
        pos = self.p.position()
        self.pos_lbl.setText(fmt_time(pos))
        self.seek.set_value(pos / d if d > 0 else 0)

    def refresh(self):
        p = self.p
        self.title.setText(p.display_title if p.available else "Nothing playing")
        self.artist.setText(p.artist)
        self.dur_lbl.setText(fmt_time(p.duration))
        self.play.set_playing(p.playing)
        liked = p.like == "LIKE"
        self.like.set_glyph("heart-fill" if liked else "heart", self._accent if liked else None)
        for w in (self.play, self.next, self.prev, self.like):
            w.setEnabled(p.available)
        self.seek.setEnabled(p.available and p.duration > 0 and not p.is_ad)
        self._position()

    def showEvent(self, e):
        super().showEvent(e)
        self._tick.start()
        if self.app.settings["mini_lyrics"] and not self.lyr_btn.isChecked():
            self.lyr_btn.setChecked(True)
        if self.app.settings["mini_pinned"]:
            QTimer.singleShot(300, lambda: kwin.set_keep_above(CAPTION, True))
        self.refresh()

    def hideEvent(self, e):
        self._tick.stop()
        super().hideEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            h = self.windowHandle()
            if h:
                h.startSystemMove()

    def contextMenuEvent(self, e):
        m = QMenu(self)
        pin = m.addAction("Always on top")
        pin.setCheckable(True)
        pin.setChecked(self.app.settings["mini_pinned"])
        m.addAction("Open Cadence", self.app.show_window)
        m.addSeparator()
        m.addAction("Close", self.hide)
        chosen = m.exec(e.globalPos())
        if chosen is pin:
            on = pin.isChecked()
            self.app.settings["mini_pinned"] = on
            kwin.set_keep_above(CAPTION, on)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 20, 20)
        base = self.palette().window().color().darker(115)
        base.setAlphaF(float(self.app.settings["mini_opacity"]))
        p.fillPath(path, base)
        g = QLinearGradient(0, 0, self.width(), self.height())
        c1 = QColor(self._accent)
        c1.setAlpha(46)
        c2 = QColor(self._accent)
        c2.setAlpha(0)
        g.setColorAt(0, c1)
        g.setColorAt(0.75, c2)
        p.fillPath(path, g)
        edge = QColor(self.palette().text().color())
        edge.setAlpha(36)
        p.setPen(edge)
        p.drawPath(path)
