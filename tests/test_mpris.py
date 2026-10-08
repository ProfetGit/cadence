import os
import subprocess
import sys

os.environ["CADENCE_MPRIS_ID"] = "cadence_test"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QCoreApplication, QTimer

from cadence.mpris import Mpris, MPRIS_NAME
from cadence.player import Player

app = QCoreApplication([])
player = Player()
cmds = []
player.command.connect(lambda n, a: cmds.append((n, a)))
m = Mpris(player, lambda: cmds.append(("raise", None)), lambda: cmds.append(("quit", None)),
          lambda u: cmds.append(("open", u)))
m.start()

results = []


def bus(*a):
    r = subprocess.run(["busctl", "--user", *a], capture_output=True, text=True, timeout=5)
    return (r.stdout + r.stderr).strip()


def step1():
    player.apply_state({"videoId": "ab-CD_12345", "title": "Song", "artist": "Band", "album": "LP",
                        "art": "https://lh3.googleusercontent.com/x=w60-h60", "duration": 200.5,
                        "playing": True, "volume": 0.5, "repeat": "ALL", "like": "LIKE", "pos": 12})


def step2():
    base = [MPRIS_NAME, "/org/mpris/MediaPlayer2"]
    P = "org.mpris.MediaPlayer2.Player"
    results.append(("status", bus("get-property", *base, P, "PlaybackStatus")))
    results.append(("loop", bus("get-property", *base, P, "LoopStatus")))
    results.append(("volume", bus("get-property", *base, P, "Volume")))
    results.append(("meta", bus("get-property", *base, P, "Metadata")))
    results.append(("pos", bus("get-property", *base, P, "Position")))
    bus("call", *base, P, "PlayPause")
    bus("call", *base, P, "Next")
    bus("call", *base, P, "Seek", "x", "5000000")
    bus("call", *base, P, "SetPosition", "ox", "/org/cadence/track/ab_CD_12345", "30000000")
    bus("set-property", *base, P, "Volume", "d", "0.25")
    bus("set-property", *base, P, "LoopStatus", "s", "Track")
    bus("set-property", *base, P, "Shuffle", "b", "true")
    results.append(("identity", bus("get-property", *base, "org.mpris.MediaPlayer2", "Identity")))


QTimer.singleShot(200, step1)
QTimer.singleShot(600, lambda: __import__("threading").Thread(target=step2).start())
QTimer.singleShot(3500, app.quit)
app.exec()

for k, v in results:
    print(k, "=>", v)
print("cmds:", cmds)
want = {("toggle", None), ("next", None)}
assert want <= set(cmds), cmds
assert any(c[0] == "seek" for c in cmds)
assert ("volume", 0.25) in cmds
print("MPRIS OK")
