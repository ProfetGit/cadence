import json
import logging
import time

from PyQt6.QtCore import QFile, QIODevice, QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineScript

from .player import Player

log = logging.getLogger("cadence.bridge")
JS_DIR = __import__("pathlib").Path(__file__).parent / "js"


def _read_qrc(path: str) -> str:
    f = QFile(path)
    if not f.open(QIODevice.OpenModeFlag.ReadOnly):
        return ""
    try:
        return bytes(f.readAll()).decode("utf-8", "replace")
    finally:
        f.close()


class Bridge(QObject):
    """Receives player state from the injected page script and sends it commands.

    The only slot reachable from the page is report(); it parses JSON defensively
    and never executes anything. Commands go the other way as fixed-name calls.
    """

    connectedChanged = pyqtSignal(bool)

    def __init__(self, page, player: Player, settings, parent=None):
        super().__init__(parent)
        self._page = page
        self._settings = settings
        self._player = player
        self._last_msg = 0.0
        self._connected = False
        self._channel = QWebChannel(self)
        self._channel.registerObject("cadence", self)
        page.setWebChannel(self._channel, QWebEngineScript.ScriptWorldId.MainWorld)
        self._install_script()
        player.command.connect(self.run)
        self._watch = QTimer(self)
        self._watch.setInterval(4000)
        self._watch.timeout.connect(self._check)
        self._watch.start()

    def _install_script(self):
        qwc = _read_qrc(":/qtwebchannel/qwebchannel.js")
        if not qwc:
            log.error("qwebchannel.js not found in resources; bridge disabled")
        bridge = (JS_DIR / "bridge.js").read_text(encoding="utf-8")
        s = QWebEngineScript()
        s.setName("cadence-bridge")
        s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        s.setRunsOnSubFrames(False)
        vol = self._settings["volume"]
        pre = "window.__CADENCE_VOLUME = %s;\n" % (("%.3f" % vol) if vol >= 0 else "null")
        s.setSourceCode(pre + qwc + "\n" + bridge)
        self._page.scripts().insert(s)

    @pyqtSlot(str)
    def report(self, payload):
        if len(payload) > 20000:
            return
        try:
            msg = json.loads(payload)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        self._last_msg = time.monotonic()
        if not self._connected:
            self._connected = True
            self.connectedChanged.emit(True)
        t = msg.get("t")
        if t == "state":
            self._player.apply_state(msg.get("s"))
        elif t == "pos":
            self._player.apply_position(msg.get("p"))
        elif t == "seeked":
            self._player.apply_position(msg.get("p"), seeked=True)
        elif t == "error":
            log.warning("page script error: %s", str(msg.get("m"))[:200])

    def run(self, name, arg=None):
        if not isinstance(name, str) or not name.isidentifier():
            return
        js = "window.__cadence&&window.__cadence.cmd(%s,%s)" % (json.dumps(name), json.dumps(arg))
        self._page.runJavaScript(js)

    def eval(self, js, callback=None):
        if callback:
            self._page.runJavaScript(js, callback)
        else:
            self._page.runJavaScript(js)

    def page_loaded(self):
        self._connected = False
        self._last_msg = 0.0

    def _check(self):
        url = self._page.url()
        if url.host() != "music.youtube.com":
            return
        if self._connected and time.monotonic() - self._last_msg > 30:
            pass
        self._player.connected = self._connected
