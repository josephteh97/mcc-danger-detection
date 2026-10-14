"""Person detectors.

oracle: reads ground-truth person boxes from the twin's world over UDP, with a configurable
        delay, jitter and miss rate, and drops the true IDs so the tracker is exercised.
yolo:   runs an ONNX person detector on the camera frame (TensorRT on the real Orin).
"""
from __future__ import annotations

import json
import random
import socket
from collections import deque


class OracleDetector:
    def __init__(self, udp=None, delay_ms=120, jitter_ms=20, miss_rate=0.02, box_jitter_px=2.0,
                 min_visible=0.5, seed=None):
        self.delay, self.jitter = delay_ms / 1000.0, jitter_ms / 1000.0
        self.miss_rate, self.box_jitter, self.min_visible = miss_rate, box_jitter_px, min_visible
        self.rng = random.Random(seed)
        self.pending, self.current, self.current_t = deque(), [], None
        self.sock = None
        if udp:
            host, _, port = udp.rpartition(":")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((host or "0.0.0.0", int(port)))
            self.sock.setblocking(False)

    def feed(self, truth, now):
        """Take one ground-truth message (as sent by the world) that arrived at `now`."""
        boxes = []
        for w in truth.get("workers", []):
            box = w.get("box")
            if not box or w.get("visible", 1.0) < self.min_visible:
                continue
            if self.rng.random() < self.miss_rate:
                continue
            j = self.box_jitter
            boxes.append(tuple(float(v) + self.rng.uniform(-j, j) for v in box))
        release = now + max(0.0, self.delay + self.rng.uniform(-self.jitter, self.jitter))
        self.pending.append((release, boxes))

    def _receive(self, now):
        if self.sock is None:
            return
        while True:
            try:
                data = self.sock.recv(65535)
            except (BlockingIOError, InterruptedError):
                return
            try:
                self.feed(json.loads(data), now)
            except ValueError:
                pass

    def run(self, frame=None, now=None):
        """Boxes [(x0, y0, x1, y1), ...] available at `now` (latest delayed truth)."""
        self._receive(now)
        while self.pending and self.pending[0][0] <= now:
            self.current_t, self.current = self.pending.popleft()
        if self.current_t is None or now - self.current_t > 1.0:    # truth stopped arriving
            return []
        return list(self.current)


class YoloDetector:
    """ONNX person detector (YOLOv8-style output). Accuracy is checked on recorded site
    footage (V17), not on the twin's renderer."""

    def __init__(self, model, conf=0.4, nms=0.5, size=640):
        import cv2
        self.cv2, self.conf, self.nms, self.size = cv2, conf, nms, size
        self.net = cv2.dnn.readNetFromONNX(model)

    def run(self, frame, now=None):
        cv2, s = self.cv2, self.size
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (s, s), swapRB=True)
        self.net.setInput(blob)
        out = self.net.forward()[0].T                     # (anchors, 4 + classes)
        boxes, scores = [], []
        for row in out:
            score = float(row[4])                         # class 0 = person
            if score < self.conf:
                continue
            cx, cy, bw, bh = row[:4]
            boxes.append([(cx - bw / 2) * w / s, (cy - bh / 2) * h / s, bw * w / s, bh * h / s])
            scores.append(score)
        keep = cv2.dnn.NMSBoxes(boxes, scores, self.conf, self.nms)
        return [(b[0], b[1], b[0] + b[2], b[1] + b[3]) for b in (boxes[i] for i in keep)]


def make_detector(cfg):
    mode = cfg.get("mode", "oracle")
    if mode == "oracle":
        return OracleDetector(cfg.get("oracle_udp"), cfg.get("oracle_delay_ms", 120),
                              cfg.get("oracle_jitter_ms", 20), cfg.get("oracle_miss_rate", 0.02))
    if mode == "yolo":
        return YoloDetector(cfg["model"], cfg.get("conf", 0.4))
    raise ValueError(f"unknown detector mode {mode!r} (oracle or yolo)")
