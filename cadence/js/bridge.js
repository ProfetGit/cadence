(function () {
  'use strict';
  if (window.__cadence_boot) return;
  if (location.hostname !== 'music.youtube.com' && !window.__CADENCE_TEST) return;
  window.__cadence_boot = true;

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const player = () => $('#movie_player');
  const bar = () => $('ytmusic-player-bar');
  const video = () => $('video');

  // Signed-in accounts get a newer UI (ytmusic-miniplayer) with unlabelled-by-id buttons.
  // Map them by position around the play button (the first "Tonal" button).
  function mini() {
    const m = $('ytmusic-miniplayer');
    if (!m) return null;
    const bs = $$('button', m);
    const i = bs.findIndex(function (b) { return /Tonal/.test(b.className); });
    if (i < 2) return null;
    return {
      shuffle: bs[0], prev: bs[i - 1], play: bs[i], next: bs[i + 2], repeat: bs[i + 3],
      like: bs[i + 4], dislike: bs[i + 5], mute: bs[i + 6],
      slider: $('input[type=range]:not([class*=ProgressBar])', m)
    };
  }
  const pressed = function (b) { return !!b && b.getAttribute('aria-pressed') === 'true'; };

  let py = null;
  const pending = [];
  function send(obj) {
    const s = JSON.stringify(obj);
    if (py) py.report(s); else pending.push(s);
  }
  function connect() {
    if (typeof QWebChannel === 'undefined' || !window.qt || !qt.webChannelTransport) {
      setTimeout(connect, 150);
      return;
    }
    new QWebChannel(qt.webChannelTransport, function (ch) {
      py = ch.objects.cadence;
      pending.splice(0).forEach(function (s) { py.report(s); });
      last = '';
      tick(true);
    });
  }

  function pickArt(md) {
    if (!md || !md.artwork || !md.artwork.length) return '';
    let best = md.artwork[md.artwork.length - 1], bw = -1;
    md.artwork.forEach(function (a) {
      const w = parseInt(String(a.sizes || '0x0').split('x')[0], 10) || 0;
      if (w >= bw) { bw = w; best = a; }
    });
    return best.src || '';
  }

  function disabled(el) {
    return !el || el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true';
  }

  function shuffleState(b) {
    return b ? b.hasAttribute('shuffle-on') : null;
  }

  function snapshot() {
    const v = video(), b = bar(), mp = player();
    const md = navigator.mediaSession && navigator.mediaSession.metadata;
    let vd = null;
    try { vd = mp && mp.getVideoData && mp.getVideoData(); } catch (e) { /* not ready */ }
    const like = b && $('ytmusic-like-button-renderer', b);
    let vol = 1, muted = false;
    try {
      if (mp && mp.getVolume) { vol = mp.getVolume() / 100; muted = !!(mp.isMuted && mp.isMuted()); }
      else if (v) { vol = v.volume; muted = v.muted; }
    } catch (e) { /* ignore */ }
    const m = mini();
    let repeat = (b && b.getAttribute('repeat-mode')) || 'NONE';
    let shuffle = shuffleState(b), likeState = (like && like.getAttribute('like-status')) || 'INDIFFERENT';
    let canNext = b ? !disabled($('.next-button', b)) : true, canPrev = b ? !disabled($('.previous-button', b)) : true;
    if (m && !b) {
      repeat = pressed(m.repeat) ? (/\b1\b|yksi|one|track|kappale/i.test(m.repeat.getAttribute('aria-label') || '') ? 'ONE' : 'ALL') : 'NONE';
      shuffle = pressed(m.shuffle);
      likeState = pressed(m.like) ? 'LIKE' : (pressed(m.dislike) ? 'DISLIKE' : 'INDIFFERENT');
      canNext = !disabled(m.next);
      canPrev = !disabled(m.prev);
    }
    return {
      videoId: (vd && vd.video_id) || '',
      title: md ? md.title : ((vd && vd.title) || ''),
      artist: md ? md.artist : ((vd && vd.author) || ''),
      album: md ? md.album : '',
      art: pickArt(md),
      duration: v && isFinite(v.duration) ? v.duration : 0,
      playing: !!v && !v.paused && !v.ended,
      volume: vol,
      muted: muted,
      repeat: repeat,
      shuffle: shuffle,
      like: likeState,
      isAd: !!(mp && mp.classList.contains('ad-showing')),
      isVideo: !!(b && b.hasAttribute('is-video')),
      canNext: canNext,
      canPrev: canPrev,
      url: location.pathname + location.search
    };
  }

  let desiredVolume = (typeof window.__CADENCE_VOLUME === 'number') ? window.__CADENCE_VOLUME : null;
  function applyDesiredVolume() {
    if (desiredVolume === null) return;
    const mp = player();
    try {
      if (mp && mp.getVolume && Math.abs(mp.getVolume() / 100 - desiredVolume) > 0.01) cmds.volume(desiredVolume);
    } catch (e) { /* ignore */ }
  }
  ['loadstart', 'play', 'loadedmetadata'].forEach(function (ev) {
    document.addEventListener(ev, applyDesiredVolume, true);
  });

  let last = '';
  let lastPosSent = 0;
  function tick(force) {
    if (!py && !force) return;
    let s;
    try { s = snapshot(); } catch (e) { return; }
    const key = JSON.stringify(s);
    const v = video();
    const now = Date.now();
    if (key !== last) {
      last = key;
      s.pos = v ? v.currentTime : 0;
      lastPosSent = now;
      send({ t: 'state', s: s });
    } else if (v && !v.paused && now - lastPosSent > 500) {
      lastPosSent = now;
      send({ t: 'pos', p: v.currentTime });
    }
  }

  ['play', 'pause', 'playing', 'ended', 'loadedmetadata', 'durationchange', 'volumechange', 'emptied'].forEach(function (ev) {
    document.addEventListener(ev, function () { tick(); }, true);
  });
  document.addEventListener('seeked', function (e) {
    if (e.target && e.target.tagName === 'VIDEO') {
      lastPosSent = Date.now();
      send({ t: 'seeked', p: e.target.currentTime });
    }
  }, true);
  setInterval(tick, 400);

  function click(el) {
    if (!el) return false;
    const b = (el.tagName === 'BUTTON' ? el : $('button', el)) || el;
    b.click();
    return true;
  }

  const cmds = {
    toggle: function () { const m = mini(); if (m && !bar()) click(m.play); else click($('#play-pause-button', bar())); },
    play: function () { const v = video(); if (v && v.paused) cmds.toggle(); },
    pause: function () { const v = video(); if (v && !v.paused) cmds.toggle(); },
    next: function () { const m = mini(); if (m && !bar()) click(m.next); else click($('.next-button', bar())); },
    prev: function () { const m = mini(); if (m && !bar()) click(m.prev); else click($('.previous-button', bar())); },
    seek: function (sec) {
      const mp = player();
      if (mp && mp.seekTo) mp.seekTo(sec, true);
      else { const v = video(); if (v) v.currentTime = sec; }
    },
    volume: function (v01) {
      desiredVolume = v01;
      const pct = Math.round(Math.max(0, Math.min(1, v01)) * 100);
      const m = mini();
      if (m && !bar() && m.slider) {
        try {
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(m.slider, pct);
          m.slider.dispatchEvent(new Event('input', { bubbles: true }));
          m.slider.dispatchEvent(new Event('change', { bubbles: true }));
        } catch (e) { /* ignore */ }
      }
      const sl = $('#volume-slider', bar());
      if (sl) { try { sl.value = pct; sl.dispatchEvent(new CustomEvent('change', { bubbles: true })); } catch (e) { /* ignore */ } }
      const mp = player();
      if (mp && mp.setVolume) { mp.setVolume(pct); if (pct > 0 && mp.isMuted && mp.isMuted()) mp.unMute(); }
      else { const v = video(); if (v) v.volume = pct / 100; }
    },
    mute: function (on) {
      const mp = player();
      if (mp && mp.mute) { if (on) mp.mute(); else mp.unMute(); }
      else { const v = video(); if (v) v.muted = !!on; }
    },
    like: function () { const m = mini(); if (m && !bar()) { click(m.like); return; } const r = $('#like-button-renderer', bar()); const b = r && $$('button', r); if (b && b[0]) b[0].click(); },
    dislike: function () { const m = mini(); if (m && !bar()) { click(m.dislike); return; } const r = $('#like-button-renderer', bar()); const b = r && $$('button', r); if (b && b[1]) b[1].click(); },
    shuffle: function () { const m = mini(); if (m && !bar()) click(m.shuffle); else click($('.shuffle', bar())); },
    repeat: function () { const m = mini(); if (m && !bar()) click(m.repeat); else click($('.repeat', bar())); },
    nav: function (i) { const e = $$('ytmusic-guide-entry-renderer')[i]; if (e) e.click(); },
    focusSearch: function () { const i = $('ytmusic-search-box input'); if (i) { i.focus(); i.select(); } },
    playerPage: function (tab) {
      const pp = $('ytmusic-player-page');
      const open = pp && pp.hasAttribute('player-page-open') || (bar() && bar().hasAttribute('player-page-open'));
      if (!open) {
        const t = $('ytmusic-miniplayer ytmusic-track-info') || $('ytmusic-miniplayer [class*=LeftSection]');
        if (t) t.click();
        else click($('.toggle-player-page-button', bar()) || $('.middle-controls', bar()) || $('.content-info-wrapper', bar()));
      }
      if (typeof tab === 'number') {
        setTimeout(function () { const t = $$('#tabsContent tp-yt-paper-tab')[tab]; if (t) t.click(); }, 250);
      }
    },
    probe: function () { return snapshot(); }
  };

  window.__cadence = {
    cmd: function (name, arg) {
      const f = cmds[name];
      if (!f) return null;
      try {
        const r = f(arg);
        if (name !== 'probe') setTimeout(function () { last = ''; tick(); }, 450);
        return r;
      } catch (e) { send({ t: 'error', m: String(e) }); return null; }
    },
    snapshot: snapshot
  };

  connect();
})();
