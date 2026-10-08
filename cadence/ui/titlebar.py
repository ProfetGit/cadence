from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QAbstractButton, QHBoxLayout, QToolButton, QWidget

from .widgets import ElidedLabel

HEIGHT = 42
RADIUS = 12


class WindowButton(QAbstractButton):
    """Minimal minimise / maximise / restore / close glyph button."""

    def __init__(self, kind, tip, parent=None):
        super().__init__(parent)
        self.kind = kind
        self._hover = False
        self.setToolTip(tip)
        self.setFixedSize(34, 28)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_kind(self, kind):
        self.kind = kind
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
        text = self.palette().text().color()
        danger = self.kind == "close"
        if self._hover or self.isDown():
            bg = QColor("#e5484d") if danger else QColor(text)
            if not danger:
                bg.setAlphaF(0.20 if self.isDown() else 0.11)
            elif self.isDown():
                bg = bg.darker(120)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 7, 7)
        fg = QColor("#ffffff") if (danger and (self._hover or self.isDown())) else QColor(text)
        fg.setAlphaF(1.0 if self._hover else 0.72)
        pen = QPen(fg, 1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        c = QPointF(self.width() / 2, self.height() / 2)
        k = 4.5
        if self.kind == "min":
            p.drawLine(QPointF(c.x() - k, c.y() + 0.5), QPointF(c.x() + k, c.y() + 0.5))
        elif self.kind == "max":
            p.drawRoundedRect(QRectF(c.x() - k, c.y() - k, 2 * k, 2 * k), 1.8, 1.8)
        elif self.kind == "restore":
            p.drawRoundedRect(QRectF(c.x() - k, c.y() - k + 2, 2 * k - 2, 2 * k - 2), 1.6, 1.6)
            path = QPainterPath()
            path.moveTo(c.x() - k + 2.5, c.y() - k + 2)
            path.lineTo(c.x() - k + 2.5, c.y() - k)
            path.lineTo(c.x() + k, c.y() - k)
            path.lineTo(c.x() + k, c.y() + k - 2.5)
            path.lineTo(c.x() + k - 2, c.y() + k - 2.5)
            p.drawPath(path)
        else:
            p.drawLine(QPointF(c.x() - k + 0.5, c.y() - k + 0.5), QPointF(c.x() + k - 0.5, c.y() + k - 0.5))
            p.drawLine(QPointF(c.x() + k - 0.5, c.y() - k + 0.5), QPointF(c.x() - k + 0.5, c.y() + k - 0.5))


class TitleBar(QWidget):
    """One slim row: navigation, page tabs, now-playing, tools and (optionally) window controls."""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.csd = win.csd
        self._radius = RADIUS if self.csd else 0
        self.setFixedHeight(HEIGHT)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(2)

        for act in (win.a_back, win.a_fwd, win.a_reload, win.a_home):
            lay.addWidget(self._tool(act))
        lay.addSpacing(8)
        for i, name in enumerate(("Home", "Explore", "Library")):
            b = QToolButton()
            b.setText(name)
            b.setAutoRaise(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, i=i: win.app.web_nav(i))
            lay.addWidget(b)

        self.title = ElidedLabel("")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet("color: palette(placeholder-text);")
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.title, 1)

        for act in (win.a_now, win.a_search):
            lay.addWidget(self._tool(act))
        self.menu_btn = QToolButton()
        self.menu_btn.setIcon(win.menu_icon)
        self.menu_btn.setToolTip("Menu")
        self.menu_btn.setAutoRaise(True)
        self.menu_btn.setIconSize(QSize(18, 18))
        self.menu_btn.setFixedSize(32, 30)
        self.menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_btn.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        self.menu_btn.setMenu(win.build_menu())
        lay.addWidget(self.menu_btn)

        self.b_min = self.b_max = self.b_close = None
        if self.csd:
            lay.addSpacing(10)
            self.b_min = WindowButton("min", "Minimise")
            self.b_max = WindowButton("max", "Maximise")
            self.b_close = WindowButton("close", "Close")
            self.b_min.clicked.connect(win.showMinimized)
            self.b_max.clicked.connect(win.toggle_maximized)
            self.b_close.clicked.connect(win.close)
            for b in (self.b_min, self.b_max, self.b_close):
                lay.addWidget(b)

    def _tool(self, action):
        b = QToolButton()
        b.setDefaultAction(action)
        b.setAutoRaise(True)
        b.setIconSize(QSize(18, 18))
        b.setFixedSize(32, 30)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return b

    def set_title(self, text):
        self.title.setText(text)

    def set_radius(self, r):
        self._radius = r if self.csd else 0
        self.update()

    def set_maximized(self, maxed):
        if self.b_max:
            self.b_max.set_kind("restore" if maxed else "max")
            self.b_max.setToolTip("Restore" if maxed else "Maximise")

    def mousePressEvent(self, e):
        if self.csd and e.button() == Qt.MouseButton.LeftButton:
            h = self.win.windowHandle()
            if h:
                h.startSystemMove()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self.csd and e.button() == Qt.MouseButton.LeftButton:
            self.win.toggle_maximized()
        else:
            super().mouseDoubleClickEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._radius
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), r, r)
        if r:
            sq = QPainterPath()
            sq.addRect(QRectF(0, self.height() / 2, self.width(), self.height() / 2))
            path = path.united(sq)
        p.fillPath(path, self.palette().window().color().darker(112))
        line = QColor(self.palette().text().color())
        line.setAlpha(22)
        p.fillRect(QRectF(0, self.height() - 1, self.width(), 1), line)
