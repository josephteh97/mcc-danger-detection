"""Camera capture with a frame-age watchdog.

cv2.VideoCapture on RTSP can block for tens of seconds when the cable is cut, so frames are
read on a background thread and the main loop only looks at how old the newest frame is.
"""
from __future__ import annotations

import logging
import os
import threading
import time

log = logging.getLogger("health")
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000|timeout;5000000")


class FrameSource:
    def __init__(self, url, lost_after_s=3.0):
        self.url, self.lost_after_s = url, lost_after_s
        self._frame, self._t, self._seq = None, None, 0
        self._cond = threading.Condition()
        self._stop = False
        self.started = time.monotonic()
        threading.Thread(target=self._reader, daemon=True, name="capture").start()

    def _reader(self):
        import cv2
        backoff = 1.0
        while not self._stop:
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap.release()
                time.sleep(backoff)
                backoff = min(5.0, backoff * 2)
                continue
            log.info("camera stream opened")
            backoff = 1.0
            while not self._stop:
                ok, frame = cap.read()
                if not ok:
                    break
                with self._cond:
                    self._frame, self._t, self._seq = frame, time.monotonic(), self._seq + 1
                    self._cond.notify_all()
            cap.release()
            log.warning("camera stream closed; reopening")
            time.sleep(0.5)

    def get(self, last_seq, timeout=0.2):
        """Wait up to `timeout` for a frame newer than last_seq. Returns (frame, seq) or (None, last_seq)."""
        with self._cond:
            if self._seq == last_seq:
                self._cond.wait(timeout)
            if self._seq == last_seq:
                return None, last_seq
            return self._frame, self._seq

    def frame_age(self, now=None):
        now = time.monotonic() if now is None else now
        return now - (self._t if self._t is not None else self.started)

    def lost(self, now=None):
        return self.frame_age(now) > self.lost_after_s

    def close(self):
        self._stop = True


class Health:
    """Raises 'camera offline' once per outage (and 'camera online' when it returns)."""

    def __init__(self, emit):
        self.emit, self.camera_ok = emit, True

    def check_camera(self, source, now):
        lost = source.lost(now)
        if lost and self.camera_ok:
            self.camera_ok = False
            log.error("camera offline: no frame for %.1f s", source.frame_age(now))
            self.emit({"kind": "health", "what": "camera_offline", "frame_age_s": round(source.frame_age(now), 1)})
        elif not lost and not self.camera_ok:
            self.camera_ok = True
            log.info("camera online")
            self.emit({"kind": "health", "what": "camera_online"})
        return self.camera_ok
