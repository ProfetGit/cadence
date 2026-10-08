import json
import logging
import time
import logging.handlers
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import DESKTOP_ID, APP_NAME, YTM_HOME, __version__, paths
from .art import ArtCache, dominant_color
from .bridge import Bridge
from .control import ControlService
from .exports import StatusExporter
from .lyrics import LyricsProvider
from .mpris import Mpris
from .notify import Notifier
from .player import Player
from .scrobble import Scrobbler
from .settings import Settings
from .sleep import SleepTimer
from .theme import build_css
from .ui.mainwindow import MainWindow
from .ui.miniplayer import MiniPlayer
from .ui.settingsdialog import SettingsDialog
from .ui.tray import Tray
from .ui.widgets import DEFAULT_ACCENT
from .web import CadencePage, StyleInjector, make_profile

log = logging.getLogger("cadence")
ICON_SVG = Path(__file__).resolve().parent / "assets" / "cadence.svg"


def _log_uncaught(exc_type, exc, tb):
    logging.getLogger("cadence").critical("uncaught exception", exc_info=(exc_type, exc, tb))


def setup_logging(debug: bool):
    sys.excepthook = _log_uncaught
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        paths.CACHE.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(paths.LOG_FILE, maxBytes=512_000, backupCount=1)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    if debug or sys.stderr.isatty():
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


def normalise_url(raw: str) -> QUrl | None:
    u = QUrl(raw.strip())
    host = u.host().lower()
    if u.scheme() not in ("https", "http"):
        return None
    if host == "youtu.be":
        return QUrl("https://music.youtube.com/watch?v=" + u.path().lstrip("/"))
    if host in ("music.youtube.com", "www.youtube.com", "youtube.com", "m.youtube.com"):
        u.setScheme("https")
        u.setHost("music.youtube.com")
        return u
    return None


class CadenceApp(QObject):
    def __init__(self, qapp: QApplication, debug=False, hidden=False, open_url=None):
        super().__init__()
        self.qapp = qapp
        self.debug = debug
        self.quitting = False
        paths.ensure_dirs()
        self.settings = Settings()
        if self.settings["debug"]:
            self.debug = True
        setup_logging(self.debug)
        log.info("Cadence %s starting", __version__)

        self.icon = QIcon.fromTheme(DESKTOP_ID, QIcon(str(ICON_SVG)))
        qapp.setWindowIcon(self.icon)
        self.accent = QColor(DEFAULT_ACCENT)
        self.player = Player(self)
        self.profile = make_profile(self)
        self.page = CadencePage(self.profile, self)
        self.bridge = Bridge(self.page, self.player, self.settings, self)
        self.style = StyleInjector(self.page, self)
        self.art = ArtCache(self)
        self.lyrics = LyricsProvider(self)
        self.sleep = SleepTimer(self.player, self)
        self.exports = StatusExporter(self.player, self.settings, self)
        self.scrobbler = Scrobbler(self.player, self.settings, self)
        self.notifier = Notifier(self._notification_action, self)
        self._art_url = ""
        self._art_img = None
        self._pending_notify = None
        self._settings_dialog = None
        self.tray = None
        self._launch_guard = not open_url
        QTimer.singleShot(30000, self._end_launch_guard)

        self.apply_theme()
        self.window = MainWindow(self)
        self.mini = MiniPlayer(self)

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = Tray(self, self.icon)
            self.tray.show()

        self.mpris = Mpris(self.player, self.show_window, self.quit, self.open_url, self)
        try:
            self.mpris.start()
        except Exception:  # noqa: BLE001
            log.exception("MPRIS failed to start")
        self.control = ControlService(self)
        try:
            self.control.start()
        except Exception:  # noqa: BLE001
            log.exception("control service failed to start")

        self._wire()
        start = None
        if open_url:
            start = normalise_url(open_url)
        if start is None:
            start = self._restore_url()
        self.page.load(start)
        qapp.aboutToQuit.connect(self._cleanup)
        if not (hidden or self.settings["start_hidden"]) or not self.tray:
            self.window.show()
        if self.settings["lyrics_panel"] and self.settings["lyrics_enabled"]:
            self.window.set_lyrics_visible(True)

    def _restore_url(self) -> QUrl:
        last = self.settings["last_url"]
        if self.settings["restore_last"] and last:
            u = QUrl(last)
            if u.host() == "music.youtube.com" and not u.path().startswith("/watch"):
                return u
        return QUrl(YTM_HOME)

    def _wire(self):
        p = self.player
        p.playingChanged.connect(self._guard_autoplay)
        p.command.connect(self._user_command)
        p.trackChanged.connect(self._on_track)
        p.metadataChanged.connect(self._on_metadata)
        self.art.ready.connect(self._art_ready)
        p.userVolume.connect(lambda v: self.settings.set("volume", round(v, 3)))
        self.page.urlChanged.connect(self._url_changed)
        self.page.loadStarted.connect(self.bridge.page_loaded)
        self.page.loadFinished.connect(self._load_finished)
        self.page.renderProcessTerminated.connect(self._render_died)
        self.lyrics.loading.connect(lambda vid: [v.set_loading() for v in self._lyric_views()])
        for v in self._lyric_views():
            v.offsetChanged.connect(self._lyric_offset_changed)
        self.lyrics.loaded.connect(self._lyrics_loaded)
        self.settings.changed.connect(self._setting_changed)
        self._bridge_timer = QTimer(self)
        self._bridge_timer.setSingleShot(True)
        self._bridge_timer.setInterval(30000)
        self._bridge_timer.timeout.connect(self._bridge_timeout)
        self.bridge.connectedChanged.connect(self._bridge_connected)

    def _end_launch_guard(self):
        self._launch_guard = False

    def _user_command(self, name, arg=None):
        if name in ("play", "toggle", "next", "prev", "seek"):
            self._launch_guard = False

    def _guard_autoplay(self, playing):
        """YouTube Music resumes the last queue by itself on load; start paused unless told otherwise."""
        if playing and self._launch_guard and not self.settings["resume_playing"]:
            self._launch_guard = False
            log.info("page autoplayed on launch; pausing")
            self.player.pause()

    def _cleanup(self):
        self.exports.clear()
        if self.tray:
            self.tray.hide()
        self.window.view.setPage(None)
        self.page.deleteLater()

    def _setting_changed(self, key):
        if key in ("hide_web_logo", "native_bar"):
            self.apply_theme()

    def _url_changed(self, url: QUrl):
        if url.host() == "music.youtube.com":
            self.settings["last_url"] = url.toString()

    def _load_finished(self, ok):
        host = self.page.url().host()
        if ok and host == "music.youtube.com":
            self._bridge_timer.start()

    def _bridge_connected(self, ok):
        self._bridge_timer.stop()
        self.window.show_banner("")

    def _bridge_timeout(self):
        if self.page.url().host() == "music.youtube.com" and not self.bridge._connected:
            self.window.show_banner(
                "Cadence can't see the YouTube Music player. The page may have changed; the bottom bar, "
                "media keys and widgets won't respond until it does. Check the log for details.")
            log.warning("bridge never connected on %s", self.page.url().toString())

    def _render_died(self, status, code):
        log.error("web renderer died: %s (%s)", status, code)
        QTimer.singleShot(600, self.reload)

    def apply_theme(self):
        css = build_css(self.settings, self.accent)
        self.style.set_css(css)

    def refresh_accent(self):
        if self.settings["auto_accent"] and self._art_img is not None and not self._art_img.isNull():
            self.accent = dominant_color(self._art_img)
        else:
            self.accent = QColor(DEFAULT_ACCENT)
        self.window.bar.set_accent(self.accent)
        self.mini.set_accent(self.accent)
        self.window.lyrics.set_accent(self.accent)
        for v in self._lyric_views()[:1]:
            v.set_image(self._art_img)
        self.apply_theme()

    def _on_track(self):
        p = self.player
        pos, dur = p.prev_end
        name, t = p.last_cmd
        log.info("track changed -> %r | prev ended at %.0f/%.0fs | last command %r %.1fs ago",
                 p.title[:50], pos, dur, name, time.monotonic() - t if t else -1)
        self._request_art()
        if not p.is_ad and p.title:
            if self.settings["notifications"] and (
                    not self.settings["notify_only_unfocused"] or not self.window.isActiveWindow()):
                self._pending_notify = (p.video_id, p.display_title, p.artist, p.album)
                QTimer.singleShot(1300, self._flush_notify)
            self._apply_lyric_offset()
            if self.window.lyrics.isVisible() or self.mini.lyr.isVisible():
                self.fetch_lyrics()

    def _on_metadata(self):
        self._request_art()

    def _request_art(self):
        url = self.player.art_url
        if url == self._art_url:
            return
        self._art_url = url
        if not url:
            self._art_img = None
            self.window.bar.set_image(None)
            self.mini.set_image(None)
            self.refresh_accent()
            return
        self.art.request(url)

    def _art_ready(self, url, img, path):
        if url != self._art_url:
            return
        self._art_img = img
        self.window.bar.set_image(img)
        self.mini.set_image(img)
        self.refresh_accent()
        self.mpris.set_art(self.player.video_id, path)
        self.exports.set_cover(path)
        ArtCache.publish_cover(path)
        self._art_path = path
        self._flush_notify()

    def _flush_notify(self):
        pn = self._pending_notify
        if not pn or pn[0] != self.player.video_id:
            return
        self._pending_notify = None
        path = getattr(self, "_art_path", "") if self._art_img is not None else ""
        self.notifier.track(pn[1], pn[2], pn[3], path)

    def _notification_action(self, key):
        if key == "next":
            self.player.next()
        elif key == "prev":
            self.player.prev()

    def _lyric_views(self):
        return [self.window.lyrics, self.mini.lyr]

    def _offsets_file(self):
        return paths.CONFIG / "lyrics_offsets.json"

    def _apply_lyric_offset(self):
        try:
            offs = json.loads(self._offsets_file().read_text())
        except (OSError, ValueError):
            offs = {}
        v = float(offs.get(self.player.video_id, 0.0)) if isinstance(offs, dict) else 0.0
        for view in self._lyric_views():
            view.set_user_offset(v)

    def _lyric_offset_changed(self, v):
        for view in self._lyric_views():
            view.set_user_offset(v)
        f = self._offsets_file()
        try:
            offs = json.loads(f.read_text())
            if not isinstance(offs, dict):
                offs = {}
        except (OSError, ValueError):
            offs = {}
        vid = self.player.video_id
        if vid:
            if abs(v) < 0.001:
                offs.pop(vid, None)
            else:
                offs[vid] = round(v, 2)
            try:
                f.write_text(json.dumps(offs))
            except OSError:
                pass

    def fetch_lyrics(self):
        p = self.player
        if not self.settings["lyrics_enabled"]:
            for v in self._lyric_views():
                v.set_message("Lyrics are turned off in Settings.")
            return
        if not p.available or p.is_ad or not p.title:
            return
        self.lyrics.fetch(p.video_id, p.title, p.artist, p.album, p.duration)

    def _lyrics_loaded(self, vid, res):
        if vid == self.player.video_id:
            for v in self._lyric_views():
                v.set_result(res)

    def web_nav(self, index):
        if self.page.url().host() != "music.youtube.com":
            self.page.load(QUrl(YTM_HOME))
        else:
            self.bridge.run("nav", index)

    def web_tab(self, tab):
        self.bridge.run("playerPage", tab)

    def focus_search(self):
        self.show_window()
        self.window.view.setFocus()
        self.bridge.run("focusSearch")

    def reload(self):
        if self.page.url().host() in ("", "about"):
            self.page.load(QUrl(YTM_HOME))
        else:
            self.page.triggerAction(CadencePage.WebAction.Reload)

    def set_zoom(self, z):
        z = round(max(0.5, min(3.0, z)), 2)
        self.window.view.setZoomFactor(z)
        self.settings["zoom"] = z

    def clear_cache(self):
        self.profile.clearHttpCache()

    def sign_out(self):
        self.profile.cookieStore().deleteAllCookies()
        self.profile.clearHttpCache()
        self.page.load(QUrl(YTM_HOME))

    def open_path(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_url(self, raw):
        u = normalise_url(raw)
        if u is None:
            log.warning("refused to open %r", raw[:100])
            return
        self._launch_guard = False
        self.page.load(u)
        self.show_window()

    def about(self):
        QMessageBox.about(
            self.window, "About " + APP_NAME,
            "<b>%s %s</b><br>YouTube Music for Linux, in a native Qt shell.<br><br>"
            "Unofficial; not affiliated with Google or YouTube." % (APP_NAME, __version__))

    def open_settings(self):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self, self.window)
        self._settings_dialog.show()
        self._settings_dialog.raise_()

    def show_window(self):
        w = self.window
        if w.isMinimized():
            w.showNormal()
        w.show()
        w.raise_()
        w.activateWindow()

    def toggle_window(self):
        w = self.window
        if w.isVisible() and not w.isMinimized() and w.isActiveWindow():
            w.hide()
        else:
            self.show_window()

    def toggle_mini(self):
        if self.mini.isVisible():
            self.mini.hide()
        else:
            self.mini.show()
            self.mini.raise_()

    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        self.window.close()
        self.qapp.quit()

    @staticmethod
    def _rel(arg: str, current: float, scale=1.0):
        arg = arg.strip()
        if arg[:1] in "+-" and len(arg) > 1:
            return current + float(arg) * scale
        return float(arg) * scale

    def handle_command(self, name: str, arg: str = "") -> str:
        p = self.player
        name = name.strip().lower()
        try:
            if name in ("play",):
                p.play()
            elif name in ("pause",):
                p.pause()
            elif name in ("toggle", "play-pause", "playpause"):
                p.toggle()
            elif name == "stop":
                p.stop()
            elif name in ("next",):
                p.next()
            elif name in ("prev", "previous"):
                p.prev()
            elif name == "like":
                p.toggle_like()
            elif name == "dislike":
                p.toggle_dislike()
            elif name == "shuffle":
                p.toggle_shuffle()
            elif name == "repeat":
                p.set_repeat(arg.upper()) if arg else p.cycle_repeat()
            elif name == "mute":
                p.toggle_mute()
            elif name == "volume":
                if not arg:
                    return str(round(p.volume * 100))
                p.set_volume(self._rel(arg, p.volume * 100) / 100.0)
            elif name == "seek":
                p.seek(self._rel(arg, p.position()))
            elif name == "show":
                self.show_window()
            elif name == "hide":
                self.window.hide()
            elif name in ("toggle-window", "window"):
                self.toggle_window()
            elif name == "mini":
                self.toggle_mini()
            elif name in ("maximize", "maximise"):
                self.window.toggle_maximized()
            elif name == "lyrics":
                self.window.bar.lyrics_btn.toggle()
            elif name == "settings":
                self.open_settings()
            elif name == "reload":
                self.reload()
            elif name == "search":
                self.focus_search()
            elif name == "sleep":
                a = arg.strip().lower()
                if a in ("", "off", "cancel"):
                    self.sleep.cancel()
                elif a in ("track", "end"):
                    self.sleep.start_end_of_track()
                else:
                    self.sleep.start(float(a))
            elif name == "open":
                self.open_url(arg)
            elif name == "quit":
                QTimer.singleShot(0, self.quit)
            elif name == "status":
                return json.dumps(p.status())
            else:
                return "error: unknown command %r" % name
        except (ValueError, TypeError) as e:
            return "error: %s" % e
        return "ok"
