import json
import logging
import time

from PyQt6.QtCore import QObject, QTimer, QUrl
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import APP_NAME, __version__
from .player import Player
from .settings import Settings

log = logging.getLogger("cadence.scrobble")
ENDPOINT = "https://api.listenbrainz.org/1/submit-listens"


class Scrobbler(QObject):
    """ListenBrainz: 'playing now' on track start, a listen after half the track or 4 minutes."""

    def __init__(self, player: Player, settings: Settings, parent=None):
        super().__init__(parent)
        self.p = player
        self.s = settings
        self._nam = QNetworkAccessManager(self)
        self._meta = None
        self._started = 0
        self._played = 0.0
        self._submitted = False
        self._last_pos = 0.0
        self._backlog = []
        self.status = "idle"
        player.trackChanged.connect(self._new_track)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self._retry = QTimer(self)
        self._retry.setInterval(60000)
        self._retry.timeout.connect(self._flush_backlog)
        self._retry.start()

    def enabled(self):
        return bool(self.s["scrobble"] and self.s["listenbrainz_token"].strip())

    def _track_meta(self):
        p = self.p
        m = {
            "artist_name": p.artist,
            "track_name": p.title,
            "additional_info": {
                "media_player": APP_NAME,
                "submission_client": APP_NAME,
                "submission_client_version": __version__,
                "music_service": "music.youtube.com",
                "origin_url": "https://music.youtube.com/watch?v=" + p.video_id,
                "duration_ms": int(p.duration * 1000),
            },
        }
        if p.album:
            m["release_name"] = p.album
        return m

    def _new_track(self):
        if self.p.is_ad or not self.p.title:
            self._meta = None
            return
        self._meta = self._track_meta()
        self._started = int(time.time())
        self._played = 0.0
        self._submitted = False
        self._last_pos = 0.0
        if self.enabled():
            self._post("playing_now", [{"track_metadata": self._meta}])

    def _on_tick(self):
        if not self._meta or not self.p.playing or self.p.is_ad:
            return
        pos = self.p.position()
        if self._submitted and pos < 5 and self._last_pos > max(30.0, self.p.duration - 15):
            self._started = int(time.time())
            self._played = 0.0
            self._submitted = False
        self._last_pos = pos
        self._played += 1.0
        d = self.p.duration
        if not self._submitted and d >= 30 and self._played >= min(d / 2, 240):
            self._submitted = True
            if self.enabled():
                item = {"listened_at": self._started, "track_metadata": self._meta}
                self._backlog.append(item)
                self._flush_backlog()

    def _flush_backlog(self):
        if not self._backlog or not self.enabled():
            return
        batch = self._backlog[:20]
        self._post("import" if len(batch) > 1 else "single", batch, batch)

    def _post(self, kind, payload, batch=None):
        req = QNetworkRequest(QUrl(ENDPOINT))
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        req.setRawHeader(b"Authorization", ("Token " + self.s["listenbrainz_token"].strip()).encode())
        req.setRawHeader(b"User-Agent", ("%s/%s" % (APP_NAME, __version__)).encode())
        req.setTransferTimeout(15000)
        body = json.dumps({"listen_type": kind, "payload": payload}).encode()
        reply = self._nam.post(req, body)
        reply.finished.connect(lambda: self._posted(reply, kind, batch))

    def _posted(self, reply: QNetworkReply, kind, batch):
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        err = reply.error()
        reply.deleteLater()
        ok = status == 200
        if kind != "playing_now":
            if ok:
                self._backlog = [x for x in self._backlog if x not in (batch or [])]
            elif status in (400, 401):
                self._backlog = [x for x in self._backlog if x not in (batch or [])]
                log.warning("ListenBrainz rejected submission (HTTP %s)", status)
            elif len(self._backlog) > 100:
                self._backlog = self._backlog[-100:]
        self.status = "ok" if ok else ("bad token" if status == 401 else "error: %s" % (status or err.name))
