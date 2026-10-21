/* ReMoRehab — guided mirror-therapy session.
   Everything runs locally. The camera stream is drawn to a canvas and never sent anywhere. */
(function () {
  'use strict';

  // Browsers only expose the camera on a secure origin. If this page was opened
  // over plain http, move to https before anything else runs.
  if (location.protocol === 'http:' && !/^(localhost|127\.|\[::1\])/.test(location.hostname)) {
    location.replace(location.href.replace(/^http:/, 'https:'));
    return;
  }

  var EXERCISES = [
    { name: 'Open and close the hand', cue: 'Spread the fingers wide, then make a loose fist.' },
    { name: 'Wrist up and down', cue: 'Bend the wrist back, then let it drop. Keep the forearm still.' },
    { name: 'Palm up, palm down', cue: 'Turn the forearm so the palm faces up, then down.' },
    { name: 'Thumb to fingertips', cue: 'Touch the thumb to each fingertip in turn, then back again.' },
    { name: 'Wrist circles', cue: 'Draw a slow circle with the hand. Change direction halfway.' },
    { name: 'Bend and straighten the elbow', cue: 'Bring the hand toward the shoulder, then reach out.' }
  ];
  var REST_MS = 15000;
  var KEY = 'remorehab.sessions.v1';
  var PREF = 'remorehab.prefs.v1';

  var $ = function (id) { return document.getElementById(id); };
  var canvas = $('canvas'), ctx = canvas.getContext('2d');
  var stage = $('stage'), hud = $('hud'), msg = $('msg'), bar = $('bar'), statusEl = $('status');

  var raw = document.createElement('canvas');
  var comp = document.createElement('canvas');

  var video = document.createElement('video');
  video.muted = true; video.playsInline = true; video.setAttribute('playsinline', '');

  var S = {
    running: false, paused: false, stereo: false, camera: false,
    exIndex: 0, rep: 0, phase: 'idle', phaseMs: 0, lastT: 0,
    totalReps: 0, activeMs: 0, stream: null
  };

  var P = {
    affected: 'left', flipped: false, sound: true,
    reps: 12, pace: 4, ipd: 62
  };
  try { Object.assign(P, JSON.parse(localStorage.getItem(PREF) || '{}')); } catch (e) {}
  function savePrefs() { try { localStorage.setItem(PREF, JSON.stringify(P)); } catch (e) {} }

  /* ---------------------------------------------------------------- audio */
  var actx = null;
  function beep(freq, ms) {
    if (!P.sound) return;
    try {
      if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)();
      if (actx.state === 'suspended') actx.resume();
      var o = actx.createOscillator(), g = actx.createGain(), t = actx.currentTime;
      o.type = 'sine'; o.frequency.value = freq || 660;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.16, t + 0.012);
      g.gain.exponentialRampToValueAtTime(0.0001, t + (ms || 90) / 1000);
      o.connect(g); g.connect(actx.destination);
      o.start(t); o.stop(t + (ms || 90) / 1000 + 0.03);
    } catch (e) {}
  }

  /* --------------------------------------------------------------- camera */
  function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      say('This browser will not give a page camera access. The paced session still works without it.', true);
      return;
    }
    say('Asking for camera permission…');
    navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 960 } }, audio: false
    }).then(function (stream) {
      S.stream = stream; video.srcObject = stream;
      return video.play();
    }).then(function () {
      S.camera = true;
      msg.hidden = true;
      $('btn-cam').textContent = 'Turn off camera';
      $('btn-stereo').disabled = false;
      say('Camera on. Nothing is recorded or uploaded.');
    }).catch(function (err) {
      var why = (err && err.name) || 'error';
      if (!window.isSecureContext) {
        why = 'this page is not on a secure connection';
      } else if (why === 'NotAllowedError') {
        why = 'permission was declined — you can re-allow it in the address bar';
      } else if (why === 'NotFoundError') {
        why = 'no camera found on this device';
      }
      say('Camera unavailable: ' + why + '. The paced session still works without it.', true);
    });
  }

  function stopCamera() {
    if (S.stream) { S.stream.getTracks().forEach(function (t) { t.stop(); }); }
    S.stream = null; S.camera = false; video.srcObject = null;
    $('btn-cam').textContent = 'Turn on camera';
    $('btn-stereo').disabled = true;
    if (S.stereo) toggleStereo();
    msg.hidden = S.running;
    say('Camera off.');
  }

  function say(t, isErr) {
    statusEl.textContent = t || '';
    statusEl.className = 'muted' + (isErr ? ' err' : '');
  }

  /* ------------------------------------------------------------- drawing */
  // Which half of the picture holds the limb the person is actually moving?
  function goodOnRight() {
    var good = P.affected === 'left' ? 'right' : 'left';
    return P.flipped ? (good === 'right') : (good === 'left');
  }

  function drawRaw(W, H) {
    raw.width = W; raw.height = H;
    var r = raw.getContext('2d');
    var vw = video.videoWidth, vh = video.videoHeight;
    r.fillStyle = '#000'; r.fillRect(0, 0, W, H);
    if (!vw || !vh) return false;
    var s = Math.max(W / vw, H / vh);
    var dw = vw * s, dh = vh * s;
    r.save();
    if (P.flipped) { r.translate(W, 0); r.scale(-1, 1); }
    r.drawImage(video, (W - dw) / 2, (H - dh) / 2, dw, dh);
    r.restore();
    return true;
  }

  // Build the symmetric picture: copy the working half across the centre line.
  function drawComposite(W, H) {
    comp.width = W; comp.height = H;
    var c = comp.getContext('2d');
    if (!drawRaw(W, H)) { c.fillStyle = '#000'; c.fillRect(0, 0, W, H); return; }
    var half = Math.floor(W / 2);
    if (goodOnRight()) {
      c.drawImage(raw, half, 0, half, H, half, 0, half, H);
      c.save(); c.translate(half, 0); c.scale(-1, 1);
      c.drawImage(raw, half, 0, half, H, 0, 0, half, H);
      c.restore();
    } else {
      c.drawImage(raw, 0, 0, half, H, 0, 0, half, H);
      c.save(); c.translate(W, 0); c.scale(-1, 1);
      c.drawImage(raw, 0, 0, half, H, 0, 0, half, H);
      c.restore();
    }
    // a soft seam so the two halves read as a reflection, not a glitch
    var grad = c.createLinearGradient(half - 14, 0, half + 14, 0);
    grad.addColorStop(0, 'rgba(0,0,0,0)');
    grad.addColorStop(0.5, 'rgba(0,0,0,0.30)');
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    c.fillStyle = grad; c.fillRect(half - 14, 0, 28, H);
  }

  // Pacing circle for people running the session without a camera.
  function drawPacer(W, H) {
    ctx.fillStyle = '#071215'; ctx.fillRect(0, 0, W, H);
    var cx = W / 2, cy = H / 2;
    var f = S.phase === 'work' ? (S.phaseMs % (P.pace * 1000)) / (P.pace * 1000) : 0;
    var k = S.phase === 'work' ? 0.5 - 0.5 * Math.cos(2 * Math.PI * f) : 0.12;
    var rMin = Math.min(W, H) * 0.12, rMax = Math.min(W, H) * 0.34;
    var r = rMin + (rMax - rMin) * k;
    ctx.beginPath(); ctx.arc(cx, cy, rMax, 0, 6.2832);
    ctx.strokeStyle = '#16323a'; ctx.lineWidth = 2; ctx.stroke();
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, 6.2832);
    ctx.fillStyle = S.phase === 'rest' ? '#1d3a42' : '#176b63'; ctx.fill();
    ctx.fillStyle = '#cfe6e8';
    ctx.font = '600 ' + Math.round(Math.min(W, H) * 0.07) + 'px Montserrat, sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(S.phase === 'rest' ? 'rest' : (S.running ? 'move' : 'ready'), cx, cy);
  }

  function fitInto(sw, sh, dw, dh) {
    var s = Math.min(dw / sw, dh / sh);
    return { w: sw * s, h: sh * s, x: (dw - sw * s) / 2, y: (dh - sh * s) / 2 };
  }

  function render() {
    var W = canvas.width, H = canvas.height;
    if (!S.camera) { drawPacer(W, H); return; }
    if (!S.stereo) { drawComposite(W, H); ctx.drawImage(comp, 0, 0, W, H); return; }
    drawComposite(960, 720);
    var eyeW = W / 2;
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
    var box = fitInto(960, 720, eyeW * 0.92, H * 0.92);
    var shift = (P.ipd - 62) * 1.6;
    ctx.drawImage(comp, box.x + shift, box.y, box.w, box.h);
    ctx.drawImage(comp, eyeW + box.x - shift, box.y, box.w, box.h);
    ctx.fillStyle = '#000'; ctx.fillRect(eyeW - 1.5, 0, 3, H);
  }

  /* ------------------------------------------------------------- session */
  function totalRepsPlanned() { return EXERCISES.length * P.reps; }

  function advance(dt) {
    S.phaseMs += dt; S.activeMs += dt;
    if (S.phase === 'work') {
      var step = P.pace * 1000;
      while (S.phaseMs >= step) {
        S.phaseMs -= step; S.rep++; S.totalReps++;
        if (S.rep >= P.reps) {
          beep(880, 150);
          if (S.exIndex >= EXERCISES.length - 1) { finish(); return; }
          S.phase = 'rest'; S.phaseMs = 0; S.rep = 0; break;
        }
        beep(660, 80);
      }
    } else if (S.phase === 'rest') {
      if (S.phaseMs >= REST_MS) {
        S.exIndex++; S.phase = 'work'; S.phaseMs = 0; S.rep = 0; beep(520, 120);
      }
    }
    paint();
  }

  function paint() {
    var ex = EXERCISES[Math.min(S.exIndex, EXERCISES.length - 1)];
    if (S.phase === 'rest') {
      var left = Math.ceil((REST_MS - S.phaseMs) / 1000);
      $('hud-ex').textContent = 'Rest';
      $('hud-cue').textContent = left + 's — next: ' + EXERCISES[Math.min(S.exIndex + 1, EXERCISES.length - 1)].name;
      $('hud-count').textContent = left;
    } else {
      $('hud-ex').textContent = ex.name;
      $('hud-cue').textContent = ex.cue;
      $('hud-count').textContent = S.rep + '/' + P.reps;
    }
    bar.style.width = (100 * S.totalReps / Math.max(1, totalRepsPlanned())) + '%';
  }

  function start() {
    S.running = true; S.paused = false; S.exIndex = 0; S.rep = 0;
    S.phase = 'work'; S.phaseMs = 0; S.totalReps = 0; S.activeMs = 0;
    hud.hidden = false; msg.hidden = true;
    $('btn-start').textContent = 'Stop';
    $('btn-pause').disabled = false; $('btn-skip').disabled = false;
    beep(520, 120); paint();
    say('Session running. Keep your eyes on the reflected limb.');
  }

  function stop(saveIt) {
    if (saveIt && S.totalReps > 0) saveSession();
    S.running = false; S.paused = false; S.phase = 'idle';
    hud.hidden = true; msg.hidden = S.camera;
    $('btn-start').textContent = 'Start session';
    $('btn-pause').disabled = true; $('btn-skip').disabled = true;
    $('btn-pause').textContent = 'Pause';
    bar.style.width = '0%';
  }

  function finish() {
    beep(760, 160);
    setTimeout(function () { beep(980, 240); }, 180);
    say('Session complete — ' + S.totalReps + ' reps logged.');
    stop(true);
  }

  function skip() {
    if (!S.running) return;
    if (S.exIndex >= EXERCISES.length - 1) { finish(); return; }
    S.exIndex++; S.phase = 'work'; S.phaseMs = 0; S.rep = 0; beep(520, 100); paint();
  }

  /* --------------------------------------------------------------- store */
  function loadLog() {
    try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; }
  }
  function saveSession() {
    var all = loadLog();
    var today = new Date().toISOString().slice(0, 10);
    var mins = Math.round(S.activeMs / 60000 * 10) / 10;
    var exDone = Math.min(S.exIndex + 1, EXERCISES.length);
    var last = all[all.length - 1];
    if (last && last.date === today) {
      last.reps += S.totalReps; last.mins = Math.round((last.mins + mins) * 10) / 10;
      last.ex = Math.max(last.ex, exDone);
    } else {
      all.push({ date: today, reps: S.totalReps, mins: mins, ex: exDone });
    }
    try { localStorage.setItem(KEY, JSON.stringify(all.slice(-120))); } catch (e) {}
    renderLog();
  }
  function streakOf(all) {
    if (!all.length) return 0;
    var days = {}; all.forEach(function (r) { days[r.date] = true; });
    var d = new Date(), n = 0;
    var iso = function (x) { return x.toISOString().slice(0, 10); };
    if (!days[iso(d)]) { d.setDate(d.getDate() - 1); if (!days[iso(d)]) return 0; }
    while (days[iso(d)]) { n++; d.setDate(d.getDate() - 1); }
    return n;
  }
  function renderLog() {
    var all = loadLog(), tb = $('log-body');
    $('streak').textContent = streakOf(all);
    if (!all.length) { tb.innerHTML = '<tr><td colspan="4" class="muted">No sessions yet.</td></tr>'; return; }
    tb.innerHTML = all.slice(-10).reverse().map(function (r) {
      return '<tr><td>' + r.date + '</td><td>' + r.ex + '</td><td>' + r.reps + '</td><td>' + r.mins + '</td></tr>';
    }).join('');
  }

  /* ----------------------------------------------------------------- UI */
  function seg(onId, offId, get, set) {
    function sync() {
      $(onId).setAttribute('aria-pressed', String(get()));
      $(offId).setAttribute('aria-pressed', String(!get()));
    }
    $(onId).addEventListener('click', function () { set(true); savePrefs(); sync(); });
    $(offId).addEventListener('click', function () { set(false); savePrefs(); sync(); });
    sync();
  }

  seg('side-left', 'side-right',
    function () { return P.affected === 'left'; },
    function (v) { P.affected = v ? 'left' : 'right'; });
  seg('flip-on', 'flip-off',
    function () { return P.flipped; },
    function (v) { P.flipped = v; });
  seg('snd-on', 'snd-off',
    function () { return P.sound; },
    function (v) { P.sound = v; if (v) beep(660, 70); });

  function slider(id, valId, key, fmt) {
    var el = $(id); el.value = P[key];
    function sync() { $(valId).textContent = fmt(P[key]); }
    el.addEventListener('input', function () { P[key] = +el.value; sync(); savePrefs(); });
    sync();
  }
  slider('reps', 'reps-val', 'reps', function (v) { return v; });
  slider('pace', 'pace-val', 'pace', function (v) { return v + ' s'; });
  slider('ipd', 'ipd-val', 'ipd', function (v) { return v + ' mm'; });

  $('btn-start').addEventListener('click', function () {
    if (S.running) { stop(true); say('Session stopped and saved.'); }
    else start();
  });
  $('btn-pause').addEventListener('click', function () {
    S.paused = !S.paused;
    $('btn-pause').textContent = S.paused ? 'Resume' : 'Pause';
    say(S.paused ? 'Paused.' : 'Running.');
  });
  $('btn-skip').addEventListener('click', skip);
  $('btn-cam').addEventListener('click', function () { S.camera ? stopCamera() : startCamera(); });

  function toggleStereo() {
    S.stereo = !S.stereo;
    stage.classList.toggle('stereo', S.stereo);
    canvas.width = S.stereo ? 1280 : 960;
    canvas.height = S.stereo ? 720 : 720;
    $('btn-stereo').textContent = S.stereo ? 'Normal view' : 'Headset view';
    if (S.stereo && stage.requestFullscreen) { stage.requestFullscreen().catch(function () {}); }
    else if (!S.stereo && document.fullscreenElement && document.exitFullscreen) { document.exitFullscreen().catch(function () {}); }
    say(S.stereo ? 'Headset view: slide the phone into the printed shell.' : '');
  }
  $('btn-stereo').addEventListener('click', toggleStereo);

  $('btn-clear').addEventListener('click', function () {
    if (!confirm('Delete all saved sessions on this device?')) return;
    try { localStorage.removeItem(KEY); } catch (e) {}
    renderLog(); say('History cleared.');
  });

  document.addEventListener('keydown', function (e) {
    if (e.target && /input|button|select/i.test(e.target.tagName)) return;
    if (e.code === 'Space') { e.preventDefault(); if (S.running) $('btn-pause').click(); else $('btn-start').click(); }
    if (e.key === 'n' || e.key === 'N') skip();
  });

  /* --------------------------------------------------------------- loop */
  function tick(t) {
    var dt = S.lastT ? Math.min(t - S.lastT, 100) : 0;
    S.lastT = t;
    if (S.running && !S.paused) advance(dt);
    render();
    requestAnimationFrame(tick);
  }

  renderLog();
  requestAnimationFrame(tick);
})();
