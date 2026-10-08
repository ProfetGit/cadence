"""Google refuses sign-in from browsers it can tell are embedded. QtWebEngine is real Chromium,
so the tells are small: no "Google Chrome" client-hint brand, an empty window.chrome and no plugins.
Present a consistent stock-Chrome identity, but only on Google's sign-in host."""
import os

MODE = os.environ.get("CADENCE_AUTH_MODE", "firefox")
CHROME_MAJOR = "140"
CHROME_FULL = "140.0.7339.225"

SEC_CH_UA = '"Chromium";v="%s", "Not=A?Brand";v="24", "Google Chrome";v="%s"' % (CHROME_MAJOR, CHROME_MAJOR)
FIREFOX_UA = b"Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"

CHROME_JS = """(function () {
  if (location.hostname !== 'accounts.google.com') return;
  const MAJOR = '%(major)s', FULL = '%(full)s';
  const brands = [{brand: 'Chromium', version: MAJOR}, {brand: 'Not=A?Brand', version: '24'}, {brand: 'Google Chrome', version: MAJOR}];
  const full = [{brand: 'Chromium', version: FULL}, {brand: 'Not=A?Brand', version: '24.0.0.0'}, {brand: 'Google Chrome', version: FULL}];
  const data = {brands: brands, mobile: false, platform: 'Linux'};
  const uad = {
    brands: brands, mobile: false, platform: 'Linux',
    getHighEntropyValues: function (hints) {
      return Promise.resolve({brands: brands, mobile: false, platform: 'Linux', platformVersion: '6.12.0',
        architecture: 'x86', bitness: '64', model: '', uaFullVersion: FULL, fullVersionList: full, wow64: false});
    },
    toJSON: function () { return data; }
  };
  try { Object.defineProperty(Navigator.prototype, 'userAgentData', {get: function () { return uad; }, configurable: true}); } catch (e) {}
  try {
    if (!window.chrome || !window.chrome.loadTimes) {
      const t0 = Date.now() / 1000;
      window.chrome = Object.assign(window.chrome || {}, {
        app: {isInstalled: false, InstallState: {DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed'},
              RunningState: {CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running'}},
        csi: function () { return {onloadT: Date.now(), startE: Date.now(), pageT: 1000, tran: 15}; },
        loadTimes: function () { return {requestTime: t0, startLoadTime: t0, commitLoadTime: t0 + 0.1, finishDocumentLoadTime: t0 + 0.3,
          finishLoadTime: t0 + 0.4, firstPaintTime: t0 + 0.2, firstPaintAfterLoadTime: 0, navigationType: 'Other',
          wasFetchedViaSpdy: true, wasNpnNegotiated: true, npnNegotiatedProtocol: 'h2', wasAlternateProtocolAvailable: false, connectionInfo: 'h2'}; }
      });
    }
  } catch (e) {}
  try {
    if (navigator.plugins.length === 0) {
      const names = ['PDF Viewer', 'Chrome PDF Viewer', 'Chromium PDF Viewer', 'Microsoft Edge PDF Viewer', 'WebKit built-in PDF'];
      const list = names.map(function (n) { return {name: n, filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 0}; });
      list.item = function (i) { return list[i] || null; };
      list.namedItem = function (n) { return list.find(function (p) { return p.name === n; }) || null; };
      list.refresh = function () {};
      Object.defineProperty(Navigator.prototype, 'plugins', {get: function () { return list; }, configurable: true});
    }
  } catch (e) {}
})();""" % {"major": CHROME_MAJOR, "full": CHROME_FULL}

FIREFOX_JS = """(function () {
  if (location.hostname !== 'accounts.google.com') return;
  const ua = 'Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0';
  const def = function (p, v) { try { Object.defineProperty(Navigator.prototype, p, {get: function () { return v; }, configurable: true}); } catch (e) {} };
  def('userAgent', ua); def('appVersion', '5.0 (X11)'); def('vendor', ''); def('userAgentData', undefined); def('productSub', '20100101');
  try { delete window.chrome; } catch (e) {}
})();"""


def page_script() -> str:
    if MODE == "firefox":
        return FIREFOX_JS
    if MODE == "none":
        return ""
    return CHROME_JS


def apply_headers(info) -> None:
    if info.requestUrl().host() != "accounts.google.com":
        return
    if MODE == "firefox":
        info.setHttpHeader(b"User-Agent", FIREFOX_UA)
        for h in (b"sec-ch-ua", b"sec-ch-ua-mobile", b"sec-ch-ua-platform"):
            info.setHttpHeader(h, b"")
    elif MODE == "chrome":
        info.setHttpHeader(b"sec-ch-ua", SEC_CH_UA.encode())
