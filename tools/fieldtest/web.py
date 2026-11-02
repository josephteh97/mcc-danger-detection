"""The field-test page (design.md D1): the live picture with the overlay as MJPEG, clicks for cones
and measurements, and a button per step. Clicking happens in the browser, so OpenCV stays
headless. Binds to 127.0.0.1 unless told otherwise; never joins the twin's networks."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from tools.fieldtest import REPORTS, describe_pitch, load_phone, report_dir
from tools.fieldtest import calib as cb
from tools.fieldtest import lens as ln
from tools.fieldtest import report as rp
from tools.fieldtest import session as ss
from tools.fieldtest import source as src

log = logging.getLogger("fieldtest")


class Live:
    """The open source, the latest frame and the session being built."""

    def __init__(self, url, preset="default", rho=None, loop=False):
        self.phone = load_phone()
        self.url, self.loop = url, loop
        self.src = src.Source(url)
        frame, _ = self.src.read()
        if frame is None:
            raise OSError(f"no frames from {self.src.shown}")
        self.frame, self.lock, self.stop = frame, threading.Lock(), False
        self.folder = report_dir()
        self.session = ss.new(self.src.size, self.src.shown, preset, self.phone, rho=rho)
        lens = ln.load(REPORTS, self.src.size)
        if lens:
            self.session["lens"] = lens.to_dict()
        self.overlay, self.views, self.writer, self.rec_path = True, [], None, None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        period = 1.0 / self.src.file_fps if os.path.exists(self.url) and self.src.file_fps else 0.0
        while not self.stop:
            t0 = time.monotonic()
            frame, _ = self.src.read()
            if frame is None:                    # a recording loops; a dropped stream reconnects
                if not (self.loop or src.is_stream(self.url)):
                    break
                self.src.close()
                try:
                    new = src.Source(self.url)
                    new.size = self.src.size             # the page keeps its size; a change is still warned
                    self.src = new
                except OSError as e:
                    log.warning("%s; trying again", e)
                    time.sleep(2.0)
                continue
            with self.lock:
                self.frame = frame
                if self.writer is not None:
                    self.writer.write(frame)
            if period:
                time.sleep(max(0.0, period - (time.monotonic() - t0)))

    def save(self):
        return ss.save(self.session, os.path.join(self.folder, "session.json"))

    def picture(self):
        with self.lock:
            frame = self.frame.copy()
        result, cam, z = ss.evaluate(self.session)
        if self.overlay and src.overlay_allowed(self.src.size, ss.lens_of(self.session)):
            return rp.annotate(frame, self.session, cam, z)
        return frame

    def state(self):
        result, cam, z = ss.evaluate(self.session)
        lens = ss.lens_of(self.session)
        return {"source": self.src.shown, "size": self.src.size, "warnings": self.src.warnings,
                "pitch": describe_pitch(self.phone, self.src.size[0], self.session["focal_equiv_mm"]),
                "overlay_allowed": src.overlay_allowed(self.src.size, lens), "views": len(self.views),
                "recording": self.rec_path, "folder": self.folder, "session": self.session,
                **{k: result[k] for k in ("steps", "nominal", "pose", "zone", "layout", "corners", "overlay", "measurements")}}


def make_app(live):
    app = FastAPI(title="Field test")

    def changed():
        live.save()
        return live.state()

    @app.get("/", response_class=HTMLResponse)
    def page():
        return PAGE

    @app.get("/stream")
    async def stream():
        async def frames():
            while True:
                ok, jpg = cv2.imencode(".jpg", await asyncio.to_thread(live.picture), [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"
                await asyncio.sleep(0.1)
        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/state")
    def state():
        return live.state()

    @app.post("/api/settings")
    def settings(body: dict):
        for k in ("rho", "focal_equiv_mm", "taped_height_m"):
            if body.get(k) not in (None, ""):
                live.session[k] = float(body[k])
        if "overlay" in body:
            live.overlay = bool(body["overlay"])
        return changed()

    @app.post("/api/cone")
    def cone(body: dict):
        live.session["cones"].append({"name": body.get("name") or "", "x": float(body["x"]), "y": float(body["y"]),
                                      "u": float(body["u"]), "v": float(body["v"])})
        return changed()

    @app.post("/api/measure")
    def measure(body: dict):
        live.session["measurements"].append({"label": body.get("label", ""), "length_m": float(body.get("length_m", 1.0)),
                                             "bottom": [float(c) for c in body["bottom"]], "top": [float(c) for c in body["top"]]})
        try:
            return changed()
        except ValueError as e:
            live.session["measurements"].pop()
            raise HTTPException(400, str(e))

    @app.post("/api/undo")
    def undo(body: dict):
        items = live.session["cones" if body.get("what") == "cone" else "measurements"]
        if items:
            items.pop()
        return changed()

    @app.post("/api/calib/capture")
    def capture():
        with live.lock:
            frame = live.frame.copy()
        corners = cb.find_corners(frame, live.phone["checkerboard"]["inner_corners"])
        if corners is None:
            raise HTTPException(400, "no checkerboard in this frame")
        live.views.append(corners)
        return live.state()

    @app.post("/api/calib/solve")
    def calibrate():
        b = live.phone["checkerboard"]
        try:
            lens = cb.calibrate(live.views, b["inner_corners"], b["square_mm"] / 1000, live.src.size, b["min_views"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        ln.save(lens, REPORTS)
        live.session["lens"] = lens.to_dict()
        return changed()

    @app.post("/api/sensors")
    def sensors():
        url = live.phone.get("sensors_url")
        try:
            import json
            g = src.gravity(json.loads(src.fetch(url)))
        except Exception as e:              # the sensors are a cross-check only
            raise HTTPException(400, f"no sensor data from {src.hide_password(url)}: {e.__class__.__name__}")
        if g is None:
            raise HTTPException(400, "sensors.json has no gravity or accelerometer data")
        pitch, roll = src.gravity_angles(g)
        live.session["sensors"] = {"pitch_deg": pitch, "roll_deg": roll}
        return changed()

    @app.post("/api/record")
    def record(body: dict):
        with live.lock:
            if body.get("on") and live.writer is None:
                live.rec_path = os.path.join(live.folder, time.strftime("rec_%H%M%S.mp4"))
                fps = live.src.file_fps if 0 < live.src.file_fps < 61 else 15.0
                live.writer = cv2.VideoWriter(live.rec_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, tuple(live.src.size))
            elif not body.get("on") and live.writer is not None:
                live.writer.release()
                live.writer = None
        return live.state()

    @app.post("/api/report")
    def report():
        result, cam, z = ss.evaluate(live.session)
        with live.lock:
            frame = live.frame.copy()
        live.save()
        return {"report": rp.write(live.session, result, cam, z, live.folder, frame)}

    return app


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Field test</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font:14px system-ui,sans-serif;margin:0;background:#111;color:#ddd}
main{display:flex;gap:12px;padding:12px;flex-wrap:wrap}
#pic{max-width:min(100%,1100px);cursor:crosshair;border:1px solid #333}
aside{flex:1;min-width:300px}
fieldset{border:1px solid #333;margin:0 0 10px;padding:8px}
input{width:5em;background:#222;color:#eee;border:1px solid #444}
button{background:#2a4;color:#fff;border:0;padding:4px 8px;margin:2px;cursor:pointer}
button.off{background:#444}
pre{white-space:pre-wrap;font-size:12px;background:#1a1a1a;padding:6px;max-height:40vh;overflow:auto}
.warn{color:#fb4}.fail{color:#f66}.pass{color:#6d6}
</style></head><body><main>
<div><img id="pic" src="/stream" alt="live picture"><div id="hint"></div></div>
<aside>
<fieldset><legend>Settings</legend>
ρ <input id="rho"> px/m · focal <input id="focal"> mm · taped height <input id="height"> m
<button onclick="settings()">Apply</button> <button id="ov" onclick="toggleOverlay()">Overlay on</button>
<div id="warn" class="warn"></div><div id="pitch"></div></fieldset>
<fieldset><legend>Click mode</legend>
<button onclick="mode('cone')">Cone</button> x <input id="cx"> y <input id="cy">
name <select id="cname"><option></option><option>far left</option><option>far right</option><option>near right</option><option>near left</option></select><br>
<button onclick="mode('measure')">Measure</button> length <input id="len" value="1.0"> m label <input id="lab" style="width:8em">
(click the base, then the top)<br>
<button class="off" onclick="post('/api/undo',{what:'cone'})">Undo cone</button>
<button class="off" onclick="post('/api/undo',{what:'measure'})">Undo measurement</button></fieldset>
<fieldset><legend>Steps</legend>
<button onclick="post('/api/calib/capture')">Capture checkerboard</button>
<button onclick="post('/api/calib/solve')">Calibrate</button>
<button onclick="post('/api/sensors')">Read sensors</button>
<button id="rec" onclick="record()">Record</button>
<button onclick="post('/api/report').then(r=>r&&alert('Report: '+r.report))">Write report</button></fieldset>
<pre id="out"></pre></aside></main>
<script>
let M='cone', first=null, S=null;
const $=id=>document.getElementById(id);
function mode(m){M=m;first=null;$('hint').textContent='mode: '+m;}
async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body||{})});
 const j=await r.json(); if(!r.ok){alert(j.detail||r.statusText);return null;} if(j.session)show(j); return j;}
function settings(){post('/api/settings',{rho:$('rho').value,focal_equiv_mm:$('focal').value,taped_height_m:$('height').value});}
function toggleOverlay(){const on=$('ov').textContent!=='Overlay on'; $('ov').textContent=on?'Overlay on':'Overlay off'; post('/api/settings',{overlay:on});}
function record(){const on=!(S&&S.recording); post('/api/record',{on});}
$('pic').addEventListener('click',e=>{const im=e.target, r=im.getBoundingClientRect();
 const u=(e.clientX-r.left)*im.naturalWidth/r.width, v=(e.clientY-r.top)*im.naturalHeight/r.height;
 if(M==='cone'){post('/api/cone',{u,v,x:$('cx').value,y:$('cy').value,name:$('cname').value});}
 else if(!first){first=[u,v];$('hint').textContent='now click the top';}
 else{post('/api/measure',{bottom:first,top:[u,v],length_m:$('len').value,label:$('lab').value});first=null;$('hint').textContent='mode: measure';}});
function show(s){S=s; const ss=s.session;
 if(!$('rho').value){$('rho').value=ss.rho;$('focal').value=ss.focal_equiv_mm;$('height').value=ss.taped_height_m??'';}
 $('warn').textContent=(s.warnings||[]).join(' · ')+(s.overlay_allowed?'':' Overlay off until the lens is calibrated at this size.');
 $('pitch').textContent=s.pitch; $('rec').textContent=s.recording?'Stop recording':'Record';
 const st=Object.entries(s.steps).map(([k,v])=>`${k}: ${v===null?'not run':v?'PASS':'FAIL'}`).join('  ');
 const z=s.zone, p=s.pose, n=s.nominal;
 $('out').textContent=`${s.source}  ${s.size[0]} x ${s.size[1]}  checkerboard views ${s.views}\\n${st}\\n`+
  `f/p ${n.fx.toFixed(1)} (nominal ${n.nominal_fp.toFixed(1)}, ${n.diff_pct.toFixed(2)}%)\\n`+
  `z_max ${z.z_max.toFixed(2)}  W_max ${z.w_max.toFixed(2)}  S ${z.s.toFixed(2)}  d ${z.d.toFixed(2)}  near ${z.near.toFixed(2)} m\\n`+
  (p.height_m!==undefined?`pose: height ${p.height_m.toFixed(3)} m pitch ${p.pitch_deg.toFixed(2)} roll ${p.roll_deg.toFixed(2)} heading ${p.heading_deg.toFixed(2)} reproj ${p.max_reproj_px.toFixed(2)} px\\n`:'pose: click 4-8 cones\\n')+
  'cones: '+ss.cones.map(c=>`${c.name||''}(${c.x},${c.y})`).join(' ')+'\\n'+
  'layout: '+Object.entries(s.layout.corners).map(([k,v])=>`${k} (${v[0]}, ${v[1]})`).join('; ')+'\\n'+
  s.measurements.map(m=>`${m.label} ${m.distance_m.toFixed(2)} m: ${m.predicted_px.toFixed(1)} vs ${m.measured_px.toFixed(1)} px ${m.error_pct.toFixed(1)}% ${m.result}`).join('\\n');}
fetch('/api/state').then(r=>r.json()).then(show); mode('cone');
setInterval(()=>fetch('/api/state').then(r=>r.json()).then(show),3000);
</script></body></html>"""
