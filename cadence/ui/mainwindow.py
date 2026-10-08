from PyQt6.QtCore import QByteArray, QEasingCurve, QEvent, QPoint, QRect, Qt, QUrl, QVariantAnimation
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QMenu, QVBoxLayout, QWidget

from .. import APP_NAME
from .lyrics_panel import LyricsPanel
from .menus import make_sleep_menu
from .playerbar import PlayerBar
from .titlebar import RADIUS, TitleBar
from .widgets import glyph_icon, themed

ERROR_HTML = """<!doctype html><meta charset=utf-8><body style="margin:0;height:100vh;display:flex;align-items:center;
justify-content:center;background:#0f0f0f;color:#cfcfcf;font:15px system-ui,sans-serif;text-align:center">
<div><div style="font-size:44px;opacity:.5">&#9835;</div><h2 style="font-weight:600;margin:.2em 0">Can't reach YouTube Music</h2>
<p style="opacity:.6;margin:0 0 1.4em">%s</p>
<a href="https://music.youtube.com/" style="color:#0f0f0f;background:#d6d6d6;padding:.6em 1.4em;border-radius:99px;
text-decoration:none;font-weight:600">Try again</a></div></body>"""


class EdgeGrip(QWidget):
    """Invisible strip on a window edge: drag to resize through the compositor."""

    def __init__(self, win, edges, cursor):
        super().__init__(win)
        self.win = win
        self.edges = edges
        self.setCursor(cursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            h = self.win.windowHandle()
            if h:
                h.startSystemResize(self.edges)


class MainWindow(QMainWindow):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.s = app.settings
        self.csd = self.s["custom_titlebar"]
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app.icon)
        self.resize(1280, 820)
        self.setMinimumSize(760, 520)
        if self.csd:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.view = QWebEngineView(self)
        self.view.setPage(app.page)
        self.view.setZoomFactor(self.s["zoom"])
        self.lyrics = LyricsPanel(app.player)
        self.lyrics.set_accent(app.accent)
        self.lyrics.openWebLyrics.connect(lambda: app.web_tab(1))
        self._slide = None
        self.split = QWidget()
        hb = QHBoxLayout(self.split)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(0)
        hb.addWidget(self.view, 1)
        hb.addWidget(self.lyrics, 0)
        self.lyrics.setFixedWidth(400)
        self.lyrics.setVisible(False)

        self.bar = PlayerBar(app.player)
        self.banner = QLabel("")
        self.banner.setWordWrap(True)
        self.banner.setContentsMargins(14, 6, 14, 6)
        self.banner.setStyleSheet("background: palette(highlight); color: palette(highlighted-text);")
        self.banner.hide()

        self._build_actions()
        self.titlebar = TitleBar(self)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.titlebar)
        lay.addWidget(self.banner)
        lay.addWidget(self.split, 1)
        lay.addWidget(self.bar)
        self.setCentralWidget(central)

        self._build_shortcuts()
        self._wire()
        self._restore_geometry()
        self.bar.setVisible(self.s["native_bar"])
        self._full = False
        self.grips = []
        if self.csd:
            self._build_grips()
        self._sync_state()

    def _build_actions(self):
        a = self.app
        self.menu_icon = themed("application-menu", "open-menu")
        self.a_back = QAction(themed("go-previous"), "Back", self)
        self.a_back.triggered.connect(self.view.back)
        self.a_fwd = QAction(themed("go-next"), "Forward", self)
        self.a_fwd.triggered.connect(self.view.forward)
        self.a_reload = QAction(themed("view-refresh"), "Reload", self)
        self.a_reload.triggered.connect(a.reload)
        self.a_home = QAction(themed("go-home"), "Home", self)
        self.a_home.triggered.connect(lambda: a.web_nav(0))
        self.a_now = QAction(themed("view-media-track", "media-album-cover"), "Now playing", self)
        self.a_now.triggered.connect(lambda: a.web_tab(None))
        self.a_search = QAction(glyph_icon("search", self.palette().text().color(), 18), "Search (Ctrl+L)", self)
        self.a_search.triggered.connect(a.focus_search)

    def build_menu(self):
        return self._build_menu()

    def _build_grips(self):
        C = Qt.CursorShape
        E = Qt.Edge
        spec = [
            (E.LeftEdge, C.SizeHorCursor), (E.RightEdge, C.SizeHorCursor),
            (E.TopEdge, C.SizeVerCursor), (E.BottomEdge, C.SizeVerCursor),
            (E.LeftEdge | E.TopEdge, C.SizeFDiagCursor), (E.RightEdge | E.BottomEdge, C.SizeFDiagCursor),
            (E.RightEdge | E.TopEdge, C.SizeBDiagCursor), (E.LeftEdge | E.BottomEdge, C.SizeBDiagCursor),
        ]
        self.grips = [EdgeGrip(self, edges, cur) for edges, cur in spec]
        self._place_grips()

    def _place_grips(self):
        if not self.grips:
            return
        w, h, t, c = self.width(), self.height(), 4, 12
        rects = [
            QRect(0, c, t, h - 2 * c), QRect(w - t, c, t, h - 2 * c),
            QRect(c, 0, w - 2 * c, t), QRect(c, h - t, w - 2 * c, t),
            QRect(0, 0, c, c), QRect(w - c, h - c, c, c),
            QRect(w - c, 0, c, c), QRect(0, h - c, c, c),
        ]
        edge = not (self.isMaximized() or self.isFullScreen())
        for g, r in zip(self.grips, rects):
            g.setGeometry(r)
            g.setVisible(edge)
            g.raise_()

    def toggle_maximized(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _sync_state(self):
        flat = self.isMaximized() or self.isFullScreen() or not self.csd
        r = 0 if flat else RADIUS
        self.titlebar.set_radius(r)
        self.bar.set_radius(r if self.s["native_bar"] else 0)
        self.titlebar.set_maximized(self.isMaximized())
        self._place_grips()

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange:
            self._sync_state()
        super().changeEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_grips()

    def _build_menu(self):
        a = self.app
        m = QMenu(self)
        m.addAction(themed("window-pip-enter"), "Mini player\tCtrl+M", a.toggle_mini)
        m.addAction(themed("view-media-lyrics"), "Lyrics panel\tCtrl+Shift+L", lambda: self.bar.lyrics_btn.toggle())
        m.addMenu(make_sleep_menu(m, a.sleep))
        m.addSeparator()
        zoom = m.addMenu("Zoom")
        zoom.addAction("Zoom in\tCtrl++", lambda: a.set_zoom(self.view.zoomFactor() + 0.1))
        zoom.addAction("Zoom out\tCtrl+-", lambda: a.set_zoom(self.view.zoomFactor() - 0.1))
        zoom.addAction("Reset\tCtrl+0", lambda: a.set_zoom(1.0))
        m.addAction(themed("view-fullscreen"), "Full screen\tF11", self.toggle_fullscreen)
        m.addSeparator()
        m.addAction(themed("configure"), "Settings…\tCtrl+,", a.open_settings)
        m.addAction(themed("help-about"), "About Cadence", a.about)
        m.addSeparator()
        m.addAction(themed("application-exit"), "Quit\tCtrl+Q", a.quit)
        return m

    def _build_shortcuts(self):
        def sc(keys, fn):
            s = QShortcut(QKeySequence(keys), self)
            s.setContext(Qt.ShortcutContext.WindowShortcut)
            s.activated.connect(fn)
        a, p = self.app, self.app.player
        sc("Alt+Left", self.view.back)
        sc("Alt+Right", self.view.forward)
        sc("F5", a.reload)
        sc("Ctrl+R", a.reload)
        sc("Ctrl+L", a.focus_search)
        sc("Ctrl+M", a.toggle_mini)
        sc("Ctrl+,", a.open_settings)
        sc("Ctrl+Q", a.quit)
        sc("F11", self.toggle_fullscreen)
        sc("Ctrl+Shift+L", lambda: self.bar.lyrics_btn.toggle())
        sc("Ctrl+Right", p.next)
        sc("Ctrl+Left", p.prev)
        sc("Ctrl+Up", lambda: p.volume_step(self.s["volume_step"]))
        sc("Ctrl+Down", lambda: p.volume_step(-self.s["volume_step"]))
        sc("Ctrl++", lambda: a.set_zoom(self.view.zoomFactor() + 0.1))
        sc("Ctrl+=", lambda: a.set_zoom(self.view.zoomFactor() + 0.1))
        sc("Ctrl+-", lambda: a.set_zoom(self.view.zoomFactor() - 0.1))
        sc("Ctrl+0", lambda: a.set_zoom(1.0))
        sc("Ctrl+B", lambda: a.web_nav(0))
        sc("Escape", lambda: self.toggle_fullscreen() if self._full else None)

    def _wire(self):
        a = self.app
        pg = a.page
        self.bar.openNowPlaying.connect(lambda: a.web_tab(None))
        self.bar.queueRequested.connect(lambda: a.web_tab(0))
        self.bar.miniRequested.connect(a.toggle_mini)
        self.bar.lyricsToggled.connect(self.set_lyrics_visible)
        self.bar.sleepRequested.connect(self._sleep_popup)
        pg.urlChanged.connect(lambda *_: self._nav_state())
        pg.loadFinished.connect(lambda *_: self._nav_state())
        pg.fullScreenRequested.connect(self._fullscreen_request)
        pg.loadingChanged.connect(self._loading_changed)
        a.player.changed.connect(self._title)
        a.settings.changed.connect(self._setting_changed)

    def _sleep_popup(self):
        m = make_sleep_menu(self, self.app.sleep)
        b = self.bar.sleep_btn
        m.exec(b.mapToGlobal(b.rect().topLeft()) - QPoint(0, m.sizeHint().height()))

    def _nav_state(self):
        h = self.app.page.history()
        self.a_back.setEnabled(h.canGoBack())
        self.a_fwd.setEnabled(h.canGoForward())

    def _loading_changed(self, info):
        from PyQt6.QtWebEngineCore import QWebEngineLoadingInfo as L
        if info.status() == L.LoadStatus.LoadFailedStatus and info.errorDomain() in (
                L.ErrorDomain.ConnectionErrorDomain, L.ErrorDomain.DnsErrorDomain, L.ErrorDomain.CertificateErrorDomain,
                L.ErrorDomain.InternalErrorDomain):
            self.app.page.setHtml(ERROR_HTML % (info.errorString() or "Check your connection."), QUrl("about:blank"))

    def _title(self):
        p = self.app.player
        if p.available:
            t = "%s — %s" % (p.display_title, p.artist) if p.artist else p.display_title
            self.setWindowTitle(("▶ " if p.playing else "") + t)
            self.titlebar.set_title(t)
        else:
            self.setWindowTitle(APP_NAME)
            self.titlebar.set_title("")

    def _setting_changed(self, key):
        if key == "native_bar":
            self.bar.setVisible(self.s["native_bar"] and not self._full)
            self._sync_state()

    def _slide_lyrics(self, show):
        want = 400
        cur = self.lyrics.width() if self.lyrics.isVisible() else 0
        if self._slide is not None:
            self._slide.stop()
        if show:
            self.lyrics.setFixedWidth(max(1, cur))
            self.lyrics.setVisible(True)
        a = QVariantAnimation(self)
        a.setDuration(360)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.setStartValue(float(cur))
        a.setEndValue(float(want if show else 0))
        a.valueChanged.connect(lambda v: self.lyrics.setFixedWidth(max(1, int(v))))
        if not show:
            a.finished.connect(lambda: self.lyrics.setVisible(False))
        self._slide = a
        a.start()

    def set_lyrics_visible(self, on):
        if self.isVisible():
            self._slide_lyrics(on)
        else:
            self.lyrics.setFixedWidth(400)
            self.lyrics.setVisible(on)
        if self.bar.lyrics_btn.isChecked() != on:
            self.bar.lyrics_btn.setChecked(on)
        self.s["lyrics_panel"] = on
        if on:
            self.app.fetch_lyrics()

    def show_banner(self, text):
        self.banner.setText(text)
        self.banner.setVisible(bool(text))

    def _fullscreen_request(self, req):
        req.accept()
        self._set_fullscreen(req.toggleOn())

    def toggle_fullscreen(self):
        self._set_fullscreen(not self._full)

    def _set_fullscreen(self, on):
        if on == self._full:
            return
        self._full = on
        self.titlebar.setVisible(not on)
        self.bar.setVisible(not on and self.s["native_bar"])
        if on:
            self.showFullScreen()
        else:
            self.showNormal()
            self.app.page.runJavaScript("document.fullscreenElement&&document.exitFullscreen()")

    def _restore_geometry(self):
        g = self.s["geometry"]
        if g:
            self.restoreGeometry(QByteArray.fromBase64(g.encode()))

    def closeEvent(self, e):
        self.s["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        if self.app.quitting:
            e.accept()
            return
        if self.s["close_to_tray"] and self.app.tray and self.app.tray.isVisible():
            e.ignore()
            self.hide()
        else:
            e.ignore()
            self.app.quit()
