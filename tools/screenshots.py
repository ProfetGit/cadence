"""Renders the README screenshots from the real UI with synthetic demo state (no account, no audio).

Run:  CADENCE_HOME=<throwaway dir> QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME=kde \\
      CADENCE_DEMO_LYRICS=1 CADENCE_ALLOW_MULTI=1 CADENCE_BUS_SUFFIX=Demo CADENCE_MPRIS_ID=cadence_demo \\
      python3 tools/screenshots.py <outdir>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWebEngineWidgets  # noqa: F401,E402
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter, QRadialGradient  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(out, exist_ok=True)
qapp = QApplication(["cadence-shots"])
qapp.setApplicationName("Cadence")
qapp.setDesktopFileName("cadence")
qapp.setQuitOnLastWindowClosed(False)

from cadence.app import CadenceApp  # noqa: E402


def cover(size=600):
    img = QImage(size, size, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#2b1055"))
    g.setColorAt(0.55, QColor("#7597de"))
    g.setColorAt(1, QColor("#ff6a88"))
    p.fillRect(img.rect(), g)
    r = QRadialGradient(size * 0.7, size * 0.3, size * 0.5)
    r.setColorAt(0, QColor(255, 220, 160, 230))
    r.setColorAt(1, QColor(255, 220, 160, 0))
    p.fillRect(img.rect(), r)
    p.end()
    return img


app = CadenceApp(qapp, debug=True)
_apply = app.player.apply_state
app.player.apply_state = lambda st: _apply(st) if str(st.get("videoId", "")).startswith("demo") else None
app.window.resize(1280, 820)
app.window.show()


def demo_state():
    app.player.apply_state({
        "videoId": "demo0000001", "title": "Midnight Cadence", "artist": "Demo Artist", "album": "Open Source",
        "art": "https://example.invalid/cover.jpg", "duration": 214.0, "playing": True, "volume": 0.6,
        "repeat": "NONE", "shuffle": False, "like": "LIKE", "pos": 13.0,
    })
    app._art_url = "https://example.invalid/cover.jpg"
    img = cover()
    cover_path = os.path.join(out, "cover.jpg")
    img.save(cover_path, "JPEG", 90)
    app._art_ready("https://example.invalid/cover.jpg", img, cover_path)
    app.window.set_lyrics_visible(True)
    app.window.lyrics.set_user_offset(0.0)
    app.fetch_lyrics()


def shoot(name, widget):
    widget.grab().save(os.path.join(out, name))


def step1():
    demo_state()
    app.toggle_mini()


QTimer.singleShot(11000, step1)
QTimer.singleShot(16000, lambda: (shoot("main.png", app.window), shoot("mini.png", app.mini)))
QTimer.singleShot(16500, lambda: (app.open_settings(), None))
QTimer.singleShot(17500, lambda: shoot("settings.png", app._settings_dialog))
QTimer.singleShot(18000, lambda: None if os.environ.get("CADENCE_SHOTS_HOLD") else os._exit(0))
sys.exit(qapp.exec())
