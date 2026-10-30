"""Twin dashboard: http://localhost:8080 (3D view, browser video, scenarios, products, faults, trial pad)."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
import time
import uuid

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

import catalog
from catalog import effects as fx
from dashboard.faults import FAULTS, Faults, FaultError
from dashboard.live import Live
from world import weather as wx
from world.camera import PinholeCamera
from world.scene import SCENARIO_NAMES

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.environ.get("TWIN_LOGS", "/logs")
CAMERA_HLS = os.environ.get("CAMERA_HLS", "http://172.29.10.20:8888")
SITE = catalog.load_site()
SCENARIO_LABELS = {"single_walk_in": "single walk-in", "two_workers": "two workers at once",
                   "passer_by_ring_edge": "passer-by on the ring edge", "stops_1_6m": "worker stops 1.6 m away",
                   "hidden_behind_another": "worker hidden behind another",
                   "squat_far_edge": "worker squats at the far edge", "demo_loop": "demo loop", "idle": "empty site"}

live = Live(SITE, logs=LOGS, broker=os.environ.get("MQTT_BROKER", "172.30.4.10"),
            pole_id=os.environ.get("POLE_ID", "07"), world_control=os.environ.get("WORLD_CONTROL", "world:9200"))
faults = Faults()
http = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0))


def orin_alive():
    """One watchdog ping: the AI box is running (not hung) and its app wrote status in the last 10 s."""
    try:
        c = faults.container("orin")
        if c.status != "running":
            return False
        res = c.exec_run(["sh", "-c", "echo $(( $(date +%s) - $(stat -c %Y /data/status.json) ))"])
        return res.exit_code == 0 and int(res.output.decode().strip() or 99) < 10
    except Exception:              # paused (exec refused), missing, or the Docker API is down
        return False


async def poe_watchdog():
    """v11: the switch pings the AI box every 10 s and power-cycles port 4 after 3 misses."""
    from devices.poe_watchdog import Watchdog
    dog = Watchdog()
    dog.step(time.monotonic(), True)
    await asyncio.sleep(60)                       # boot grace after the stack starts
    while True:
        await asyncio.sleep(dog.interval_s)
        if "switch_hang" in faults.active:        # the switch itself is hung: no watchdog
            continue
        if dog.step(time.monotonic(), await asyncio.to_thread(orin_alive)):
            live.on_event({"pole": live.pole, "ts": round(time.time(), 3), "kind": "health",
                           "what": "watchdog_power_cycle", "detail": "PoE watchdog power-cycled port 4 (AI box)"})
            await asyncio.to_thread(faults.inject, "power_cut")
            faults.active.pop("orin_hang", None)
            faults.active.pop("power_cut", None)


@asynccontextmanager
async def lifespan(_app):
    os.makedirs(LOGS, exist_ok=True)
    live.state["run"] = live.recorder.new_run("startup")
    await live.run_truth()
    tails = asyncio.create_task(live.run_tails())
    live.start_mqtt()
    dog = asyncio.create_task(poe_watchdog()) if SITE["profile"] == "v11" else None
    yield
    tails.cancel()
    if dog:
        dog.cancel()


app = FastAPI(title="Danger-zone pole twin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


# ------------------------------------------------------------------ live feed
@app.websocket("/live")
async def live_ws(ws: WebSocket):
    """The 3D page subscribes here (15 updates a second); the trial pad sends keys back."""
    await ws.accept()

    async def sender():
        while True:
            await ws.send_json({**live.snapshot(), "faults": faults.active, "server_t": time.time()})
            await asyncio.sleep(1 / 15)
    task = asyncio.create_task(sender())
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "keys":
                keys = [k for k in msg.get("keys", []) if k in ("up", "down", "left", "right")]
                live.control({"cmd": "keys", "keys": keys, "run": bool(msg.get("run"))})
            elif msg.get("type") == "cmd" and msg.get("cmd") in ("add_worker", "switch", "reset"):
                live.control({"cmd": msg["cmd"]})
            elif msg.get("type") == "cmd" and msg.get("cmd") == "posture" and msg.get("posture") in ("squat", "kneel"):
                live.control({"cmd": "posture", "posture": msg["posture"]})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        task.cancel()


@app.get("/api/state")
def state():
    return {**live.snapshot(), "faults": faults.active}


# ------------------------------------------------------------------ video (same origin as the page)
@app.api_route("/video/{path:path}", methods=["GET", "HEAD"])
async def video(path: str, request: Request):
    url = f"{CAMERA_HLS}/{path}"
    try:
        req = http.build_request(request.method, url, params=dict(request.query_params))
        upstream = await http.send(req, stream=True, follow_redirects=True)   # MediaMTX cookie-check redirect
    except httpx.HTTPError as e:
        raise HTTPException(502, f"camera stream unavailable: {e.__class__.__name__}")
    headers = {k: v for k, v in upstream.headers.items() if k.lower() in ("content-type", "cache-control")}
    return StreamingResponse(upstream.aiter_raw(), status_code=upstream.status_code, headers=headers,
                             background=BackgroundTask(upstream.aclose))


# ------------------------------------------------------------------ site, scenarios, weather
def _footprint(cam, lens, per_edge=12):
    """The camera's ground footprint, traced along the frame edge through the lens (bowed in v11)."""
    from app.alarm import undistort_pixel
    w, h = cam.width, cam.height
    edge = [(u, h) for u in np.linspace(0, w, per_edge, endpoint=False)] + \
           [(w, v) for v in np.linspace(h, 0, per_edge, endpoint=False)] + \
           [(u, 0) for u in np.linspace(w, 0, per_edge, endpoint=False)] + \
           [(0, v) for v in np.linspace(0, h, per_edge, endpoint=False)]
    if lens is None:
        edge = edge[::per_edge]                          # a pinhole's footprint is the four corners
    out = []
    for u, v in edge:
        pu, pv = undistort_pixel(float(u), float(v), lens.params if lens else None)
        d = cam.rays(np.array([pu]), np.array([pv]))[0]
        s = 40.0 if d[2] >= -1e-9 else min(40.0, -cam.pos[2] / d[2])    # cap above the horizon at 40 m
        out.append((float(cam.pos[0] + s * d[0]), float(cam.pos[1] + s * d[1])))
    return out


@app.get("/api/site")
def site():
    from world.camera import Lens
    cam = PinholeCamera.from_site(SITE)
    corners = _footprint(cam, Lens.from_site(cam, SITE["fitted"]["camera"]))
    return {"profile": SITE["profile"], "render": SITE["camera"].get("render", {}),
            "pit": SITE["site"]["pit"], "boundary": SITE["site"]["boundary"],
            "rings": {str(b): fx.ring_points(SITE, b, 120).round(3).tolist()
                      for b in (SITE["zones"]["alarm_buffer_m"], SITE["zones"]["warn_buffer_m"])},
            "camera": {"pos": cam.pos.tolist(), "footprint": corners}, "arm": SITE["arm"],
            "floodlight": SITE["floodlight"], "products": SITE["products"],
            "weathers": [{"name": p.name, "description": p.description, "night": p.night, "floodlight": p.floodlight,
                          "rain_mm_h": p.rain_mm_h, "visibility_m": p.visibility_m, "light": p.light,
                          "wet_ground": p.wet_ground} for p in wx.PRESETS.values()],
            "camera_h": float(cam.pos[2]), "plans": list((SITE.get("power_plans") or {}).keys()),
            "scenarios": [{"name": n, "label": SCENARIO_LABELS.get(n, n)} for n in SCENARIO_NAMES], "faults": FAULTS}


async def _storm_events():
    """Thunderstorm: a power surge reboots the Orin, then a 30 s 4G drop."""
    await asyncio.sleep(20)
    if live.state.get("weather") == "thunderstorm":
        await asyncio.to_thread(faults.inject, "power_cut")
    await asyncio.sleep(20)
    if live.state.get("weather") == "thunderstorm":
        await asyncio.to_thread(faults.inject, "4g_outage")
        await asyncio.sleep(30)
        await asyncio.to_thread(faults.restore, "4g_outage")


@app.post("/api/scenario/{name}")
def scenario(name: str):
    if name not in SCENARIO_NAMES:
        raise HTTPException(404, f"unknown scenario; valid: {', '.join(SCENARIO_NAMES)}")
    live.state["run"] = live.recorder.new_run(name)
    live.control({"cmd": "scenario", "name": name})
    return {"ok": True, "scenario": name, "run": live.state["run"]}


@app.post("/api/weather/{name}")
async def weather(name: str):
    try:
        preset = wx.get_preset(name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    live.control({"cmd": "weather", "name": name})
    live.state["weather"] = name
    if preset.events:
        asyncio.create_task(_storm_events())
    return {"ok": True, "weather": name, "events": list(preset.events)}


# ------------------------------------------------------------------ faults
@app.post("/fault/{name}")
async def fault(name: str):
    if name not in FAULTS:
        raise HTTPException(404, f"unknown fault; valid: {', '.join(FAULTS)}")
    try:
        return await asyncio.to_thread(faults.inject, name)
    except (FaultError, Exception) as e:
        return JSONResponse({"ok": False, "fault": name, "error": f"{e.__class__.__name__}: {e}"}, status_code=500)


@app.post("/fault/{name}/restore")
async def fault_restore(name: str):
    if name not in FAULTS:
        raise HTTPException(404, f"unknown fault; valid: {', '.join(FAULTS)}")
    try:
        return await asyncio.to_thread(faults.restore, name)
    except Exception as e:
        return JSONResponse({"ok": False, "fault": name, "error": f"{e.__class__.__name__}: {e}"}, status_code=500)


@app.get("/api/faults")
async def fault_status():
    return {**await asyncio.to_thread(faults.status), "power_cut_plan": faults.power_cut_plan}


@app.get("/api/coverage")
async def coverage_map():
    """px/m in the processed image on a ground grid, for the 3D view's heatmap."""
    from dashboard import v11
    return await asyncio.to_thread(v11.coverage, SITE)


@app.get("/api/v11/hud")
async def hud():
    """HUD numbers: PoE, power plan, 4G data, and a site power cut's stages when one is active."""
    from dashboard import v11
    if SITE["profile"] != "v11":
        return {"profile": SITE["profile"]}
    out = await asyncio.to_thread(v11.hud_static, SITE)
    out["power_cut"] = faults.power_cut_plan
    return {"profile": "v11", **out}


@app.get("/api/v11/whatif")
async def whatif_fields():
    """The numbers the what-if panel can change (products and site settings) and today's results."""
    from dashboard import v11
    fields = await asyncio.to_thread(v11.fields)
    return {**fields, "result": await asyncio.to_thread(v11.whatif)}


@app.post("/api/v11/whatif")
async def whatif(body: dict):
    """Recalculate PoE, power plans, costs, 4G, coverage and laser reach with keyed-in values.
    Body: {"products": {"<id>": {"<field>": value}}, "settings": {"<key>": value}}. Files are untouched."""
    from dashboard import v11
    try:
        return await asyncio.to_thread(v11.whatif, body.get("products"), body.get("settings"))
    except (catalog.CatalogError, ValueError, TypeError, KeyError) as e:
        raise HTTPException(400, f"{e.__class__.__name__}: {e}")


@app.post("/api/v11/router/switch_restart")
async def router_switch_restart():
    """The 4G router's digital output driving the switch-restart relay (called by the router)."""
    if SITE["profile"] != "v11":
        raise HTTPException(404, "the router-driven switch restart exists in the v11 profile only")
    return await asyncio.to_thread(faults.switch_restart)


# ------------------------------------------------------------------ products
@app.get("/api/catalog")
def catalog_list():
    out = {}
    for cat in catalog.CATEGORIES:
        fitted = SITE["products"].get(cat) or []
        fitted = fitted if isinstance(fitted, list) else [fitted]
        out[cat] = [{"id": p, "name": (prod := catalog.load_product(cat, p))["name"], "verified": prod["verified"],
                     "legacy": prod.get("legacy", False), "fitted": p in fitted}
                    for p in catalog.list_products(cat)]
    return out


@app.post("/api/compare")
async def compare(body: dict):
    from tools.compare import compare as run_compare
    category, products = body.get("category"), body.get("products") or []
    weathers = body.get("weathers") or ["clear"]
    if category not in catalog.BASE_CATEGORIES or not products or len(products) > 6 or len(weathers) > 6:
        raise HTTPException(400, "pick a category, 1-6 products and 1-6 weather presets")
    try:
        result = await asyncio.to_thread(run_compare, category, products, weathers)
    except (catalog.CatalogError, ValueError) as e:
        raise HTTPException(400, str(e))
    grid_url = None
    if result["grid"] is not None:
        import cv2
        gid = uuid.uuid4().hex[:12]
        os.makedirs(os.path.join(LOGS, "compare"), exist_ok=True)
        cv2.imwrite(os.path.join(LOGS, "compare", f"{gid}.jpg"), result["grid"], [cv2.IMWRITE_JPEG_QUALITY, 82])
        grid_url = f"/api/compare/{gid}.jpg"
    return {"columns": result["columns"], "rows": result["rows"], "grid": grid_url}


@app.get("/api/compare/{gid}.jpg")
def compare_grid(gid: str):
    path = os.path.join(LOGS, "compare", f"{os.path.basename(gid)}.jpg")
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


# ------------------------------------------------------------------ runs
@app.get("/api/runs")
def runs():
    return live.recorder.list_runs()


@app.get("/api/runs/{run_id}")
def run(run_id: str):
    try:
        return live.recorder.load_run(run_id)
    except FileNotFoundError:
        raise HTTPException(404, "no such run")


@app.get("/healthz")
def healthz():
    return Response("ok")
