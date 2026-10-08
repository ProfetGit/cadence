import colorsys
import hashlib
import logging
import math
import re
import shutil

from PyQt6.QtCore import QObject, QRect, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import APP_NAME, __version__, paths

log = logging.getLogger("cadence.art")

_SIZE = 600


def upscale_url(url: str) -> str:
    if "googleusercontent.com" in url or "ggpht.com" in url:
        url = re.sub(r"=w\d+-h\d+", "=w%d-h%d" % (_SIZE, _SIZE), url)
        url = re.sub(r"=s\d+", "=s%d" % _SIZE, url)
    return url


def _video_thumb_candidates(url: str):
    m = re.match(r"(https://i\.ytimg\.com/vi/[^/]+/)[a-z0-9]+\.jpg", url)
    if m:
        return [m.group(1) + "maxresdefault.jpg", url]
    return [url]


def crop_square(img: QImage, video_thumb: bool) -> QImage:
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return img
    if video_thumb:
        inner_h = h
        if h / w > 0.62:
            inner_h = int(w * 9 / 16)
        top = (h - inner_h) // 2
        side = inner_h
        left = (w - side) // 2
        return img.copy(QRect(left, top, side, side))
    side = min(w, h)
    return img.copy(QRect((w - side) // 2, (h - side) // 2, side, side))


def dominant_color(img: QImage) -> QColor:
    small = img.scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    small = small.convertToFormat(QImage.Format.Format_RGB32)
    sx = sy = tw = 0.0
    sat = val = 0.0
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            h, s, v = colorsys.rgb_to_hsv(c.redF(), c.greenF(), c.blueF())
            wgt = (s * s) * (0.25 + v) + 0.002
            sx += math.cos(h * 2 * math.pi) * wgt
            sy += math.sin(h * 2 * math.pi) * wgt
            sat += s * wgt
            val += v * wgt
            tw += wgt
    if tw <= 0:
        return QColor("#9a9a9a")
    hue = (math.atan2(sy, sx) / (2 * math.pi)) % 1.0
    s = max(0.0, min(1.0, sat / tw))
    if s < 0.12:
        return QColor("#b8b8b8")
    s = max(0.45, min(0.85, s))
    return QColor.fromHsvF(hue, s, 0.9)


class ArtCache(QObject):
    """Fetches cover art, squares it, caches to disk, and reports the result."""

    ready = pyqtSignal(str, QImage, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._mem = {}
        self._inflight = set()

    def _cache_path(self, url):
        return paths.ART_CACHE / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".jpg")

    def request(self, url: str):
        if not url.startswith("https://"):
            return
        if url in self._mem:
            img, path = self._mem[url]
            QTimer.singleShot(0, lambda: self.ready.emit(url, img, path))
            return
        cp = self._cache_path(url)
        if cp.exists():
            img = QImage(str(cp))
            if not img.isNull():
                self._mem[url] = (img, str(cp))
                QTimer.singleShot(0, lambda: self.ready.emit(url, img, str(cp)))
                return
        if url in self._inflight:
            return
        self._inflight.add(url)
        self._fetch(url, _video_thumb_candidates(upscale_url(url)), url)

    def _fetch(self, original, candidates, key):
        if not candidates:
            self._inflight.discard(key)
            return
        req = QNetworkRequest(QUrl(candidates[0]))
        req.setRawHeader(b"User-Agent", ("%s/%s" % (APP_NAME, __version__)).encode())
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        req.setTransferTimeout(15000)
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._done(reply, original, candidates, key))

    def _done(self, reply: QNetworkReply, original, candidates, key):
        data = bytes(reply.readAll())
        ok = reply.error() == QNetworkReply.NetworkError.NoError
        reply.deleteLater()
        img = QImage()
        if ok:
            img.loadFromData(data)
        is_thumb = "i.ytimg.com/vi/" in original
        if img.isNull() or (is_thumb and candidates[0].endswith("maxresdefault.jpg") and img.width() < 400):
            self._fetch(original, candidates[1:], key)
            return
        img = crop_square(img, is_thumb)
        cp = self._cache_path(key)
        try:
            img.save(str(cp), "JPEG", 90)
        except Exception:
            log.debug("could not write art cache", exc_info=True)
        self._inflight.discard(key)
        if len(self._mem) > 40:
            self._mem.pop(next(iter(self._mem)))
        self._mem[key] = (img, str(cp))
        self.ready.emit(key, img, str(cp))

    @staticmethod
    def publish_cover(path: str):
        try:
            paths.RUNTIME.mkdir(parents=True, exist_ok=True)
            tmp = paths.COVER_FILE.with_suffix(".tmp")
            shutil.copyfile(path, tmp)
            tmp.replace(paths.COVER_FILE)
        except OSError:
            pass
