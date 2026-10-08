from PyQt6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import (
    QBrush, QColor, QFontMetrics, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import QAbstractButton, QLabel, QSizePolicy, QToolButton, QWidget

DEFAULT_ACCENT = QColor("#c9c9c9")


def fmt_time(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


GLYPHS = {
    "heart": "M16.5 3c-1.74 0-3.41.81-4.5 2.09C10.91 3.81 9.24 3 7.5 3 4.42 3 2 5.42 2 8.5c0 3.78 3.4 6.86 8.55 11.54L12 21.35l1.45-1.32C18.6 15.36 22 12.28 22 8.5 22 5.42 19.58 3 16.5 3zm-4.4 15.55l-.1.1-.1-.1C7.14 14.24 4 11.39 4 8.5 4 6.5 5.5 5 7.5 5c1.54 0 3.04.99 3.57 2.36h1.87C13.46 5.99 14.96 5 16.5 5c2 0 3.5 1.5 3.5 3.5 0 2.89-3.14 5.74-7.9 10.05z",
    "heart-fill": "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z",
    "thumb-down": "M15 3H6c-.83 0-1.54.5-1.84 1.22l-3.02 7.05c-.09.23-.14.47-.14.73v2c0 1.1.9 2 2 2h6.31l-.95 4.57-.03.32c0 .41.17.79.44 1.06L9.83 23l6.59-6.59c.36-.36.58-.86.58-1.41V5c0-1.1-.9-2-2-2zm0 12l-4.34 4.34L12 14H3v-2l3-7h9v10zm4-12h4v12h-4z",
    "thumb-down-fill": "M15 3H6c-.83 0-1.54.5-1.84 1.22l-3.02 7.05c-.09.23-.14.47-.14.73v2c0 1.1.9 2 2 2h6.31l-.95 4.57-.03.32c0 .41.17.79.44 1.06L9.83 23l6.59-6.59c.36-.36.58-.86.58-1.41V5c0-1.1-.9-2-2-2zm4 0v12h4V3h-4z",
    "expand": "M21 11V3h-8l3.29 3.29-10 10L3 13v8h8l-3.29-3.29 10-10z",
    "close": "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
    "search": "M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z",
}


def glyph_icon(name: str, color: QColor, size: int = 24) -> QIcon:
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="%s" d="%s"/></svg>' % (
        color.name(), GLYPHS[name])
    r = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for s in (size, size * 2):
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        r.render(p)
        p.end()
        ic.addPixmap(pm)
    return ic


def themed(name: str, fallback: str = "") -> QIcon:
    ic = QIcon.fromTheme(name)
    if ic.isNull() and fallback:
        ic = QIcon.fromTheme(fallback)
    return ic


class IconButton(QToolButton):
    def __init__(self, icon_names, tip="", size=20, checkable=False, parent=None):
        super().__init__(parent)
        names = [icon_names] if isinstance(icon_names, str) else list(icon_names)
        self.setIcon(themed(names[0], names[1] if len(names) > 1 else ""))
        self.setIconSize(QSize(size, size))
        self.setToolTip(tip)
        self.setAutoRaise(True)
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(size + 12, size + 12)

    def set_icon_name(self, name, fallback=""):
        self.setIcon(themed(name, fallback))

    def set_glyph(self, name, color=None):
        self.setIcon(glyph_icon(name, color or self.palette().text().color(), self.iconSize().width()))


class RoundButton(QAbstractButton):
    """Filled circular play/pause button."""

    def __init__(self, size=44, parent=None):
        super().__init__(parent)
        self._playing = False
        self._accent = DEFAULT_ACCENT
        self._hover = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_playing(self, playing: bool):
        self._playing = playing
        self.update()

    def set_accent(self, c: QColor):
        self._accent = c
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = self.palette().text().color()
        col = QColor(base)
        if self.isDown():
            col = col.darker(120)
        elif not self._hover:
            col.setAlphaF(0.92)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        d = self.width()
        p.drawEllipse(QRectF(1, 1, d - 2, d - 2))
        p.setBrush(self.palette().window().color())
        c = d / 2
        k = d * 0.2
        if self._playing:
            bw, bh = d * 0.1, d * 0.34
            p.drawRoundedRect(QRectF(c - bw * 1.7, c - bh / 2, bw, bh), 1.5, 1.5)
            p.drawRoundedRect(QRectF(c + bw * 0.7, c - bh / 2, bw, bh), 1.5, 1.5)
        else:
            path = QPainterPath()
            path.moveTo(c - k * 0.55, c - k * 1.05)
            path.lineTo(c - k * 0.55, c + k * 1.05)
            path.lineTo(c + k * 1.15, c)
            path.closeSubpath()
            p.setPen(QPen(self.palette().window().color(), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)


class ElidedLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(20)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def setText(self, text):
        self._full = text
        self.setToolTip(text)
        self._elide()

    def text(self):
        return self._full

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, Qt.TextElideMode.ElideRight, max(0, self.width())))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class ArtLabel(QWidget):
    clicked = pyqtSignal()

    def __init__(self, size=56, radius=8, parent=None):
        super().__init__(parent)
        self._pm = None
        self._radius = radius
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_image(self, img: QImage | None):
        self._pm = None if img is None or img.isNull() else QPixmap.fromImage(img)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
        p.setClipPath(path)
        if self._pm:
            p.drawPixmap(self.rect(), self._pm)
        else:
            c = self.palette().mid().color()
            p.fillRect(self.rect(), c)
            ic = themed("media-optical")
            if not ic.isNull():
                s = self.width() // 2
                ic.paint(p, (self.width() - s) // 2, (self.height() - s) // 2, s, s)


class SeekBar(QWidget):
    """Thin custom slider: click or drag anywhere to jump."""

    moved = pyqtSignal(float)
    released = pyqtSignal(float)
    wheeled = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._v = 0.0
        self._hover = False
        self._drag = False
        self._accent = DEFAULT_ACCENT
        self._wheel = False
        self.setMinimumHeight(18)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(120, 18)

    def set_accent(self, c: QColor):
        self._accent = c
        self.update()

    def set_value(self, v: float):
        if self._drag:
            return
        v = max(0.0, min(1.0, v))
        if abs(v - self._v) > 1e-4:
            self._v = v
            self.update()

    def value(self):
        return self._v

    def _pos_to_value(self, x):
        pad = 6
        w = max(1, self.width() - 2 * pad)
        return max(0.0, min(1.0, (x - pad) / w))

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self._v = self._pos_to_value(e.position().x())
            self.moved.emit(self._v)
            self.update()

    def mouseMoveEvent(self, e):
        if self._drag:
            self._v = self._pos_to_value(e.position().x())
            self.moved.emit(self._v)
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag and e.button() == Qt.MouseButton.LeftButton:
            self._drag = False
            self.released.emit(self._v)
            self.update()

    def enable_wheel(self):
        self._wheel = True

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if self._wheel and d:
            self.wheeled.emit(1 if d > 0 else -1)
            e.accept()
        else:
            e.ignore()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad = 6
        w = self.width() - 2 * pad
        big = self._hover or self._drag
        h = 6 if big else 4
        y = (self.height() - h) / 2
        groove = QColor(self.palette().text().color())
        groove.setAlphaF(0.18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(groove)
        p.drawRoundedRect(QRectF(pad, y, w, h), h / 2, h / 2)
        fill = QColor(self._accent if self.isEnabled() else groove)
        p.setBrush(fill)
        fw = w * self._v
        p.drawRoundedRect(QRectF(pad, y, max(h, fw) if self._v > 0 else 0, h), h / 2, h / 2)
        if big and self.isEnabled():
            p.setBrush(self.palette().text().color())
            p.drawEllipse(QPointF(pad + fw, self.height() / 2), 6, 6)
