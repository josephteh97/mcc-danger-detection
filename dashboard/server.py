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
                   "hidden_behind_another": "worker hidden behind another", "demo_loop": "demo loop", "idle": "empty site"}

live = Live(SITE, logs=LOGS, broker=os.environ.get("MQTT_BROKER", "172.30.4.10"),
            pole_id=os.environ.get("POLE_ID", "07"), world_control=os.environ.get("WORLD_CONTROL", "world:9200"))
faults = Faults()
http = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0))


@asynccontextmanager
async def lifespan(_app):
    os.makedirs(LOGS, exist_ok=True)
    live.state["run"] = live.recorder.new_run("startup")
    await live.run_truth()
    tails = asyncio.create_task(live.run_tails())
    live.start_mqtt()
    yield
    tails.cancel()


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
@app.get("/api/site")
def site():
    cam = PinholeCamera.from_site(SITE)
    corners = []
    for u, v in ((0, cam.height), (cam.width, cam.height), (cam.width, 0), (0, 0)):
        g = cam.ground_point(u, v)
        if g is None:                       # above the horizon: cap the footprint at 40 m
            d = cam.rays(np.array([float(u)]), np.array([float(v)]))[0]
            g = (cam.pos[0] + 40 * d[0], cam.pos[1] + 40 * d[1])
        corners.append(g)
    return {"pit": SITE["site"]["pit"], "boundary": SITE["site"]["boundary"],
            "rings": {str(b): fx.ring_points(SITE, b, 120).round(3).tolist()
                      for b in (SITE["zones"]["alarm_buffer_m"], SITE["zones"]["warn_buffer_m"])},
            "camera": {"pos": cam.pos.tolist(), "footprint": corners}, "arm": SITE["arm"],
            "floodlight": SITE["floodlight"], "products": SITE["products"],
            "weathers": [{"name": p.name, "description": p.description} for p in wx.PRESETS.values()],
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
    return await asyncio.to_thread(faults.status)


# ------------------------------------------------------------------ products
@app.get("/api/catalog")
def catalog_list():
    out = {}
    for cat in catalog.CATEGORIES:
        out[cat] = [{"id": p, "name": catalog.load_product(cat, p)["name"],
                     "verified": catalog.load_product(cat, p)["verified"], "fitted": p == SITE["products"][cat]}
                    for p in catalog.list_products(cat)]
    return out


@app.post("/api/compare")
async def compare(body: dict):
    from tools.compare import compare as run_compare
    category, products = body.get("category"), body.get("products") or []
    weathers = body.get("weathers") or ["clear"]
    if category not in catalog.CATEGORIES or not products or len(products) > 6 or len(weathers) > 6:
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
