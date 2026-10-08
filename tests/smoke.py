"""Headless checks that need no network, no account and no audio. Run: python3 tests/smoke.py"""
import http.server
import json
import os
import sys
import tempfile
import threading
import time

HOME = tempfile.mkdtemp(prefix="cadence-test-")
os.environ["CADENCE_HOME"] = HOME
os.environ["CADENCE_MPRIS_ID"] = "cadence_smoke"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWebEngineWidgets  # noqa: F401,E402
from PyQt6.QtCore import QCoreApplication, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(["cadence-test"])
failures = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (" " + str(extra) if (extra and not cond) else ""))
    if not cond:
        failures.append(name)


def spin(ms):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


# --- settings
from cadence import paths  # noqa: E402
from cadence.settings import DEFAULTS, Settings  # noqa: E402

paths.ensure_dirs()
s = Settings()
s["zoom"] = 1.3
s["listenbrainz_token"] = "tok"
s2 = Settings()
check("settings persist", s2["zoom"] == 1.3 and s2["listenbrainz_token"] == "tok")
check("settings file is private", oct(os.stat(paths.SETTINGS_FILE).st_mode & 0o777) == "0o600")
paths.SETTINGS_FILE.write_text('{"zoom": "bad", "unknown": 1, "close_to_tray": false}')
s3 = Settings()
check("settings reject bad types", s3["zoom"] == DEFAULTS["zoom"] and s3["close_to_tray"] is False)
paths.SETTINGS_FILE.write_text("{not json")
check("settings survive corrupt file", Settings()["zoom"] == DEFAULTS["zoom"])

# --- player model
from cadence.player import Player  # noqa: E402

p = Player()
events = []
p.trackChanged.connect(lambda: events.append("track"))
p.apply_state({"videoId": "abc", "title": "T" * 1000, "artist": "A", "duration": 100, "playing": True,
               "volume": 7, "repeat": "BOGUS", "like": "LIKE", "pos": 10})
spin(700)
check("track change debounced once", events == ["track"], events)
check("title clamped", len(p.title) == 400)
check("volume clamped, repeat sanitised", p.volume == 1.0 and p.repeat == "NONE")
t0 = p.position()
time.sleep(0.3)
check("position extrapolates while playing", p.position() > t0)
p.apply_state({"videoId": "abc", "title": "T", "artist": "A", "duration": 100, "playing": False, "pos": 20})
check("position frozen when paused", abs(p.position() - 20) < 0.05)
p.apply_state("garbage")
p.apply_state({"videoId": 5, "duration": "nan", "volume": None})
check("garbage state tolerated", True)

# --- bridge JS against a fake YouTube Music page
from cadence.bridge import Bridge  # noqa: E402
from cadence.web import CadencePage, make_profile  # noqa: E402

FAKE = """<!doctype html><title>fake</title><ytmusic-app>
<ytmusic-player-bar repeat-mode="NONE">
 <div class="previous-button"><button onclick="log('prev')"></button></div>
 <div id="play-pause-button"><button onclick="toggle()"></button></div>
 <div class="next-button"><button onclick="log('next')"></button></div>
 <div class="shuffle"><button onclick="document.querySelector('ytmusic-player-bar').toggleAttribute('shuffle-on')"></button></div>
 <div class="repeat"><button onclick="rep()"></button></div>
 <ytmusic-like-button-renderer id="like-button-renderer" like-status="INDIFFERENT"><button onclick="like('LIKE')"></button><button onclick="like('DISLIKE')"></button></ytmusic-like-button-renderer>
</ytmusic-player-bar>
<div id="movie_player"></div></ytmusic-app>
<video id=v></video>
<script>
window.cmdlog=[];
function log(x){cmdlog.push(x)}
const v=document.getElementById('v'); let paused=true;
Object.defineProperty(v,'paused',{get:()=>paused}); Object.defineProperty(v,'duration',{get:()=>200});
Object.defineProperty(v,'currentTime',{get:()=>42,set:x=>log('seek '+x)});
function toggle(){paused=!paused; v.dispatchEvent(new Event(paused?'pause':'play'))}
function rep(){const b=document.querySelector('ytmusic-player-bar');const m=['NONE','ALL','ONE'];b.setAttribute('repeat-mode',m[(m.indexOf(b.getAttribute('repeat-mode'))+1)%3])}
function like(x){document.getElementById('like-button-renderer').setAttribute('like-status',x)}
let vol=100; const mp=document.getElementById('movie_player');
mp.getVideoData=()=>({video_id:'fake123',title:'Fake',author:'Band'}); mp.getVolume=()=>vol; mp.setVolume=x=>{vol=x}; mp.isMuted=()=>false;
mp.seekTo=x=>log('seekTo '+x);
navigator.mediaSession.metadata=new MediaMetadata({title:'Fake Song',artist:'Fake Band',album:'Fake LP',artwork:[{src:'https://example.invalid/a.jpg',sizes:'60x60'},{src:'https://example.invalid/b.jpg',sizes:'544x544'}]});
</script>"""

profile = make_profile()
page = CadencePage(profile)
pl = Player()
settings = Settings()
from PyQt6.QtWebEngineCore import QWebEngineScript  # noqa: E402

sc = QWebEngineScript()
sc.setName("test-flag")
sc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
sc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
sc.setSourceCode("window.__CADENCE_TEST=true;")
page.scripts().insert(sc)
bridge = Bridge(page, pl, settings)
page.setHtml(FAKE)
spin(2500)


def js(code):
    out = []
    page.runJavaScript(code, out.append)
    spin(250)
    return out[0] if out else None


def js_on(pg, code):
    out = []
    pg.runJavaScript(code, out.append)
    spin(300)
    return out[0] if out else None


check("bridge connects to page", pl.available and pl.video_id == "fake123", (pl.video_id, pl.title))
check("metadata read from mediaSession", pl.title == "Fake Song" and pl.artist == "Fake Band" and pl.album == "Fake LP")
check("largest artwork chosen", pl.art_url.endswith("b.jpg"))
check("duration read", pl.duration == 200)
check("starts paused", not pl.playing)
pl.toggle()
spin(900)
check("play command reaches page and state returns", js("paused") is False and pl.playing)
pl.toggle_shuffle()
spin(900)
check("shuffle command reaches page", js("document.querySelector('ytmusic-player-bar').hasAttribute('shuffle-on')") is True)
pl.shuffle = False
page.runJavaScript("document.querySelector('ytmusic-player-bar').removeAttribute('shuffle-on')")
spin(900)
check("page-side shuffle change reaches model", pl.shuffle is False)
pl.cycle_repeat()
spin(900)
check("repeat command reaches page", js("document.querySelector('ytmusic-player-bar').getAttribute('repeat-mode')") == "ALL")
page.runJavaScript("document.querySelector('ytmusic-player-bar').setAttribute('repeat-mode','ONE')")
spin(900)
check("page-side repeat change reaches model", pl.repeat == "ONE", pl.repeat)
pl.toggle_like()
spin(900)
check("like command reaches page", js("document.getElementById('like-button-renderer').getAttribute('like-status')") == "LIKE")
pl.set_volume(0.3)
spin(900)
check("volume command reaches page", js("document.getElementById('movie_player').getVolume()") == 30)
pl.next()
pl.seek(55)
spin(900)
log = js("window.cmdlog.join(',')") or ""
check("next and seek reach page", "next" in log and "seekTo 55" in log, log)
page.runJavaScript("document.dispatchEvent(new Event('x'))")

# --- Google sign-in identity: JS and headers must agree on a non-embedded browser (profile-level script)
from PyQt6.QtCore import QUrl  # noqa: E402

gpage = CadencePage(profile)
gpage.setHtml("<html><body>x</body></html>", QUrl("https://accounts.google.com/v3/signin"))
spin(1500)
ident = json.loads(js_on(gpage, "JSON.stringify({ua: navigator.userAgent, uad: typeof navigator.userAgentData, chrome: typeof window.chrome})") or "{}")
check("sign-in page sees a Firefox identity", "Firefox" in ident.get("ua", "") and ident.get("uad") == "undefined", ident)
ypage = CadencePage(profile)
ypage.setHtml("<html><body>x</body></html>", QUrl("https://music.youtube.com/"))
spin(1500)
yid = json.loads(js_on(ypage, "JSON.stringify({ua: navigator.userAgent})") or "{}")
check("music.youtube.com keeps the Chrome identity", "Chrome/" in yid.get("ua", "") and "Firefox" not in yid.get("ua", ""), yid)

# --- scrobbler against a local server
from cadence import scrobble  # noqa: E402

got = []


class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        got.append((self.headers.get("Authorization"), json.loads(self.rfile.read(n))))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
scrobble.ENDPOINT = "http://127.0.0.1:%d/1/submit-listens" % srv.server_port
settings["listenbrainz_token"] = "secret-token"
settings["scrobble"] = True
sp = Player()
sb = scrobble.Scrobbler(sp, settings)
sp.apply_state({"videoId": "zzz", "title": "Song", "artist": "Band", "album": "LP", "duration": 40, "playing": True})
spin(700)
for _ in range(25):
    sb._on_tick()
spin(1200)
kinds = [g[1]["listen_type"] for g in got]
check("scrobbler sends playing_now then single", kinds[:2] == ["playing_now", "single"], kinds)
check("scrobbler sends token", all(g[0] == "Token secret-token" for g in got))
check("scrobble payload", got and got[-1][1]["payload"][0]["track_metadata"]["track_name"] == "Song")
srv.shutdown()

# --- sleep timer
from cadence.sleep import SleepTimer  # noqa: E402

sl = SleepTimer(sp)
cmds = []
sp.command.connect(lambda n, a: cmds.append(n))
sl.start(0.01)
spin(1500)
check("sleep timer pauses", "pause" in cmds and not sl.active, cmds)

# --- ui constructs
from cadence.ui.lyrics_panel import LyricsPanel  # noqa: E402
from cadence.ui.playerbar import PlayerBar  # noqa: E402
from cadence.lyrics import LyricsResult  # noqa: E402

bar = PlayerBar(pl)
bar.resize(1200, 90)
bar.show()
pl.apply_state({"videoId": "fake123", "title": "Fake Song", "artist": "Fake Band", "duration": 200, "playing": True})
spin(200)
check("player bar shows title", bar.title.text() == "Fake Song")
lp = LyricsPanel(pl)
lp.resize(320, 600)
lp.show()
lp.set_result(LyricsResult(synced=[(0.0, "one"), (5.0, "two"), (10.0, "three"), (15.0, "four")]))
spin(300)
check("lyrics panel builds lines", len(lp._lines) == 4)

print("\n%d failure(s)" % len(failures))
os._exit(1 if failures else 0)
