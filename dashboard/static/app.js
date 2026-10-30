import * as THREE from 'three';
import { OrbitControls } from '/static/vendor/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { Sky } from 'three/addons/objects/Sky.js';

const $ = (id) => document.getElementById(id);
const P = (x, y, z = 0) => new THREE.Vector3(x, z, -y);   // site (x east, y north, z up) -> three.js
const DEG = Math.PI / 180;
let site = null, live = null, replay = null, hudData = null;

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
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private window */ } },
};

// ------------------------------------------------------------------ renderer and quality presets
const QUALITY = {
  low: { shadows: false, bloom: false, rain: 0, ratio: 1, shadowSize: 512 },
  medium: { shadows: true, bloom: true, rain: 1500, ratio: 1, shadowSize: 1024 },
  high: { shadows: true, bloom: true, rain: 4000, ratio: Math.min(2, window.devicePixelRatio), shadowSize: 2048 },
};
let quality = QUALITY[store.get('twin.quality', 'medium')] ? store.get('twin.quality', 'medium') : 'medium';
$('quality').value = quality;

const view = $('view3d');
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.9;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
view.insertBefore(renderer.domElement, view.firstChild);
const scene = new THREE.Scene();
const cam3 = new THREE.PerspectiveCamera(45, 1, 0.1, 600);
cam3.position.copy(P(-9, -10, 11));                 // inside the hoarding, behind and above the stand
const controls = new OrbitControls(cam3, renderer.domElement);
controls.target.set(0, 0, 0);
controls.maxPolarAngle = 88 * DEG;

const hemi = new THREE.HemisphereLight(0xdfe9ff, 0x4a3b2c, 0.6);
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.shadow.camera.left = -16; sun.shadow.camera.right = 16; sun.shadow.camera.top = 16; sun.shadow.camera.bottom = -16;
sun.shadow.camera.far = 120; sun.shadow.bias = -0.0005; sun.shadow.normalBias = 0.02;
scene.add(hemi, sun, sun.target);
const sky = new Sky(); sky.scale.setScalar(450); scene.add(sky);
sky.material.uniforms.turbidity.value = 6; sky.material.uniforms.rayleigh.value = 1.6;
sky.material.uniforms.mieCoefficient.value = 0.004; sky.material.uniforms.mieDirectionalG.value = 0.8;

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, cam3));
const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.7, 0.25, 1.0);   // threshold 1: only HDR emitters glow
composer.addPass(bloom);
composer.addPass(new OutputPass());

function applyQuality() {
  const q = QUALITY[quality];
  renderer.setPixelRatio(q.ratio);
  renderer.shadowMap.enabled = q.shadows;
  sun.castShadow = q.shadows;
  sun.shadow.mapSize.set(q.shadowSize, q.shadowSize);
  if (sun.shadow.map) { sun.shadow.map.dispose(); sun.shadow.map = null; }
  scene.traverse(o => { if (o.material) o.material.needsUpdate = true; });
  rain.setCount(q.rain);
  resize();
}
$('quality').onchange = (e) => { quality = e.target.value; store.set('twin.quality', quality); applyQuality(); };

// ------------------------------------------------------------------ materials and helpers
const std = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.8, metalness: 0.0, ...o });
const lineLoop = (pts, color, z = 0.03, opacity = 1) => {
  const g = new THREE.BufferGeometry().setFromPoints(pts.map(([x, y]) => P(x, y, z)));
  return new THREE.LineLoop(g, new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity }));
};
const box = (w, h, d, m, shadow = true) => {
  const o = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); o.castShadow = shadow; o.receiveShadow = true; return o;
};
const cyl = (r0, r1, h, m, seg = 12) => {
  const o = new THREE.Mesh(new THREE.CylinderGeometry(r0, r1, h, seg), m); o.castShadow = true; return o;
};
function mudTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'); g.fillStyle = '#6b5843'; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2600; i++) {
    const v = 70 + Math.random() * 60;
    g.fillStyle = `rgba(${v + 20},${v},${v - 25},${0.15 + Math.random() * 0.25})`;
    g.beginPath(); g.arc(Math.random() * 256, Math.random() * 256, 1 + Math.random() * 4, 0, 7); g.fill();
  }
  g.strokeStyle = 'rgba(40,30,22,.35)'; g.lineWidth = 5;
  for (let i = 0; i < 5; i++) { g.beginPath(); const y = Math.random() * 256; g.moveTo(0, y); g.bezierCurveTo(80, y + 30, 170, y - 30, 256, y + 10); g.stroke(); }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// ------------------------------------------------------------------ rain
const rain = (() => {
  const max = 4000, pos = new Float32Array(max * 3), geo = new THREE.BufferGeometry();
  for (let i = 0; i < max; i++) { pos[i * 3] = (Math.random() - .5) * 40; pos[i * 3 + 1] = Math.random() * 20; pos[i * 3 + 2] = (Math.random() - .5) * 40; }
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const pts = new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xbfd4ff, size: 0.06, transparent: true, opacity: 0.6, depthWrite: false }));
  pts.visible = false; scene.add(pts);
  let count = 0, on = false;
  return {
    setCount(n) { count = n; geo.setDrawRange(0, n); pts.visible = on && n > 0; },
    set(active) { on = active; pts.visible = on && count > 0; },
    step(dt, wind) {
      if (!pts.visible) return;
      for (let i = 0; i < count; i++) {
        pos[i * 3 + 1] -= 9 * dt; pos[i * 3] += wind * dt;
        if (pos[i * 3 + 1] < 0) { pos[i * 3 + 1] = 20; pos[i * 3] = (Math.random() - .5) * 40; }
      }
      geo.attributes.position.needsUpdate = true;
    },
  };
})();

// ------------------------------------------------------------------ site
const objs = {};
const groundMat = std(0xffffff, { map: mudTexture(), roughness: 0.95 });
function buildSite(s) {
  const xs = s.boundary.map(p => p[0]), ys = s.boundary.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const w = x1 - x0 + 30, h = y1 - y0 + 30;
  groundMat.map.repeat.set(w / 6, h / 6);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(w, h), groundMat);
  ground.rotation.x = -Math.PI / 2; ground.position.copy(P((x0 + x1) / 2, (y0 + y1) / 2, 0)); ground.receiveShadow = true;
  scene.add(ground); objs.ground = ground;
  const hoard = std(0xb9b2a4, { transparent: true, opacity: 0.3, side: THREE.DoubleSide, depthWrite: false });
  [[x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]].forEach(([ax, ay, bx, by]) => {
    const len = Math.hypot(bx - ax, by - ay), wall = box(len, 2.4, 0.05, hoard, false);
    wall.position.copy(P((ax + bx) / 2, (ay + by) / 2, 1.2)); wall.rotation.y = Math.atan2(by - ay, bx - ax); scene.add(wall);
  });
  // pit, recessed, with a red and white barrier
  const pxs = s.pit.map(p => p[0]), pys = s.pit.map(p => p[1]);
  const pw = Math.max(...pxs) - Math.min(...pxs), pd = Math.max(...pys) - Math.min(...pys);
  const pit = box(pw, 0.05, pd, std(0x111111, { roughness: 1 }), false); pit.position.y = 0.01; scene.add(pit);
  const bx0 = Math.min(...pxs) - 0.3, bx1 = Math.max(...pxs) + 0.3, by0 = Math.min(...pys) - 0.3, by1 = Math.max(...pys) + 0.3;
  const red = std(0xd02020, { roughness: 0.5 }), white = std(0xf2f2f2, { roughness: 0.5 });
  [[bx0, by0, bx1, by0], [bx1, by0, bx1, by1], [bx1, by1, bx0, by1], [bx0, by1, bx0, by0]].forEach(([ax, ay, bx, by]) => {
    const n = Math.max(2, Math.round(Math.hypot(bx - ax, by - ay) / 0.5));
    for (let i = 0; i < n; i++) {
      const t0 = i / n, t1 = (i + 1) / n;
      const rail = box(Math.hypot(bx - ax, by - ay) / n, 0.08, 0.04, i % 2 ? red : white);
      rail.position.copy(P(ax + (bx - ax) * (t0 + t1) / 2, ay + (by - ay) * (t0 + t1) / 2, 1.0));
      rail.rotation.y = Math.atan2(by - ay, bx - ax); scene.add(rail);
      const post = cyl(0.03, 0.03, 1.0, white, 6); post.position.copy(P(ax + (bx - ax) * t0, ay + (by - ay) * t0, 0.5)); scene.add(post);
    }
  });
  const ringColours = [0xff3b30, 0xffb000];
  Object.values(s.rings).forEach((pts, i) => scene.add(lineLoop(pts, ringColours[i] ?? 0xffffff)));
  buildPole(s);
  // the camera's true field of view: rays to the (lens-bowed) ground footprint
  const [cx, cy, ch] = s.camera.pos;
  const fp = s.camera.footprint;
  const step = Math.max(1, Math.floor(fp.length / 8));
  const rays = fp.filter((_, i) => i % step === 0).flatMap(([x, y]) => [P(cx, cy, ch), P(x, y, 0.03)]);
  objs.frustum = new THREE.Group();
  objs.frustum.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(rays),
    new THREE.LineBasicMaterial({ color: 0x5ab0ff, transparent: true, opacity: 0.35 })));
  objs.frustum.add(lineLoop(fp, 0x5ab0ff, 0.03, 0.8));
  scene.add(objs.frustum);
  // laser beam and dot (emissive: bloom makes them glow)
  objs.laser = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 1, 6, 1, true),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(0.6, 3.0, 0.9), transparent: true, opacity: 0.85, toneMapped: false }));
  objs.dot = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(1.5, 4.0, 1.8), toneMapped: false }));
  objs.dot.scale.y = 0.3;
  scene.add(objs.laser, objs.dot);
}

function buildPole(s) {
  const [cx, cy, ch] = s.camera.pos;
  const metal = std(0x9aa1a8, { metalness: 0.7, roughness: 0.35 }), dark = std(0x2a2e33, { roughness: 0.6 });
  const g = new THREE.Group(); g.position.copy(P(cx, cy, 0)); scene.add(g);
  if (s.profile === 'v11') {                // wheeled cabinet stand
    const cab = box(0.8, 1.1, 0.6, std(0xd7d9dc, { roughness: 0.5 })); cab.position.y = 0.75; g.add(cab);
    [[-0.32, -0.24], [0.32, -0.24], [-0.32, 0.24], [0.32, 0.24]].forEach(([x, z]) => {
      const wh = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 0.06, 16), dark); wh.rotation.x = Math.PI / 2;
      wh.position.set(x, 0.1, z); wh.castShadow = true; g.add(wh);
    });
    const mast = cyl(0.045, 0.06, ch - 1.3, metal); mast.position.y = 1.3 + (ch - 1.3) / 2; g.add(mast);
    objs.skid = new THREE.Group();          // Plans B and C: solar skid beside the stand
    const skidBase = box(2.6, 0.15, 2.2, std(0x5b6168)); skidBase.position.y = 0.08; objs.skid.add(skidBase);
    const panelMat = std(0x1a2a4a, { metalness: 0.4, roughness: 0.25 });
    for (let i = 0; i < 4; i++) {
      const pnl = box(1.0, 0.04, 1.65, panelMat); pnl.position.set(-0.75 + (i % 2) * 1.5, 0.9 + Math.floor(i / 2) * 0.05, -0.45 + Math.floor(i / 2) * 0.9);
      pnl.rotation.x = -15 * DEG; objs.skid.add(pnl);
    }
    objs.skid.position.copy(P(cx + 2.6, cy - 0.5, 0)); objs.skid.visible = false; scene.add(objs.skid);
  } else {                                   // trailer with telescopic mast
    const trailer = box(2.2, 0.5, 1.4, std(0x3d4a57)); trailer.position.y = 0.55; g.add(trailer);
    const mast = cyl(0.08, 0.12, ch, metal); mast.position.y = ch / 2; g.add(mast);
  }
  const head = box(0.18, 0.14, 0.42, std(0xeeeeee, { roughness: 0.4 })); head.position.y = ch; g.add(head);
  head.lookAt(new THREE.Vector3(-cx, 0, cy).add(new THREE.Vector3(0, ch, 0)));
  objs.strobe = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 12), std(0x552200, { emissive: 0x000000 }));
  objs.strobe.position.y = ch + 0.25; g.add(objs.strobe);
  const a = s.arm;
  const arm = box(0.22, 0.22, 0.22, dark); arm.position.copy(P(a.xy[0], a.xy[1], a.pivot_h_m)); scene.add(arm);
  // floodlight: a spot light plus a visible cone at night
  const f = s.floodlight;
  objs.spot = new THREE.SpotLight(0xfff2c4, 0, 40, 30 * DEG, 0.5, 1.4);
  objs.spot.position.copy(P(f.xy[0], f.xy[1], f.height_m)); objs.spot.target.position.copy(P(f.aim[0], f.aim[1], 0));
  scene.add(objs.spot, objs.spot.target);
  const coneLen = Math.hypot(f.xy[0] - f.aim[0], f.xy[1] - f.aim[1], f.height_m);
  objs.flood = new THREE.Mesh(new THREE.ConeGeometry(Math.tan(Math.PI / 6) * coneLen, coneLen, 32, 1, true),
    new THREE.MeshBasicMaterial({ color: 0xfff2b0, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false }));
  const top = P(f.xy[0], f.xy[1], f.height_m), aim = P(f.aim[0], f.aim[1], 0);
  objs.flood.position.copy(top.clone().add(aim).multiplyScalar(0.5));
  objs.flood.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), top.clone().sub(aim).normalize());
  scene.add(objs.flood);
}

// ------------------------------------------------------------------ rigged workers
const skin = std(0xc8a07a), trousers = std(0x2c3440), boots = std(0x1c1c1c);
function limb(len, r, m) {
  const pivot = new THREE.Group(), seg = cyl(r, r * 0.9, len, m, 8); seg.position.y = -len / 2; pivot.add(seg); return pivot;
}
function workerRig() {
  const root = new THREE.Group(), hips = new THREE.Group();
  const vest = std(0xe8f02a, { roughness: 0.55, emissive: 0x000000 });
  const torso = box(0.36, 0.55, 0.22, vest); torso.position.y = 0.3;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 12), skin); head.position.y = 0.72; head.castShadow = true;
  const helmet = new THREE.Mesh(new THREE.SphereGeometry(0.135, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), std(0xf5f5f5, { roughness: 0.35 }));
  helmet.position.y = 0.75; helmet.castShadow = true;
  const legs = [-0.1, 0.1].map(x => {
    const thigh = limb(0.45, 0.075, trousers), shin = limb(0.45, 0.065, trousers);
    shin.position.y = -0.45; thigh.add(shin); thigh.position.set(x, 0, 0);
    const boot = box(0.1, 0.08, 0.22, boots); boot.position.set(0, -0.47, 0.04); shin.add(boot);
    hips.add(thigh); return { thigh, shin };
  });
  const arms = [-0.23, 0.23].map(x => {
    const upper = limb(0.3, 0.05, vest), fore = limb(0.28, 0.045, skin);
    fore.position.y = -0.3; upper.add(fore); upper.position.set(x, 0.55, 0); hips.add(upper); return { upper, fore };
  });
  hips.add(torso, head, helmet); root.add(hips);
  root.userData = { hips, legs, arms, vest, phase: Math.random() * 6, last: null, heading: 0 };
  scene.add(root); return root;
}
const POSES = {      // hips height, thigh and shin angles (left, right), arm swing
  stand: { h: 0.92, th: [0, 0], sh: [0, 0] },
  squat: { h: 0.46, th: [-1.75, -1.75], sh: [2.2, 2.2] },
  kneel: { h: 0.58, th: [-1.5, 0.05], sh: [1.6, 1.55] },
};
function poseRig(r, posture, t, dt) {
  const u = r.userData, walk = posture === 'walk';
  const base = POSES[walk ? 'stand' : posture] ?? POSES.stand;
  u.phase += walk ? dt * 7 : 0;
  const swing = walk ? Math.sin(u.phase) * 0.55 : 0;
  u.hips.position.y = base.h + (walk ? Math.abs(Math.cos(u.phase)) * 0.03 : 0);
  u.legs.forEach((l, i) => {
    const s = i ? -swing : swing;
    l.thigh.rotation.x = base.th[i] + s; l.shin.rotation.x = base.sh[i] + (walk ? Math.max(0, -s) * 0.9 : 0);
  });
  u.arms.forEach((a, i) => { a.upper.rotation.x = (i ? swing : -swing) * 0.8 + (posture === 'squat' ? -0.6 : 0); a.fore.rotation.x = -0.25; });
}
const workers = new Map();
function beam(arm) {
  if (!arm || !arm.laser || arm.tilt <= 0) return null;
  const a = site.arm, reach = a.pivot_h_m / Math.tan(Math.min(arm.tilt, 90) * DEG);
  const ang = (a.heading_deg + arm.pan) * DEG;
  return [a.xy[0] + reach * Math.cos(ang), a.xy[1] + reach * Math.sin(ang)];
}
let lastDraw = performance.now();
function draw(truth, arm, relay, dot) {
  const now = performance.now(), dt = Math.min(0.2, (now - lastDraw) / 1000); lastDraw = now;
  const seen = new Set();
  for (const w of truth?.workers ?? []) {
    seen.add(w.id);
    const r = workers.get(w.id) ?? workers.set(w.id, workerRig()).get(w.id);
    const u = r.userData;
    if (u.last) {
      const dx = w.x - u.last[0], dy = w.y - u.last[1];
      if (Math.hypot(dx, dy) > 0.01) u.heading = Math.atan2(dy, dx);
    }
    u.last = [w.x, w.y];
    r.position.copy(P(w.x, w.y, 0));
    r.rotation.y = u.heading - Math.PI / 2;
    poseRig(r, w.posture ?? 'stand', now / 1000, dt);
    u.vest.color.set(w.edge_m <= 1.5 ? 0xef4444 : w.edge_m <= 3.0 ? 0xf59e0b : 0xe8f02a);
  }
  for (const [id, m] of workers) if (!seen.has(id)) { scene.remove(m); workers.delete(id); }
  dot = dot ?? beam(arm);
  objs.laser.visible = objs.dot.visible = !!dot;
  if (dot) {
    const a = site.arm, from = P(a.xy[0], a.xy[1], a.pivot_h_m), to = P(dot[0], dot[1], 0.02);
    objs.laser.position.copy(from.clone().add(to).multiplyScalar(0.5));
    objs.laser.scale.set(1, from.distanceTo(to), 1);
    objs.laser.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), to.clone().sub(from).normalize());
    objs.dot.position.copy(to);
  }
  const strobeOn = relay?.strobe && (Date.now() % 500 < 250);
  objs.strobe.material.emissive.set(strobeOn ? 0xff6a00 : 0x000000);
  objs.strobe.material.emissiveIntensity = strobeOn ? 6 : 0;
  const floodOn = !!relay?.floodlight;
  objs.flood.visible = floodOn && environment.night;
  objs.spot.intensity = floodOn && environment.night ? 80 : 0;
}

// ------------------------------------------------------------------ sky, sun and weather
const environment = { night: false, name: null };
function singaporeHour() {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Singapore', hour: 'numeric', minute: 'numeric', hour12: false }).formatToParts(new Date());
  const get = (t) => +parts.find(p => p.type === t)?.value || 0;
  return get('hour') + get('minute') / 60;
}
function setEnvironment(name) {
  const preset = site?.weathers.find(w => w.name === name);
  if (!preset || (environment.name === name && environment.hour === Math.floor(singaporeHour() * 4))) return;
  environment.name = name; environment.hour = Math.floor(singaporeHour() * 4);
  environment.night = preset.night;
  let h = singaporeHour();
  if (!preset.night && (h < 7.5 || h > 18.5)) h = 10;          // the world shows day: keep the sky in step
  const elev = preset.night ? -10 : Math.max(5, 75 * Math.sin(Math.PI * (h - 7) / 12));
  const az = 90 + (h - 7) / 12 * 180;                             // east in the morning, west in the evening
  const sunDir = new THREE.Vector3().setFromSphericalCoords(1, (90 - elev) * DEG, az * DEG);
  sky.material.uniforms.sunPosition.value.copy(sunDir);
  sky.visible = !preset.night;
  sun.position.copy(sunDir.clone().multiplyScalar(60)); sun.target.position.set(0, 0, 0);
  const overcast = 1 - Math.min(1, preset.light);
  sun.intensity = preset.night ? 0.05 : 2.4 * Math.max(0.15, preset.light);
  hemi.intensity = preset.night ? 0.08 : 0.35 + 0.35 * (1 - overcast);
  sky.material.uniforms.turbidity.value = 4 + 14 * overcast;
  scene.background = preset.night ? new THREE.Color(0x05070d) : null;
  const vis = preset.visibility_m ?? 20000;
  scene.fog = vis < 5000 ? new THREE.FogExp2(preset.night ? 0x0b0e14 : 0xc9ced6, Math.min(0.08, 2.5 / vis)) : null;
  groundMat.roughness = preset.wet_ground ? 0.35 : 0.95;
  groundMat.color.set(preset.wet_ground ? 0xb8b0a8 : 0xffffff);
  rain.set(preset.rain_mm_h > 0);
  renderer.toneMappingExposure = preset.night ? 1.4 : 0.5;
}

// ------------------------------------------------------------------ px/m heatmap
let heat = null;
async function toggleHeatmap(on) {
  if (heat) heat.visible = on;
  if (!on || heat) return;
  const c = await api('/api/coverage');
  const cv = document.createElement('canvas'); cv.width = c.nx; cv.height = c.ny;
  const g = cv.getContext('2d'), img = g.createImageData(c.nx, c.ny);
  for (let j = 0; j < c.ny; j++) for (let i = 0; i < c.nx; i++) {
    const v = c.ppm[j][i], k = ((c.ny - 1 - j) * c.nx + i) * 4;
    const [r, gg, b, a] = v <= 0 ? [0, 0, 0, 0] : v >= 100 ? [34, 197, 94, 120] : v >= 60 ? [245, 158, 11, 130] : [239, 68, 68, 140];
    img.data.set([r, gg, b, a], k);
  }
  g.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(cv); tex.magFilter = THREE.NearestFilter;
  const w = c.nx * c.step, h = c.ny * c.step;
  heat = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }));
  heat.rotation.x = -Math.PI / 2;
  heat.position.copy(P(c.x0 - c.step / 2 + w / 2, c.y0 - c.step / 2 + h / 2, 0.025));
  scene.add(heat);
  toast(`heatmap: ring corners ${c.corners.map(p => `${p.ppm.toFixed(0)}`).join(', ')} px/m`);
}
$('heatmap').onchange = (e) => toggleHeatmap(e.target.checked).catch(err => toast(err.message));

// ------------------------------------------------------------------ frame loop
function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h, false); composer.setSize(w, h); bloom.setSize(w / 2, h / 2);
  cam3.aspect = w / h; cam3.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(view);
let frames = 0, fpsT = performance.now(), prevT = performance.now();
renderer.setAnimationLoop(() => {
  const now = performance.now(), dt = Math.min(0.1, (now - prevT) / 1000); prevT = now;
  controls.update();
  rain.step(dt, 1.5);
  if (QUALITY[quality].bloom) composer.render(); else renderer.render(scene, cam3);
  frames++;
  if (now - fpsT > 1000) {
    const c = renderer.domElement, line = `${Math.round(frames * 1000 / (now - fpsT))} fps at ${c.width}×${c.height} (${quality})`;
    $('fps').textContent = line; $('fsfps').textContent = line; frames = 0; fpsT = now;
  }
});

$('fullscreen').onclick = () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else view.requestFullscreen().catch(e => toast(`full screen refused: ${e.message}`));
};
document.addEventListener('fullscreenchange', () => {
  $('fullscreen').textContent = document.fullscreenElement ? '✕ leave full screen' : '⛶ full screen';
  resize();
});

// ------------------------------------------------------------------ HUD
function hud() {
  if (!site) return;
  const st = live?.status, level = live ? levelOf(live) : 'monitoring';
  const dwell = Math.max(0, ...(st?.people ?? []).map(p => p.zone_s));
  const parts = [`<div><span class="k">alarm</span> <b class="${level}">${level.toUpperCase()}</b>${dwell > 0 ? ` · in zone ${dwell.toFixed(1)} s` : ''}</div>`];
  if (hudData?.profile === 'v11') {
    const pw = hudData.power, poe = hudData.poe, d = hudData.data, plan = $('plan').value || pw.plan;
    const cut = hudData.power_cut;
    parts.push(`<div><span class="k">power</span> Plan ${plan} · ${pw.average_load_w} W average · battery ${(pw.battery_wh / 1000).toFixed(2)} kWh`
      + (cut ? `<br><b class="alarm">site power cut</b>: ${cut.events.filter(e => e[1].startsWith('Stage')).map(e => `${e[1].split(':')[0]} +${e[0]} h`).join(', ') || 'on battery'}` : '') + '</div>');
    parts.push(`<div><span class="k">PoE</span> ${poe.draw_w} W used, ${poe.reserved_w} W reserved of ${poe.budget_w} W`
      + `<div class="bar"><i class="res" style="width:${100 * poe.reserved_w / poe.budget_w}%"></i><i style="width:${100 * poe.draw_w / poe.budget_w}%"></i></div></div>`);
    parts.push(`<div><span class="k">4G</span> ${live?.mqtt ? 'uplink up' : '<b class="alarm">uplink down</b>'} · ${d.month_to_date_gb} GB this month (estimate ${d.month_estimate_gb} of ${d.plan_gb} GB)</div>`);
  }
  const active = Object.keys(live?.faults ?? {});
  parts.push(`<div><span class="k">faults</span> ${active.length ? `<b class="warning">${active.join(', ')}</b>` : 'none'}</div>`);
  $('hud').innerHTML = parts.join('');
}
async function refreshHud() { try { hudData = await api('/api/v11/hud'); } catch { /* stack starting */ } }
$('plan').onchange = () => { if (objs.skid) objs.skid.visible = ['B', 'C'].includes($('plan').value); hud(); };

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
  setEnvironment(live.weather ?? 'clear');
  draw(live.truth, live.arm, live.relay, live.dot);
  setLevel(levelOf(live));
  hud();
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
const POSTURE_KEYS = { c: 'squat', k: 'kneel' };
const typing = (e) => ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName) && e.target.type !== 'checkbox';
window.addEventListener('keydown', (e) => {
  if (!$('kbd').checked || typing(e)) return;
  if (e.key === 'Shift') $('run').checked = true;
  const posture = POSTURE_KEYS[e.key.toLowerCase?.()];
  if (posture && !e.repeat) { send({ type: 'cmd', cmd: 'posture', posture }); return; }
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
document.querySelectorAll('[data-posture]').forEach(b => b.addEventListener('click', () => send({ type: 'cmd', cmd: 'posture', posture: b.dataset.posture })));

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
    const inj = document.createElement('button');
    inj.textContent = name === 'power_cut' ? 'cut + restore' : name === 'switch_restart' ? 'restart' : 'inject';
    const res = document.createElement('button'); res.textContent = 'restore';
    inj.onclick = () => api(`/fault/${name}`, 'POST').then(() => { toast(`fault injected: ${label}`); refreshHud(); }).catch(e => toast(`${name}: ${e.message}`));
    res.onclick = () => api(`/fault/${name}/restore`, 'POST').then(() => { toast(`restored: ${label}`); refreshHud(); }).catch(e => toast(`${name}: ${e.message}`));
    $('faults').append(l, inj, res);
  }
  if (s.plans?.length) {
    $('plan').innerHTML = s.plans.map(p => `<option>${p}</option>`).join('');
    $('planPick').hidden = false;
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
    `<label><input type="checkbox" value="${p.id}" checked>${p.id}${p.fitted ? ' (fitted)' : ''}${p.legacy ? ' (legacy)' : ''}${p.verified ? '' : ' *'}</label>`).join('');
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

// ------------------------------------------------------------------ v11 what-if
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let wiBase = null, wiTimer = null;
async function buildWhatIf() {
  wiBase = await api('/api/v11/whatif');
  $('wiProducts').innerHTML = wiBase.products.map(p => `<div class="wi-prod"><b>${esc(p.id)}</b>${p.verified ? '' : ' *'}
      <div class="muted">${esc(p.name)}</div><div class="flds">${Object.entries(p.fields).map(([f, v]) =>
      `<label>${f} <input type="number" step="any" data-prod="${esc(p.id)}" data-field="${f}" value="${v}" data-base="${v}"></label>`).join('')}</div></div>`).join('');
  $('wiSite').innerHTML = Object.entries(wiBase.site).map(([k, f]) =>
    `<label>${esc(f.label)}${f.unit ? ` (${esc(f.unit)})` : ''} <input type="number" step="any" data-site="${k}" value="${f.value}" data-base="${f.value}"></label>`).join('');
  document.querySelectorAll('#whatifPanel input[type=number]').forEach(i => i.addEventListener('input', () => {
    i.classList.toggle('edited', i.value !== i.dataset.base);
    clearTimeout(wiTimer); wiTimer = setTimeout(recalc, 350);
  }));
  showWhatIf(wiBase.result);
}
async function recalc() {
  const products = {}, settings = {};
  document.querySelectorAll('#whatifPanel input.edited').forEach(i => {
    if (i.value === '') return;
    if (i.dataset.prod) (products[i.dataset.prod] ??= {})[i.dataset.field] = +i.value;
    else settings[i.dataset.site] = +i.value;
  });
  $('wiInfo').textContent = 'working it out...';
  try { showWhatIf(await api('/api/v11/whatif', 'POST', { products, settings })); } catch (e) { $('wiInfo').textContent = e.message; }
}
function showWhatIf(r) {
  $('wiChecks').innerHTML = '<tr><th>check</th><th></th><th>result</th></tr>' + r.checks.map(c =>
    `<tr><td>${esc(c.name)}</td><td class="${c.ok ? 'ok' : 'bad'}">${c.ok ? 'OK' : 'FAIL'}</td><td>${esc(c.detail)}</td></tr>`).join('');
  $('wiPlans').innerHTML = '<tr><th>plan</th><th>cost (S$)</th><th>average load</th><th>battery</th><th>panels</th><th>lowest charge</th></tr>'
    + Object.entries(r.plans).map(([k, p]) => `<tr><td>${k}</td><td>${r.costs_sgd[k].toLocaleString()}</td><td>${p.average_load_w} W</td>`
      + `<td>${(p.battery_wh / 1000).toFixed(2)} kWh</td><td>${p.panel_w} W</td><td class="${p.ok ? 'ok' : 'bad'}">${p.lowest}${p.stage2 ? ' (Stage 2)' : ''}</td></tr>`).join('')
    + `<tr><td colspan="6" class="muted">Plan A with the socket off ${r.plan_a_socket_off.hours} h: ${r.plan_a_socket_off.hours_without_alarm} h without an alarm, `
    + `router on ${r.plan_a_socket_off.router_hours_after_stage2} h after Stage 2. Coverage q ${r.coverage.q}, D ${r.coverage.D}; largest zone `
    + `${r.coverage.largest_zone.fov[0]} m (field of view), ${r.coverage.largest_zone.distortion?.[0] ?? '-'} m (distortion).</td></tr>`;
  const n = r.edited.products.length + r.edited.settings.length;
  $('wiInfo').textContent = n ? `${n} change(s) from the catalogue · worked out in ${r.elapsed_s} s` : 'catalogue values';
}
$('wiReset').onclick = () => {
  document.querySelectorAll('#whatifPanel input[type=number]').forEach(i => { i.value = i.dataset.base; i.classList.remove('edited'); });
  showWhatIf(wiBase.result);
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
  setEnvironment(f.weather ?? 'clear');
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
if (site.render?.width) $('video').style.aspectRatio = `${site.render.width} / ${site.render.height}`;
buildSite(site); buildPanels(site); applyQuality(); setEnvironment('clear'); connect(); startVideo();
refreshHud(); setInterval(refreshHud, 10000);
buildProducts().catch(e => toast(e.message)); loadRuns().catch(() => {});
buildWhatIf().catch(e => { $('wiInfo').textContent = `what-if unavailable: ${e.message}`; });
