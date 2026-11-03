"""The phone's picture: IP Webcam's RTSP or MJPEG stream, a recording, full-resolution stills and
the phone's sensors. N and the frame height come from the frames actually received."""
from __future__ import annotations

import logging
import math
import os
import re
import time

import cv2
import numpy as np

log = logging.getLogger("fieldtest")

REC_NAME = "rec_%H%M%S.mp4"         # time.strftime: a recording's name
OPEN_TRIES, OPEN_WAIT_S = 5, 2.0    # a phone app restarts its server for a few seconds after a viewer leaves


def hide_password(url):
    """rtsp://user:secret@host/... -> rtsp://user:***@host/... (for logs and the page)."""
    return re.sub(r"(//[^/:@]+:)[^@/]*@", r"\1***@", str(url))


def is_stream(url):
    """A network stream (rtsp://, http://), not a recording on disk."""
    return "://" in str(url) and not os.path.exists(str(url))


def is_4_3(w, h):
    return abs(w * 3 - h * 4) <= 0.01 * max(w, h)


def shape_warning(w, h):
    """None for a 4:3 frame, else why the 4:3 lens values do not apply."""
    if is_4_3(w, h):
        return None
    shape = "16:9" if abs(w * 9 - h * 16) <= 0.01 * max(w, h) else f"{w}:{h}"
    return (f"the frame is {w} × {h}, cropped to {shape}, so the 4:3 lens values do not apply: "
            f"calibrate the lens at this size before using the overlay")


def overlay_allowed(size, lens):
    """The overlay runs on a 4:3 frame, or on any frame once the lens is calibrated at that size."""
    return is_4_3(*size) or (lens is not None and lens.calibrated and tuple(lens.size) == tuple(size))


class Source:
    """Frames from a stream URL or a recording file. `size` is the size received; a change of size
    during a session is logged in `warnings`."""

    def __init__(self, url):
        self.url, self.shown, self.stream = url, hide_password(url), is_stream(url)
        if str(url).startswith("rtsp://"):          # RTSP over TCP, as app/health.py: UDP is lossy on Wi-Fi
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        self.size, self.warnings, self.frames = None, [], 0
        self._open()

    def _open(self):
        """Open the source, retrying a stream (not a file) before giving up."""
        for attempt in range(OPEN_TRIES if self.stream else 1):
            if attempt:
                log.warning("cannot open %s, trying again (%d of %d)", self.shown, attempt + 1, OPEN_TRIES)
                time.sleep(OPEN_WAIT_S)
            self.cap = cv2.VideoCapture(self.url)
            if self.cap.isOpened():
                break
        else:
            hint = (": is the phone app serving, with the screen on? An app that stops after each viewer "
                    "needs ▶ pressed again; close other viewers (ffplay, VLC)"
                    if self.stream else "")
            raise OSError(f"cannot open {self.shown}{hint}")
        self.file_fps = self.cap.get(cv2.CAP_PROP_FPS) or 0.0
        self.t0 = time.monotonic()

    def reopen(self):
        """Start again after a dropped stream or the end of a recording; a changed size is still warned."""
        self.cap.release()
        self._open()

    def writer(self, path):
        """A video writer for this source's frames."""
        fps = self.file_fps if 0 < self.file_fps < 61 else 15.0
        return cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, tuple(self.size))

    def read(self):
        """(frame, t seconds) or (None, None) at the end of a recording."""
        ok, frame = self.cap.read()
        if not ok:
            return None, None
        size = (frame.shape[1], frame.shape[0])
        if self.size is None:
            self.size = size
            w = shape_warning(*size)
            if w:
                self.warnings.append(w)
        elif size != self.size:
            self.warnings.append(f"the frame size changed from {self.size[0]} × {self.size[1]} to {size[0]} × {size[1]}")
            log.warning(self.warnings[-1])
            self.size = size
        self.frames += 1
        msec = self.cap.get(cv2.CAP_PROP_POS_MSEC)
        return frame, (msec / 1000.0 if msec else time.monotonic() - self.t0)

    def __iter__(self):
        while True:
            frame, t = self.read()
            if frame is None:
                return
            yield t, frame

    def close(self):
        self.cap.release()


def fetch(url, timeout=10.0):
    """Bytes from an IP Webcam HTTP endpoint; a login in the URL is sent as basic auth."""
    import httpx
    m = re.match(r"(https?://)([^/:@]+):([^@/]*)@(.*)", url)
    auth = (m.group(2), m.group(3)) if m else None
    r = httpx.get(m.group(1) + m.group(4) if m else url, auth=auth, timeout=timeout)
    r.raise_for_status()
    return r.content


def still(url):
    """A full-resolution photo from IP Webcam's photo endpoint."""
    img = cv2.imdecode(np.frombuffer(fetch(url), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"{hide_password(url)} did not return an image")
    return img


def gravity(sensors):
    """The latest gravity vector (or accelerometer reading) from IP Webcam's sensors.json, or None."""
    for key in ("gravity", "accel"):
        data = (sensors.get(key) or {}).get("data") or []
        if data:
            return np.asarray(data[-1][1][:3], dtype=np.float64)
    return None


def gravity_angles(g):
    """(pitch down, roll right side down) in degrees from the gravity vector, for the phone held in
    landscape with its top to the left, back camera forward: image right = −y, image down = −x and
    forward = −z in the phone's axes. A cross-check only; the cones decide the pose."""
    g = np.asarray(g, dtype=np.float64)
    up = np.array([-g[1], -g[0], -g[2]]) / np.linalg.norm(g)      # 'up' in camera axes (right, down, forward)
    return math.degrees(math.asin(np.clip(-up[2], -1, 1))), math.degrees(math.asin(np.clip(-up[0], -1, 1)))


def probe(url, seconds=3.0):
    """Frame size, fps and warnings of a stream."""
    src = Source(url)
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < seconds:
            frame, _ = src.read()
            if frame is None:
                break
    finally:
        src.close()
    dt = time.monotonic() - t0
    return {"url": src.shown, "size": src.size, "fps": round(src.frames / dt, 1) if dt > 0 else 0.0,
            "frames": src.frames, "warnings": src.warnings}
