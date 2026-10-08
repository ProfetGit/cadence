import os
import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from .. import paths


def _autostart_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / "cadence.desktop"


def set_autostart(on: bool):
    f = _autostart_file()
    if not on:
        try:
            f.unlink()
        except OSError:
            pass
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    exe = shutil.which("cadence-music") or shutil.which("cadence") or str(Path.home() / ".local/bin/cadence")
    f.write_text(
        "[Desktop Entry]\nType=Application\nName=Cadence\nComment=YouTube Music for Linux\n"
        f"Exec={exe} --hidden\nIcon=cadence\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"
    )


class SettingsDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.s = app.settings
        self.setWindowTitle("Cadence Settings")
        self.setMinimumWidth(480)
        tabs = QTabWidget()
        tabs.addTab(self._general(), "General")
        tabs.addTab(self._appearance(), "Appearance")
        tabs.addTab(self._integrations(), "Integrations")
        tabs.addTab(self._data(), "Account && data")
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(close)

    def _bind_check(self, key, text, tip="", after=None):
        c = QCheckBox(text)
        c.setChecked(self.s[key])
        if tip:
            c.setToolTip(tip)

        def toggled(v):
            self.s[key] = v
            if after:
                after(v)
        c.toggled.connect(toggled)
        return c

    def _general(self):
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(self._bind_check("close_to_tray", "Keep playing in the tray when the window is closed"))
        f.addWidget(self._bind_check("start_hidden", "Start minimised to the tray"))
        f.addWidget(self._bind_check("autostart", "Start Cadence when I log in", after=set_autostart))
        f.addWidget(self._bind_check("restore_last", "Reopen the page I was on"))
        f.addWidget(self._bind_check("resume_playing", "Let YouTube Music resume playing by itself when Cadence starts"))
        f.addWidget(self._bind_check("notifications", "Show a notification when the track changes"))
        f.addWidget(self._bind_check("notify_only_unfocused", "…but only when Cadence isn't the focused window"))
        row = QFormLayout()
        step = QSpinBox()
        step.setRange(1, 25)
        step.setSuffix(" %")
        step.setValue(self.s["volume_step"])
        step.valueChanged.connect(lambda v: self.s.set("volume_step", v))
        row.addRow("Volume step (Ctrl+Up/Down)", step)
        f.addLayout(row)
        f.addStretch()
        return w

    def _appearance(self):
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(self._bind_check("native_bar", "Use the native player bar (hides YouTube Music's own)",
                                     after=lambda v: self.app.apply_theme()))
        f.addWidget(self._bind_check("custom_titlebar", "Use Cadence's own title bar, with rounded corners (restart to apply)"))
        f.addWidget(self._bind_check("hide_web_logo", "Hide the YouTube Music logo in the top bar",
                                     after=lambda v: self.app.apply_theme()))
        f.addWidget(self._bind_check("auto_accent", "Tint the interface with the album colour",
                                     after=lambda v: self.app.refresh_accent()))
        form = QFormLayout()
        zoom = QDoubleSpinBox()
        zoom.setRange(0.5, 2.5)
        zoom.setSingleStep(0.1)
        zoom.setValue(self.s["zoom"])
        zoom.valueChanged.connect(lambda v: self.app.set_zoom(v))
        form.addRow("Page zoom", zoom)
        f.addLayout(form)
        f.addStretch()
        return w

    def _integrations(self):
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(QLabel("<b>Desktop</b>"))
        f.addWidget(self._bind_check("status_file", "Write now-playing.json and cover.jpg for widgets",
                                     tip=str(paths.STATUS_FILE)))
        info = QLabel("MPRIS is always on: Plasma's media widget, lock screen, KDE Connect and media keys "
                      "control Cadence automatically.")
        info.setWordWrap(True)
        info.setStyleSheet("color: palette(placeholder-text);")
        f.addWidget(info)
        f.addWidget(QLabel("<b>Lyrics</b>"))
        f.addWidget(self._bind_check(
            "lyrics_enabled", "Fetch synced lyrics from LRCLIB when the lyrics panel is open",
            tip="Sends the track title, artist, album and length to lrclib.net"))
        f.addWidget(QLabel("<b>ListenBrainz scrobbling</b>"))
        f.addWidget(self._bind_check("scrobble", "Submit what I listen to"))
        form = QFormLayout()
        tok = QLineEdit(self.s["listenbrainz_token"])
        tok.setEchoMode(QLineEdit.EchoMode.Password)
        tok.setPlaceholderText("User token from listenbrainz.org/settings")
        tok.editingFinished.connect(lambda: self.s.set("listenbrainz_token", tok.text().strip()))
        form.addRow("Token", tok)
        f.addLayout(form)
        f.addStretch()
        return w

    def _data(self):
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(QLabel("Sign-in lives in YouTube Music's own account menu (top right of the page)."))
        for text, fn in (
            ("Open config folder", lambda: self.app.open_path(paths.CONFIG)),
            ("Open log file", lambda: self.app.open_path(paths.LOG_FILE)),
            ("Clear web cache", self.app.clear_cache),
            ("Sign out and clear cookies…", self._sign_out),
        ):
            b = QPushButton(text)
            b.clicked.connect(fn)
            f.addWidget(b)
        f.addStretch()
        return w

    def _sign_out(self):
        r = QMessageBox.question(
            self, "Sign out", "Delete all YouTube Music cookies and sign out of Google in Cadence?")
        if r == QMessageBox.StandardButton.Yes:
            self.app.sign_out()
