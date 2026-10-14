import * as THREE from 'three';
import { OrbitControls } from '/static/vendor/OrbitControls.js';

const $ = (id) => document.getElementById(id);
const P = (x, y, z = 0) => new THREE.Vector3(x, z, -y);   // site (x east, y north, z up) -> three.js
let site = null, live = null, replay = null;

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove('show'), 2600);
}
async function api(url, method = 'GET', body) {
  const r = await fetch(url, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.ok === false) throw new Error(j.detail || j.error || `HTTP ${r.status}`);
  return j;
}

// ------------------------------------------------------------------ 3D scene
const view = $('view3d');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
view.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);
const cam3 = new THREE.PerspectiveCamera(45, 1, 0.1, 400);
cam3.position.copy(P(-15, 13, 13));
const controls = new OrbitControls(cam3, renderer.domElement);
controls.target.set(0, 0, 0);
scene.add(new THREE.HemisphereLight(0xffffff, 0x404040, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 1.2); sun.position.set(10, 20, 5); scene.add(sun);

const mat = (c, extra = {}) => new THREE.MeshStandardMaterial({ color: c, ...extra });
const lineLoop = (pts, color, z = 0.03) => {
  const g = new THREE.BufferGeometry().setFromPoints(pts.map(([x, y]) => P(x, y, z)));
  return new THREE.LineLoop(g, new THREE.LineBasicMaterial({ color }));
};
const objs = {};

function buildSite(s) {
  const xs = s.boundary.map(p => p[0]), ys = s.boundary.map(p => p[1]);
  const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat(0x6c5a45));
  ground.rotation.x = -Math.PI / 2; scene.add(ground);
  scene.add(lineLoop(s.boundary, 0x88aaff, 0.05));
  const pxs = s.pit.map(p => p[0]), pys = s.pit.map(p => p[1]);
  const pit = new THREE.Mesh(new THREE.BoxGeometry(Math.max(...pxs) - Math.min(...pxs), 0.05, Math.max(...pys) - Math.min(...pys)), mat(0x111111));
  pit.position.y = 0.02; scene.add(pit);
  const ringColours = [0xff3b30, 0xffb000];
  Object.values(s.rings).forEach((pts, i) => scene.add(lineLoop(pts, ringColours[i] ?? 0xffffff)));
  const [cx, cy, ch] = s.camera.pos;
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.12, ch, 12), mat(0xbbbbbb));
  pole.position.copy(P(cx, cy, ch / 2)); scene.add(pole);
  const fr = new THREE.BufferGeometry().setFromPoints(s.camera.footprint.flatMap(([x, y]) => [P(cx, cy, ch), P(x, y, 0.02)]));
  scene.add(new THREE.LineSegments(fr, new THREE.LineBasicMaterial({ color: 0x5ab0ff, transparent: true, opacity: 0.5 })));
  scene.add(lineLoop(s.camera.footprint, 0x5ab0ff, 0.02));
  const arm = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.3, 0.3), mat(0x444444));
  arm.position.copy(P(s.arm.xy[0], s.arm.xy[1], s.arm.pivot_h_m)); scene.add(arm);
  objs.strobe = new THREE.Mesh(new THREE.SphereGeometry(0.22, 16, 12), mat(0x552200, { emissive: 0x000000 }));
  objs.strobe.position.copy(P(cx, cy, ch + 0.3)); scene.add(objs.strobe);
  const f = s.floodlight;
  const coneLen = Math.hypot(f.xy[0] - f.aim[0], f.xy[1] - f.aim[1], f.height_m);
  objs.flood = new THREE.Mesh(new THREE.ConeGeometry(Math.tan(Math.PI / 6) * coneLen, coneLen, 24, 1, true),
    new THREE.MeshBasicMaterial({ color: 0xfff2b0, transparent: true, opacity: 0.12, side: THREE.DoubleSide }));
  const top = P(f.xy[0], f.xy[1], f.height_m), aim = P(f.aim[0], f.aim[1], 0);
  objs.flood.position.copy(top.clone().add(aim).multiplyScalar(0.5));
  objs.flood.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), top.clone().sub(aim).normalize());
  scene.add(objs.flood);
  objs.laser = new THREE.Line(new THREE.BufferGeometry().setFromPoints([P(0, 0), P(0, 0)]), new THREE.LineBasicMaterial({ color: 0x33ff55 }));
  objs.dot = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 8), new THREE.MeshBasicMaterial({ color: 0x33ff55 }));
  scene.add(objs.laser, objs.dot);
}

const workers = new Map();
function workerMesh() {
  const g = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.25, 1.4, 16), mat(0x3b82f6));
  body.position.y = 0.7;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.17, 16, 12), mat(0xf5f5f5));
  head.position.y = 1.62;
  g.add(body, head); g.userData.body = body; scene.add(g); return g;
}
function beam(arm) {
  if (!arm || !arm.laser || arm.tilt <= 0) return null;
  const a = site.arm, reach = a.pivot_h_m / Math.tan(Math.min(arm.tilt, 90) * Math.PI / 180);
  const ang = (a.heading_deg + arm.pan) * Math.PI / 180;
  return [a.xy[0] + reach * Math.cos(ang), a.xy[1] + reach * Math.sin(ang)];
}
function draw(truth, arm, relay, dot) {
  const seen = new Set();
  for (const w of truth?.workers ?? []) {
    seen.add(w.id);
    const m = workers.get(w.id) ?? workers.set(w.id, workerMesh()).get(w.id);
    m.position.copy(P(w.x, w.y, 0));
    m.userData.body.material.color.set(w.edge_m <= 1.5 ? 0xef4444 : w.edge_m <= 3.0 ? 0xf59e0b : 0x3b82f6);
  }
  for (const [id, m] of workers) if (!seen.has(id)) { scene.remove(m); workers.delete(id); }
  dot = dot ?? beam(arm);
  objs.laser.visible = objs.dot.visible = !!dot;
  if (dot) {
    const a = site.arm;
    objs.laser.geometry.setFromPoints([P(a.xy[0], a.xy[1], a.pivot_h_m), P(dot[0], dot[1], 0.03)]);
    objs.dot.position.copy(P(dot[0], dot[1], 0.05));
  }
  const strobeOn = relay?.strobe && (Date.now() % 500 < 250);
  objs.strobe.material.emissive.set(strobeOn ? 0xff6a00 : 0x000000);
  objs.flood.visible = !!relay?.floodlight;
}
function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h, false); cam3.aspect = w / h; cam3.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(view);
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, cam3); });

// ------------------------------------------------------------------ live state
let ws;
function connect() {
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/live`);
  ws.onopen = () => { $('conn').textContent = 'live'; };
  ws.onclose = () => { $('conn').textContent = 'reconnecting...'; setTimeout(connect, 1000); };
  ws.onmessage = (e) => { live = JSON.parse(e.data); if (!replay) showLive(); };
}
function levelOf(state) {
  const st = state.status;
  if (st && Date.now() / 1000 - st.ts < 5) return st.state;
  const last = [...state.events].reverse().find(e => ['warning', 'alarm', 'reset'].includes(e.kind));
  return !last || last.kind === 'reset' ? 'monitoring' : last.kind;
}
function setLevel(level) {
  const b = $('state'); b.textContent = level.toUpperCase(); b.className = `badge state-${level}`;
}
function showLive() {
  if (!site) return;
  draw(live.truth, live.arm, live.relay, live.dot);
  setLevel(levelOf(live));
  $('weatherNow').textContent = `weather: ${live.weather ?? '-'}`;
  $('scenarioNow').textContent = `scenario: ${live.scenario ?? '-'}`;
  $('runNow').textContent = `run: ${live.run ?? '-'}`;
  const r = live.relay ?? {};
  $('outputs').textContent = `strobe ${r.strobe ? 'ON' : 'off'} · floodlight ${r.floodlight ? 'on' : 'off'} · laser ${live.arm?.laser ? 'ON' : 'off'}`;
  $('conn').textContent = `live · cloud ${live.mqtt ? 'connected' : 'not connected'}`;
  const st = live.status;
  $('status').textContent = st ? `Orin: ${st.state}, ${st.people.length} tracked, camera ${st.camera_ok ? 'ok' : 'OFFLINE'}, arm ${st.arm_online ? 'online' : 'OFFLINE'}, horn ${st.horn ?? 'off'}, queued ${st.queue}`
    : 'Orin status not received yet (it publishes every second over 4G).';
  renderEvents(live.events);
}
function renderEvents(events) {
  $('events').innerHTML = [...events].reverse().slice(0, 25).map(e => {
    const t = new Date((e.ts ?? 0) * 1000).toLocaleTimeString();
    const what = e.kind === 'health' ? e.what : `${e.kind}${e.pid != null ? ` person ${e.pid}` : ''}${e.dist_m != null && e.dist_m >= 0 ? ` at ${e.dist_m} m` : ''}`;
    return `<div class="ev-${e.kind}">${t} ${what}</div>`;
  }).join('') || '<div class="muted">No events yet.</div>';
}

// ------------------------------------------------------------------ video
function startVideo() {
  const v = $('video'), src = '/video/stream1/index.m3u8';
  if (window.Hls && Hls.isSupported()) {
    const hls = new Hls({ liveSyncDurationCount: 2, maxLiveSyncPlaybackRate: 1.5 });
    hls.loadSource(src); hls.attachMedia(v);
    hls.on(Hls.Events.MANIFEST_PARSED, () => { v.play().catch(() => {}); $('videoInfo').textContent = 'live: browser stream from the camera (HLS via this page)'; });
    hls.on(Hls.Events.ERROR, (_, d) => {
      if (d.fatal) { $('videoInfo').textContent = 'video unavailable, retrying...'; hls.destroy(); setTimeout(startVideo, 3000); }
    });
  } else if (v.canPlayType('application/vnd.apple.mpegurl')) {
    v.src = src; v.play().catch(() => {});
  } else {
    $('videoInfo').textContent = 'This browser cannot play HLS video.';
  }
}

// ------------------------------------------------------------------ trial pad
const held = new Set();
let wasHeld = false;
function send(msg) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg)); }
document.querySelectorAll('#pad button').forEach(b => {
  const k = b.dataset.key;
  const on = (e) => { e.preventDefault(); held.add(k); b.classList.add('held'); };
  const off = () => { held.delete(k); b.classList.remove('held'); };
  b.addEventListener('pointerdown', on); ['pointerup', 'pointerleave', 'pointercancel'].forEach(t => b.addEventListener(t, off));
});
const KEYMAP = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', w: 'up', s: 'down', a: 'left', d: 'right' };
const typing = (e) => ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName) && e.target.type !== 'checkbox';
window.addEventListener('keydown', (e) => {
  if (!$('kbd').checked || typing(e)) return;
  if (e.key === 'Shift') $('run').checked = true;
  const k = KEYMAP[e.key] ?? KEYMAP[e.key.toLowerCase?.()];
  if (k) { held.add(k); e.preventDefault(); }
});
window.addEventListener('keyup', (e) => {
  if (e.key === 'Shift') $('run').checked = false;
  const k = KEYMAP[e.key] ?? KEYMAP[e.key.toLowerCase?.()];
  if (k) held.delete(k);
});
window.addEventListener('blur', () => held.clear());
setInterval(() => {
  if (held.size) send({ type: 'keys', keys: [...held], run: $('run').checked });
  else if (wasHeld) send({ type: 'keys', keys: [] });
  wasHeld = held.size > 0;
}, 100);
document.querySelectorAll('[data-cmd]').forEach(b => b.addEventListener('click', () => send({ type: 'cmd', cmd: b.dataset.cmd })));

// ------------------------------------------------------------------ panels
function buildPanels(s) {
  $('scenarios').innerHTML = '';
  s.scenarios.forEach(({ name, label }) => {
    const b = document.createElement('button'); b.textContent = label;
    b.onclick = () => api(`/api/scenario/${name}`, 'POST').then(r => toast(`scenario ${name} started (${r.run})`)).catch(e => toast(e.message));
    $('scenarios').appendChild(b);
  });
  $('weather').innerHTML = s.weathers.map(w => `<option value="${w.name}">${w.name} - ${w.description}</option>`).join('');
  $('applyWeather').onclick = () => api(`/api/weather/${$('weather').value}`, 'POST')
    .then(r => toast(`weather: ${r.weather}${r.events.length ? ` (storm events: ${r.events.join(', ')})` : ''}`)).catch(e => toast(e.message));
  $('faults').innerHTML = '';
  for (const [name, label] of Object.entries(s.faults)) {
    const l = document.createElement('span'); l.textContent = label;
    const inj = document.createElement('button'); inj.textContent = name === 'power_cut' ? 'cut + restore' : 'inject';
    const res = document.createElement('button'); res.textContent = 'restore';
    inj.onclick = () => api(`/fault/${name}`, 'POST').then(() => toast(`fault injected: ${label}`)).catch(e => toast(`${name}: ${e.message}`));
    res.onclick = () => api(`/fault/${name}/restore`, 'POST').then(() => toast(`restored: ${label}`)).catch(e => toast(`${name}: ${e.message}`));
    $('faults').append(l, inj, res);
  }
}

let catalogData = null;
async function buildProducts() {
  catalogData = await api('/api/catalog');
  $('category').innerHTML = Object.keys(catalogData).map(c => `<option>${c}</option>`).join('');
  $('category').onchange = showProducts;
  $('cmpWeather').innerHTML = site.weathers.map(w => `<label><input type="checkbox" value="${w.name}" ${['clear', 'tropical_downpour', 'night_clear', 'low_sun_glare'].includes(w.name) ? 'checked' : ''}>${w.name}</label>`).join('');
  showProducts();
}
function showProducts() {
  $('products').innerHTML = catalogData[$('category').value].map(p =>
    `<label><input type="checkbox" value="${p.id}" checked>${p.id}${p.fitted ? ' (fitted)' : ''}${p.verified ? '' : ' *'}</label>`).join('');
  $('cmpInfo').textContent = '* not yet verified against a datasheet';
}
$('compare').onclick = async () => {
  const products = [...$('products').querySelectorAll('input:checked')].map(i => i.value);
  const weathers = [...$('cmpWeather').querySelectorAll('input:checked')].map(i => i.value);
  $('cmpInfo').textContent = 'rendering the comparison...';
  try {
    const r = await api('/api/compare', 'POST', { category: $('category').value, products, weathers });
    $('cmpTable').innerHTML = `<tr>${r.columns.map(c => `<th>${c}</th>`).join('')}</tr>` + r.rows.map(row => `<tr>${row.map(v => `<td>${v}</td>`).join('')}</tr>`).join('');
    $('grid').hidden = !r.grid; if (r.grid) $('grid').src = r.grid;
    $('cmpInfo').textContent = r.grid ? 'picture grid: one row per weather, one column per product' : '';
  } catch (e) { $('cmpInfo').textContent = e.message; }
};

// ------------------------------------------------------------------ replay
async function loadRuns() {
  const runs = await api('/api/runs');
  $('runs').innerHTML = runs.map(r => `<option value="${r.id}">${r.id}</option>`).join('');
}
$('refreshRuns').onclick = loadRuns;
$('loadRun').onclick = async () => {
  if (!$('runs').value) return;
  replay = await api(`/api/runs/${$('runs').value}`);
  if (!replay.truth.length) { toast('that run has no frames yet'); replay = null; return; }
  replay.i = 0; $('replayBar').style.display = 'flex'; $('mode').textContent = `replay ${replay.id}`;
  $('rpSlider').max = replay.truth.length - 1; showFrame();
};
function latest(list, t) { let out = null; for (const x of list) { if ((x.t ?? x.ts) <= t) out = x; else break; } return out; }
function showFrame() {
  const f = replay.truth[replay.i];
  draw(f, latest(replay.arm, f.t), latest(replay.relay, f.t), null);
  const evs = replay.events.filter(e => e.ts <= f.t);
  renderEvents(evs); setLevel(levelOf({ status: null, events: evs }));
  $('rpSlider').value = replay.i; $('rpInfo').textContent = `frame ${replay.i + 1}/${replay.truth.length} · ${new Date(f.t * 1000).toLocaleTimeString()}`;
}
const stepTo = (i) => { replay.i = Math.max(0, Math.min(replay.truth.length - 1, i)); showFrame(); };
$('rpPrev').onclick = () => stepTo(replay.i - 1);
$('rpNext').onclick = () => stepTo(replay.i + 1);
$('rpSlider').oninput = (e) => stepTo(+e.target.value);
$('rpPlay').onclick = () => {
  if (replay.timer) { clearInterval(replay.timer); replay.timer = null; $('rpPlay').textContent = 'play'; return; }
  $('rpPlay').textContent = 'pause';
  replay.timer = setInterval(() => replay.i < replay.truth.length - 1 ? stepTo(replay.i + 1) : $('rpPlay').click(), 1000 / 15);
};
$('rpExit').onclick = () => { if (replay?.timer) clearInterval(replay.timer); replay = null; $('replayBar').style.display = 'none'; $('mode').textContent = 'live'; };

// ------------------------------------------------------------------ start
site = await api('/api/site');
buildSite(site); buildPanels(site); resize(); connect(); startVideo();
buildProducts().catch(e => toast(e.message)); loadRuns().catch(() => {});
