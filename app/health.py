"""Camera capture with a frame-age watchdog.

Frames are decoded by an ffmpeg subprocess (RTSP over TCP -> raw BGR) read on a background
thread. If no frame arrives for `lost_after_s`, the main loop raises 'camera offline' and the
reader kills ffmpeg and reconnects, so a cut cable or a rebooting camera never blocks the app.
Falls back to cv2.VideoCapture where ffmpeg is not installed.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time

import numpy as np

log = logging.getLogger("health")


class FrameSource:
    def __init__(self, url, lost_after_s=3.0, size=(1280, 720)):
        self.url, self.lost_after_s, self.size = url, lost_after_s, tuple(size)
        self._frame, self._t, self._seq = None, None, 0
        self._cond = threading.Condition()
        self._stop = False
        self.started = time.monotonic()
        target = self._reader_ffmpeg if shutil.which("ffmpeg") else self._reader_cv2
        threading.Thread(target=target, daemon=True, name="capture").start()

    def _publish(self, frame):
        with self._cond:
            self._frame, self._t, self._seq = frame, time.monotonic(), self._seq + 1
            self._cond.notify_all()

    def _reader_ffmpeg(self):
        w, h = self.size
        nbytes, backoff = w * h * 3, 1.0
        while not self._stop:
            proc = subprocess.Popen(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", self.url,
                 "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=nbytes)
            watchdog = threading.Thread(target=self._kill_if_stalled, args=(proc,), daemon=True)
            watchdog.start()
            got = False
            while not self._stop:
                buf = proc.stdout.read(nbytes)
                if len(buf) < nbytes:
                    break
                if not got:
                    log.info("camera stream opened")
                    got, backoff = True, 1.0
                self._publish(np.frombuffer(buf, np.uint8).reshape(h, w, 3))
            proc.kill()
            proc.wait()
            if got:
                log.warning("camera stream closed; reconnecting")
            time.sleep(backoff)
            backoff = min(5.0, backoff * 2)

    def _kill_if_stalled(self, proc):
        """ffmpeg can hang on a dead TCP connection: kill it when frames stop."""
        opened = time.monotonic()
        while proc.poll() is None and not self._stop:
            time.sleep(0.5)
            last = self._t if self._t is not None and self._t > opened else opened
            if time.monotonic() - last > max(self.lost_after_s, 5.0):
                proc.kill()
                return

    def _reader_cv2(self):
        import cv2
        backoff = 1.0
        while not self._stop:
            cap = cv2.VideoCapture(self.url)
            if not cap.isOpened():
                cap.release()
                time.sleep(backoff)
                backoff = min(5.0, backoff * 2)
                continue
            backoff = 1.0
            while not self._stop:
                ok, frame = cap.read()
                if not ok:
                    break
                self._publish(frame)
            cap.release()
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
