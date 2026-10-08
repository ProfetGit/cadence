import bisect
import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
    QTextLayout, QTextOption,
)
from PyQt6.QtWidgets import QPushButton, QWidget

from ..lyrics import LyricsResult
from ..player import Player

PAD = 28
BASE_PX = 27
INACTIVE_SCALE = 0.74
ANCHOR = 0.34
LEAD = 0.34


def _ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _approach(cur, target, rate, dt):
    return cur + (target - cur) * (1.0 - math.exp(-rate * dt))


class _Line:
    __slots__ = ("text", "t", "tl", "rows", "h", "scale", "alpha", "y")

    def __init__(self, text, t):
        self.text = text or "♪"
        self.t = t
        self.tl = None
        self.rows = []
        self.h = 0.0
        self.scale = INACTIVE_SCALE
        self.alpha = 0.0
        self.y = 0.0


class LyricsPanel(QWidget):
    """Custom-painted lyrics: spring scroll, distance-based scale/fade, per-line karaoke sweep."""

    openWebLyrics = pyqtSignal()
    offsetChanged = pyqtSignal(float)

    def __init__(self, player: Player, compact=False, parent=None):
        super().__init__(parent)
        self.p = player
        self._compact = compact
        self._pad = 18 if compact else PAD
        self._base_px = 20 if compact else BASE_PX
        self._radius = 0
        self._user = 0.0
        self._hdr = {}
        self._hdr_hover = False
        self._lines = []
        self._times = []
        self._synced = False
        self._state = "message"
        self._message = ""
        self._accent = QColor("#c9c9c9")
        self._offset = 0.0
        self._manual_until = 0.0
        self._hover = -1
        self._hit = []
        self._born = 0.0
        self._idx = -1
        self._last = time.monotonic()
        self._layout_w = 0
        self._font = QFont(self.font())
        self._font.setPixelSize(self._base_px)
        self._font.setWeight(QFont.Weight.Bold)
        self._bg_old = None
        self._bg_new = None
        self._bg_fade = 1.0
        self._layer = None

        self.setMouseTracking(True)
        self.setMinimumWidth(0)

        self.web_btn = QPushButton("Open lyrics on YouTube Music", self)
        self.web_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.web_btn.clicked.connect(self.openWebLyrics)
        self.web_btn.hide()

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.p.changed.connect(self._kick)
        self.p.seeked.connect(lambda _: self._kick())

    # ---- public API ----------------------------------------------------------------------
    def set_accent(self, c: QColor):
        self._accent = QColor(c)
        self._kick()

    def set_image(self, img: QImage | None):
        if img is None or img.isNull():
            self._bg_old, self._bg_new, self._bg_fade = self._bg_new, None, 0.0
        else:
            small = img.scaled(14, 14, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._bg_old, self._bg_new, self._bg_fade = self._bg_new, QPixmap.fromImage(small), 0.0
        self._kick()

    def set_loading(self):
        self._clear()
        self._state = "loading"
        self.web_btn.hide()
        self._kick()

    def set_message(self, text, button=False):
        self._clear()
        self._state = "message"
        self._message = text
        self.web_btn.setVisible(button)
        self._place_button()
        self._kick()

    def set_offline(self):
        self.set_message("Couldn't reach the lyrics service.", True)

    def set_result(self, res: LyricsResult | None):
        if res is None:
            return self.set_offline()
        if res.synced:
            self._load([(t, x) for t, x in res.synced], True)
        elif res.plain:
            self._load([(0.0, x) for x in res.plain.splitlines()], False)
        else:
            self.set_message("No lyrics found for this track.", True)

    def _lead(self):
        return LEAD + self._user

    def set_radius(self, r):
        self._radius = r
        self.update()

    def set_user_offset(self, v):
        self._user = float(v)
        self._kick()
        self.update()

    def _nudge(self, delta):
        self._user = round(0.0 if delta == 0 else max(-3.0, min(3.0, self._user + delta)), 2)
        self.offsetChanged.emit(self._user)
        self._kick()

    # ---- state ---------------------------------------------------------------------------
    def _clear(self):
        self._lines = []
        self._times = []
        self._idx = -1
        self._hover = -1
        self._hit = []

    def _load(self, items, synced):
        self._clear()
        self._state = "lyrics"
        self._synced = synced
        self.web_btn.hide()
        self._lines = [_Line(x, t) for t, x in items]
        self._times = [ln.t for ln in self._lines] if synced else []
        self._layout_w = 0
        self._relayout()
        self._born = time.monotonic()
        self._offset = -(self.height() * ANCHOR + 30) if synced else -150.0
        self._kick()

    def _relayout(self):
        width = max(260 if self._compact else 300, self.width()) - 2 * self._pad
        if width == self._layout_w:
            return
        self._layout_w = width
        for ln in self._lines:
            tl = QTextLayout(ln.text, self._font)
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WordWrap)
            tl.setTextOption(opt)
            tl.beginLayout()
            y = 0.0
            rows = []
            while True:
                row = tl.createLine()
                if not row.isValid():
                    break
                row.setLineWidth(width)
                row.setPosition(QPointF(0, y))
                y += row.height()
                rows.append(row)
            tl.endLayout()
            ln.tl, ln.rows, ln.h = tl, rows, y

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()
        self._place_button()
        self._layer = None
        self._kick()

    def _place_button(self):
        s = self.web_btn.sizeHint()
        self.web_btn.move((self.width() - s.width()) // 2, int(self.height() * 0.5) + 28)

    def showEvent(self, e):
        super().showEvent(e)
        self._last = time.monotonic()
        self._kick()

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def _kick(self):
        if self.isVisible() and not self._timer.isActive():
            self._last = time.monotonic()
            self._timer.start()

    # ---- input ---------------------------------------------------------------------------
    def wheelEvent(self, e):
        if self._state != "lyrics":
            return
        dy = e.pixelDelta().y() or e.angleDelta().y() * 0.6
        self._offset -= dy
        self._manual_until = time.monotonic() + 2.8
        self._kick()
        e.accept()

    def mousePressEvent(self, e):
        e.accept()

    def mouseMoveEvent(self, e):
        hov = e.position().y() < 44 and bool(self._hdr)
        if hov != self._hdr_hover:
            self._hdr_hover = hov
            self.update()
        h = -1
        if self._synced:
            y = e.position().y()
            for top, bottom, i in self._hit:
                if top <= y <= bottom:
                    h = i
                    break
        if h != self._hover:
            self._hover = h
            self.setCursor(Qt.CursorShape.PointingHandCursor if h >= 0 else Qt.CursorShape.ArrowCursor)
            self._kick()

    def leaveEvent(self, e):
        self._hover = -1
        self._kick()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() < 44 and self._hdr:
            pt = e.position()
            if self._hdr["minus"].contains(pt):
                self._nudge(-0.1)
            elif self._hdr["plus"].contains(pt):
                self._nudge(0.1)
            elif self._hdr["val"].contains(pt):
                self._nudge(0)
            return
        if e.button() == Qt.MouseButton.LeftButton and self._synced and self._hover >= 0:
            self.p.seek(self._times[self._hover])
            self._manual_until = 0.0
            self._kick()

    # ---- animation -----------------------------------------------------------------------
    def _tick(self):
        now = time.monotonic()
        dt = min(0.05, max(0.001, now - self._last))
        self._last = now
        moving = self._step(now, dt)
        self.update()
        if not moving and not self.p.playing:
            self._timer.stop()

    def _step(self, now, dt):
        moving = False
        if self._bg_fade < 1.0:
            self._bg_fade = min(1.0, self._bg_fade + dt / 0.8)
            moving = True
        if self._state == "loading":
            return True
        if self._state != "lyrics" or not self._lines:
            return moving

        if self._synced:
            idx = bisect.bisect_right(self._times, self.p.position() + self._lead()) - 1
        else:
            idx = -2
        self._idx = idx

        for i, ln in enumerate(self._lines):
            if self._synced:
                d = i - idx
                if d == 0:
                    ts, ta = 1.0, 1.0
                elif d < 0:
                    ts, ta = INACTIVE_SCALE, max(0.16, 0.40 - 0.07 * (-d - 1))
                else:
                    ts, ta = INACTIVE_SCALE, max(0.14, 0.52 - 0.10 * (d - 1))
                if i == self._hover and d != 0:
                    ta = max(ta, 0.85)
            else:
                ts, ta = 1.0, 0.9
            ns, na = _approach(ln.scale, ts, 15, dt), _approach(ln.alpha, ta, 12, dt)
            if abs(ns - ts) > 0.002 or abs(na - ta) > 0.003:
                moving = True
            ln.scale, ln.alpha = ns, na

        y = 0.0
        for ln in self._lines:
            ln.y = y
            y += ln.h * ln.scale + 16 * ln.scale + (8 if ln.scale > 0.95 else 0)
        content_h = y

        H = self.height()
        limit = max(0.0, content_h - H * 0.6)
        lo = -(H * ANCHOR + 30) if self._synced else -150.0
        if self._synced:
            if idx >= 0:
                ln = self._lines[idx]
                centre = ln.y + ln.h * ln.scale * 0.5
            else:
                centre = self._lines[0].y
            target = max(lo, min(centre - H * ANCHOR, limit))
            if now >= self._manual_until:
                new = _approach(self._offset, target, 9.0, dt)
                if abs(new - self._offset) > 0.1:
                    moving = True
                self._offset = new
            else:
                self._offset = max(lo, min(self._offset, limit))
                moving = True
        else:
            self._offset = max(lo, min(self._offset, limit))
        if now - self._born < 1.6:
            moving = True
        return moving

    # ---- painting ------------------------------------------------------------------------
    def paintEvent(self, e):
        W, H = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                         | QPainter.RenderHint.SmoothPixmapTransform)
        if self._radius:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
            sq = QPainterPath()
            sq.addRect(QRectF(0, 0, W, H / 2))
            p.setClipPath(clip.united(sq))
        base = self.palette().window().color().darker(112)
        p.fillRect(self.rect(), base)
        self._paint_backdrop(p, W, H, base)

        text = self.palette().text().color()
        if self._state == "lyrics" and self._lines:
            self._paint_lines(p, W, H, text)
        elif self._state == "loading":
            self._paint_skeleton(p, W, H, text)
        else:
            self._paint_message(p, W, H, text)
        self._paint_header(p, W, text)

        edge = QColor(text)
        edge.setAlpha(24)
        p.fillRect(0, 0, 1, H, edge)

    def _paint_backdrop(self, p, W, H, base):
        for pm, a in ((self._bg_old, 1.0 - self._bg_fade), (self._bg_new, self._bg_fade)):
            if pm is not None and a > 0.01:
                p.setOpacity(0.55 * a)
                p.drawPixmap(QRectF(-W * 0.2, -H * 0.1, W * 1.4, H * 1.2), pm, QRectF(pm.rect()))
        p.setOpacity(1.0)
        g = QLinearGradient(0, 0, 0, H)
        top = QColor(base)
        top.setAlpha(150)
        bot = QColor(base)
        bot.setAlpha(225)
        g.setColorAt(0, top)
        g.setColorAt(1, bot)
        p.fillRect(self.rect(), g)
        glow = QRadialGradient(QPointF(W * 0.15, H * ANCHOR), max(W, 300) * 0.95)
        c0 = QColor(self._accent)
        c0.setAlpha(46)
        c1 = QColor(self._accent)
        c1.setAlpha(0)
        glow.setColorAt(0, c0)
        glow.setColorAt(1, c1)
        p.fillRect(self.rect(), glow)

    def _layer_for(self, W, H):
        dpr = self.devicePixelRatioF()
        if self._layer is None or self._layer.width() != int(W * dpr) or self._layer.height() != int(H * dpr):
            self._layer = QPixmap(int(W * dpr), int(H * dpr))
            self._layer.setDevicePixelRatio(dpr)
        self._layer.fill(Qt.GlobalColor.transparent)
        return self._layer

    def _paint_lines(self, p, W, H, text):
        layer = self._layer_for(W, H)
        q = QPainter(layer)
        q.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                         | QPainter.RenderHint.SmoothPixmapTransform)
        now = time.monotonic()
        age = now - self._born
        self._hit = []
        pos = self.p.position() + self._lead()
        for i, ln in enumerate(self._lines):
            top = ln.y - self._offset
            bottom = top + ln.h * ln.scale
            if bottom < -40 or top > H + 40:
                continue
            enter = _ease((age - min(i, 14) * 0.04) / 0.55)
            if enter <= 0.0:
                continue
            slide = (1.0 - enter) * 26
            self._hit.append((top, bottom, i))
            q.save()
            q.translate(self._pad, top + slide)
            q.scale(ln.scale, ln.scale)
            if self._synced and i == self._idx:
                self._draw_active(q, ln, text, pos, i, enter)
            else:
                col = QColor(text)
                col.setAlphaF(max(0.0, min(1.0, ln.alpha * enter)))
                q.setPen(QPen(col))
                for row in ln.rows:
                    row.draw(q, QPointF(0, 0))
            q.restore()
        if self._synced and self._idx < 0 and self._times and self._times[0] > 2.0:
            self._paint_dots(q, self._lines[0].y - self._offset - 38, text, now)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        mask = QLinearGradient(0, 0, 0, H)
        mask.setColorAt(0.0, QColor(0, 0, 0, 0))
        mask.setColorAt(min(0.1, 54.0 / H), QColor(0, 0, 0, 0))
        mask.setColorAt(min(0.25, 140.0 / H), QColor(0, 0, 0, 255))
        mask.setColorAt(max(0.78, 1 - 90.0 / H), QColor(0, 0, 0, 255))
        mask.setColorAt(1.0, QColor(0, 0, 0, 0))
        q.fillRect(0, 0, W, H, mask)
        q.end()
        p.drawPixmap(0, 0, layer)

    def _draw_active(self, q, ln, text, pos, i, enter):
        nxt = self._times[i + 1] if i + 1 < len(self._times) else ln.t + 5.0
        dur = max(0.6, min(nxt - ln.t, max(1.6, len(ln.text) * 0.085)))
        prog = max(0.0, min(1.0, (pos - ln.t) / dur))
        bright = QColor(text)
        bright.setAlphaF(enter)
        dim = QColor(text)
        dim.setAlphaF(0.42 * enter)
        glow = QColor(self._accent)
        glow.setAlphaF(0.14 * enter)
        total = sum(r.naturalTextWidth() for r in ln.rows) or 1.0
        fill = prog * total
        q.setPen(QPen(glow))
        for off in ((-1.6, 0), (1.6, 0), (0, -1.6), (0, 1.6)):
            for row in ln.rows:
                row.draw(q, QPointF(*off))
        cum = 0.0
        for row in ln.rows:
            w = row.naturalTextWidth()
            local = fill - cum
            cum += w
            if local <= 0:
                local = -60.0
            elif local >= w:
                local = w + 60.0
            g = QLinearGradient(local - 26, 0, local + 8, 0)
            g.setColorAt(0.0, bright)
            g.setColorAt(1.0, dim)
            q.setPen(QPen(QBrush(g), 1))
            row.draw(q, QPointF(0, 0))

    def _paint_dots(self, q, y, text, now):
        q.setPen(Qt.PenStyle.NoPen)
        for k in range(3):
            ph = (math.sin(now * 3.2 - k * 0.9) + 1) / 2
            c = QColor(text)
            c.setAlphaF(0.25 + 0.6 * ph)
            q.setBrush(c)
            r = 4.0 + 2.2 * ph
            q.drawEllipse(QPointF(self._pad + 6 + k * 18, y), r, r)

    def _paint_skeleton(self, p, W, H, text):
        now = time.monotonic()
        widths = (0.82, 0.58, 0.9, 0.66, 0.76, 0.5, 0.86)
        x0, bw = self._pad, W - 2 * self._pad
        sweep = (now * 0.8) % 1.8 - 0.4
        for i, f in enumerate(widths):
            r = QRectF(x0, H * 0.22 + i * 46, bw * f, 24)
            c = QColor(text)
            c.setAlphaF(0.07)
            path = QPainterPath()
            path.addRoundedRect(r, 12, 12)
            p.fillPath(path, c)
            gx = x0 + sweep * bw
            g = QLinearGradient(gx - 70, 0, gx + 70, 0)
            hi = QColor(text)
            hi.setAlphaF(0.13)
            lo = QColor(text)
            lo.setAlphaF(0.0)
            g.setColorAt(0, lo)
            g.setColorAt(0.5, hi)
            g.setColorAt(1, lo)
            p.save()
            p.setClipPath(path)
            p.fillRect(r, g)
            p.restore()

    def _paint_message(self, p, W, H, text):
        c = QColor(text)
        c.setAlphaF(0.6)
        p.setPen(c)
        f = QFont(self.font())
        f.setPixelSize(15)
        p.setFont(f)
        flags = int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom) | int(Qt.TextFlag.TextWordWrap)
        p.drawText(QRectF(self._pad, 0, W - 2 * self._pad, H * 0.5 + 12), flags, self._message)

    def _paint_header(self, p, W, text):
        f = QFont(self.font())
        f.setPixelSize(10)
        f.setWeight(QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)
        p.setFont(f)
        c = QColor(text)
        c.setAlphaF(0.5)
        p.setPen(c)
        rect = QRectF(self._pad, 14, W - 2 * self._pad, 18)
        p.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "LYRICS")
        self._hdr = {}
        if not (self._synced and self._state == "lyrics"):
            return
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.4)
        p.setFont(f)
        right = W - self._pad
        a = 0.85 if self._hdr_hover else 0.30
        val = "%+.1fs" % self._user if abs(self._user) > 0.001 else "SYNC"
        vw, bw = 46.0, 20.0
        plus = QRectF(right - bw, 14, bw, 18)
        valr = QRectF(plus.left() - vw, 14, vw, 18)
        minus = QRectF(valr.left() - bw, 14, bw, 18)
        self._hdr = {"plus": plus, "val": valr, "minus": minus}
        c.setAlphaF(a)
        p.setPen(c)
        p.drawText(minus, Qt.AlignmentFlag.AlignCenter, "−")
        p.drawText(plus, Qt.AlignmentFlag.AlignCenter, "+")
        c.setAlphaF(a if abs(self._user) > 0.001 else a * 0.8)
        p.setPen(c)
        p.drawText(valr, Qt.AlignmentFlag.AlignCenter, val)
