import json
import logging
import re

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
    qWebEngineVersion,
)

from . import auth, paths

log = logging.getLogger("cadence.web")

INTERNAL_SUFFIXES = (
    "music.youtube.com",
    "youtube.com",
    "accounts.youtube.com",
    "consent.youtube.com",
    "google.com",
    "accounts.google.com",
    "consent.google.com",
    "gstatic.com",
    "googleusercontent.com",
    "ggpht.com",
    "ytimg.com",
    "googlevideo.com",
)


_GOOGLE_AUTH_HOST = re.compile(r"^(accounts|consent|myaccount|families)\.google\.[a-z.]{2,6}$")


def is_internal(url: QUrl) -> bool:
    if url.scheme() in ("data", "about", "blob", "qrc"):
        return True
    h = url.host().lower()
    if any(h == s or h.endswith("." + s) for s in INTERNAL_SUFFIXES):
        return True
    return bool(_GOOGLE_AUTH_HOST.match(h))


class GoogleSignInInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        auth.apply_headers(info)


def make_profile(parent=None) -> QWebEngineProfile:
    p = QWebEngineProfile("cadence", parent)
    p.setPersistentStoragePath(str(paths.WEBENGINE))
    p.setCachePath(str(paths.CACHE / "webengine"))
    p.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
    p.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
    p.setHttpCacheMaximumSize(200 * 1024 * 1024)
    p.setSpellCheckEnabled(False)
    ua = p.httpUserAgent().replace(" QtWebEngine/%s" % qWebEngineVersion(), "")
    p.setHttpUserAgent(ua)
    p._interceptor = GoogleSignInInterceptor(p)
    p.setUrlRequestInterceptor(p._interceptor)
    s = p.settings()
    A = QWebEngineSettings.WebAttribute
    s.setAttribute(A.PlaybackRequiresUserGesture, False)
    s.setAttribute(A.FullScreenSupportEnabled, True)
    s.setAttribute(A.ScrollAnimatorEnabled, True)
    s.setAttribute(A.JavascriptCanAccessClipboard, False)
    s.setAttribute(A.LocalContentCanAccessRemoteUrls, False)
    s.setAttribute(A.ErrorPageEnabled, False)
    p.downloadRequested.connect(lambda d: d.cancel())
    return p


class _Redirector(QWebEnginePage):
    """Throwaway page that catches target=_blank / window.open and routes it."""

    def __init__(self, owner, profile):
        super().__init__(profile, owner)
        self._owner = owner

    def acceptNavigationRequest(self, url, nav_type, is_main):
        if url.scheme() in ("http", "https"):
            if url.host() == "music.youtube.com":
                self._owner.load(url)
            else:
                QDesktopServices.openUrl(url)
        self.deleteLater()
        return False


class CadencePage(QWebEnginePage):
    externalOpened = pyqtSignal(QUrl)

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.setBackgroundColor(QColor("#0f0f0f"))
        self.urlChanged.connect(self._base_color)
        code = auth.page_script()
        if code:
            sc = QWebEngineScript()
            sc.setName("cadence-auth")
            sc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            sc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            sc.setRunsOnSubFrames(True)
            sc.setSourceCode(code)
            self.profile().scripts().insert(sc)
        self.permissionRequested.connect(self._on_permission)
        self.profile().downloadRequested.connect(lambda d: d.cancel())

    def _base_color(self, url):
        dark = url.host() == "music.youtube.com" or url.scheme() in ("about", "data")
        self.setBackgroundColor(QColor("#0f0f0f") if dark else QColor("#ffffff"))

    def _on_permission(self, perm):
        try:
            perm.deny()
        except Exception:
            pass

    def acceptNavigationRequest(self, url, nav_type, is_main):
        if url.scheme() in ("file", "ftp"):
            return False
        if is_main and not is_internal(url) and url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            self.externalOpened.emit(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main)

    def createWindow(self, window_type):
        return _Redirector(self, self.profile())

    def javaScriptConsoleMessage(self, level, message, line, source):
        if log.isEnabledFor(logging.DEBUG):
            log.debug("js[%s] %s (%s:%s)", level.name, message[:200], source[-40:], line)

    def load(self, url):
        super().load(url if isinstance(url, QUrl) else QUrl(url))


def style_script(css: str) -> str:
    return """(function(){
const css = %s;
function apply(){
  try {
    if (!window.__cadenceSheet) window.__cadenceSheet = new CSSStyleSheet();
    window.__cadenceSheet.replaceSync(css);
    if (!document.adoptedStyleSheets.includes(window.__cadenceSheet))
      document.adoptedStyleSheets = [...document.adoptedStyleSheets, window.__cadenceSheet];
  } catch (e) {
    let s = document.getElementById('cadence-css');
    if (!s) { s = document.createElement('style'); s.id = 'cadence-css'; (document.head || document.documentElement).appendChild(s); }
    s.textContent = css;
  }
}
apply();
document.addEventListener('DOMContentLoaded', apply);
})();""" % json.dumps(css)


class StyleInjector(QObject):
    """Keeps one injected stylesheet script in sync with the current theme CSS."""

    SCRIPT_NAME = "cadence-style"

    def __init__(self, page: QWebEnginePage, parent=None):
        super().__init__(parent)
        self._page = page

    def set_css(self, css: str):
        scripts = self._page.scripts()
        for old in scripts.find(self.SCRIPT_NAME):
            scripts.remove(old)
        code = style_script(css)
        s = QWebEngineScript()
        s.setName(self.SCRIPT_NAME)
        s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        s.setRunsOnSubFrames(False)
        s.setSourceCode("if (location.hostname === 'music.youtube.com') {" + code + "}")
        scripts.insert(s)
        self._page.runJavaScript("if (location.hostname === 'music.youtube.com') {" + code + "}")
