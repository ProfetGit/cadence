import json
import logging
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlencode

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import APP_NAME, __version__, paths

log = logging.getLogger("cadence.lyrics")

API = "https://lrclib.net/api"
DEMO_LINES = [
    "Should auld acquaintance be forgot,", "and never brought to mind?", "Should auld acquaintance be forgot,",
    "and auld lang syne?", "For auld lang syne, my dear,", "for auld lang syne,",
    "we'll tak a cup o' kindness yet,", "for auld lang syne.", "And surely ye'll be your pint-stoup!",
    "and surely I'll be mine!", "And we'll tak a cup o' kindness yet,", "for auld lang syne.",
    "We two hae run about the braes,", "and pou'd the gowans fine;", "But we've wander'd mony a weary fit,",
    "sin' auld lang syne.", "We two hae paidl'd in the burn,", "frae morning sun till dine;",
    "But seas between us braid hae roar'd", "sin' auld lang syne.",
]
_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*(official|video|audio|lyric|visuali[sz]er|remaster|hd\b|hq\b|4k|\bmv\b|explicit|"
    r"music video|clip)[^\)\]]*[\)\]]",
    re.I,
)
_LRC = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


@dataclass
class LyricsResult:
    synced: list = field(default_factory=list)
    plain: str = ""
    source: str = "LRCLIB"

    @property
    def found(self):
        return bool(self.synced or self.plain)

    @property
    def valid(self):
        """Community data contains junk entries like a single 'probe' line; skip those."""
        if self.plain.startswith("♪"):
            return True
        return len(self.synced) >= 4 or len([l for l in self.plain.splitlines() if l.strip()]) >= 4


def clean_title(t: str) -> str:
    t = _NOISE.sub("", t)
    t = re.sub(r"\s*[\(\[]\s*(feat|ft|with)\.?[^\)\]]*[\)\]]", "", t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip(" -–")


def clean_artist(a: str) -> str:
    a = re.sub(r"\s*-\s*Topic$", "", a, flags=re.I)
    return a.split(" • ")[0].split(",")[0].strip()


def parse_lrc(text: str):
    out = []
    for line in text.splitlines():
        stamps = _LRC.findall(line)
        if not stamps:
            continue
        body = _LRC.sub("", line).strip()
        for m, s in stamps:
            out.append((int(m) * 60 + float(s), body))
    out.sort(key=lambda x: x[0])
    return out


class LyricsProvider(QObject):
    loading = pyqtSignal(str)
    loaded = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._token = 0
        self._current = ""

    def fetch(self, video_id, title, artist, album, duration):
        self._token += 1
        token = self._token
        self._current = video_id
        cached = self._read_cache(video_id)
        if cached is not None:
            QTimer.singleShot(0, lambda: self.loaded.emit(video_id, cached))
            return
        if os.environ.get("CADENCE_DEMO_LYRICS"):
            lines = DEMO_LINES
            res = LyricsResult(synced=[(4.0 + i * 5.2, x) for i, x in enumerate(lines)], plain="\n".join(lines))
            QTimer.singleShot(250, lambda: self.loaded.emit(video_id, res))
            return
        self.loading.emit(video_id)
        t, a = clean_title(title), clean_artist(artist)
        queries = [("get", dict(track_name=t, artist_name=a, album_name=album, duration=int(duration)))]
        queries.append(("get", dict(track_name=t, artist_name=a, duration=int(duration))))
        if " - " in t:
            left, right = [x.strip() for x in t.split(" - ", 1)]
            queries.append(("get", dict(track_name=right, artist_name=left, duration=int(duration))))
        queries.append(("search", dict(track_name=t, artist_name=a)))
        queries.append(("search", dict(q=("%s %s" % (a, t)).strip())))
        base = re.sub(r"\s*\([^)]*\)", "", t).strip()
        head = base.split(" - ")[0].strip()
        tail = re.sub(r"[:\-].*$", "", base.split(" - ", 1)[1]).strip() if " - " in base else ""
        for q in dict.fromkeys(x for x in (("%s %s" % (head, tail)).strip(), base, t) if x):
            queries.append(("search", dict(q=q, _tol=15)))
        self._run(video_id, token, queries, duration)

    def _run(self, vid, token, queries, duration):
        if token != self._token:
            return
        if not queries:
            res = LyricsResult()
            self._write_cache(vid, res)
            self.loaded.emit(vid, res)
            return
        kind, params = queries[0]
        tol = params.get("_tol", 4)
        params = {k: v for k, v in params.items() if v not in ("", None) and k != "_tol"}
        req = QNetworkRequest(QUrl("%s/%s?%s" % (API, kind, urlencode(params))))
        req.setRawHeader(b"User-Agent", ("%s/%s" % (APP_NAME, __version__)).encode())
        req.setTransferTimeout(10000)
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._reply(reply, vid, token, kind, queries[1:], duration, tol))

    def _reply(self, reply: QNetworkReply, vid, token, kind, rest, duration, tol=4):
        data = bytes(reply.readAll())
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        net_err = reply.error() != QNetworkReply.NetworkError.NoError and status is None
        reply.deleteLater()
        if token != self._token:
            return
        if net_err:
            self.loaded.emit(vid, None)
            return
        item = None
        try:
            obj = json.loads(data.decode("utf-8", "replace")) if status == 200 else None
        except ValueError:
            obj = None
        if kind == "get" and isinstance(obj, dict):
            item = obj
        elif kind == "search" and isinstance(obj, list):
            item = self._best(obj, duration, tol)
        res = self._to_result(item) if item else None
        if res and res.valid:
            self._write_cache(vid, res)
            self.loaded.emit(vid, res)
        else:
            self._run(vid, token, rest, duration)

    @staticmethod
    def _best(items, duration, tol=4):
        best, score = None, -1
        for it in items:
            if not isinstance(it, dict) or it.get("instrumental"):
                continue
            d = it.get("duration") or 0
            if duration and abs(d - duration) > tol:
                continue
            cand = LyricsProvider._to_result(it)
            if not cand.valid:
                continue
            sc = (1000 if cand.synced else 0) + len(cand.synced or cand.plain.splitlines())
            if sc > score:
                best, score = it, sc
        return best

    @staticmethod
    def _to_result(it):
        if it.get("instrumental"):
            return LyricsResult(plain="♪ Instrumental ♪")
        synced = parse_lrc(it.get("syncedLyrics") or "")
        plain = it.get("plainLyrics") or ""
        return LyricsResult(synced=synced, plain=plain)

    def _cache_file(self, vid):
        return paths.LYRICS_CACHE / (re.sub(r"[^A-Za-z0-9_-]", "_", vid) + ".json")

    def _read_cache(self, vid):
        try:
            d = json.loads(self._cache_file(vid).read_text())
            return LyricsResult([tuple(x) for x in d["synced"]], d["plain"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _write_cache(self, vid, res: LyricsResult):
        try:
            self._cache_file(vid).write_text(json.dumps({"synced": res.synced, "plain": res.plain}))
        except OSError:
            pass
