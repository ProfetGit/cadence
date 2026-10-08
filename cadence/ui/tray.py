from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .menus import make_sleep_menu
from .widgets import themed


class Tray(QSystemTrayIcon):
    def __init__(self, app, icon):
        super().__init__(icon)
        self.app = app
        p = app.player
        menu = QMenu()
        self.now = QAction("Nothing playing")
        self.now.setEnabled(False)
        menu.addAction(self.now)
        menu.addSeparator()
        self.a_play = menu.addAction(themed("media-playback-start"), "Play", p.toggle)
        self.a_prev = menu.addAction(themed("media-skip-backward"), "Previous", p.prev)
        self.a_next = menu.addAction(themed("media-skip-forward"), "Next", p.next)
        self.a_like = menu.addAction(themed("rating-unrated"), "Like", p.toggle_like)
        menu.addSeparator()
        menu.addAction(themed("window-pip-enter"), "Mini player", app.toggle_mini)
        self.sleep_menu = make_sleep_menu(menu, app.sleep)
        menu.addMenu(self.sleep_menu)
        menu.addSeparator()
        menu.addAction("Show Cadence", app.show_window)
        menu.addAction(themed("configure"), "Settings…", app.open_settings)
        menu.addAction(themed("application-exit"), "Quit", app.quit)
        self.setContextMenu(menu)
        self._menu = menu
        self.activated.connect(self._activated)
        p.changed.connect(self.refresh)
        self.refresh()

    def _activated(self, reason):
        R = QSystemTrayIcon.ActivationReason
        if reason == R.Trigger:
            self.app.toggle_window()
        elif reason == R.MiddleClick:
            self.app.player.toggle()

    def refresh(self):
        p = self.app.player
        if p.available:
            line = "%s — %s" % (p.display_title, p.artist) if p.artist else p.display_title
        else:
            line = "Nothing playing"
        self.now.setText(line[:70])
        self.setToolTip(line)
        self.a_play.setText("Pause" if p.playing else "Play")
        self.a_play.setIcon(themed("media-playback-pause" if p.playing else "media-playback-start"))
        self.a_like.setText("Unlike" if p.like == "LIKE" else "Like")
        for a in (self.a_play, self.a_prev, self.a_next, self.a_like):
            a.setEnabled(p.available)
