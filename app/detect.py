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


def pixel_height_miss(h_px, factor=1.0):
    """Miss rate for a person h_px tall in the processed image: 2% at 100 px or more, rising
    linearly to 50% at 50 px and to 100% at 30 px, times the weather's contrast factor."""
    if h_px >= 100:
        p = 0.02
    elif h_px >= 50:
        p = 0.5 - (h_px - 50) / 50 * 0.48
    elif h_px >= 30:
        p = 1.0 - (h_px - 30) / 20 * 0.5
    else:
        p = 1.0
    return min(1.0, p * factor)


class OracleDetector:
    """With miss_model 'pixel_height', a box's miss rate follows its height in the processed
    image: the stream box height scaled to the native width (native_px) and then down to the
    detector's input width (input_px), or kept native when the detector runs on tiles."""

    def __init__(self, udp=None, delay_ms=120, jitter_ms=20, miss_rate=0.02, box_jitter_px=2.0,
                 min_visible=0.5, seed=None, miss_model="fixed", native_px=None, input_px=None, tiles=False):
        self.delay, self.jitter = delay_ms / 1000.0, jitter_ms / 1000.0
        self.miss_rate, self.box_jitter, self.min_visible = miss_rate, box_jitter_px, min_visible
        self.miss_model, self.native_w, self.input_px, self.tiles = miss_model, (native_px or [0])[0], input_px, tiles
        self.rng = random.Random(seed)
        self.pending, self.current, self.current_t = deque(), [], None
        self.sock = None
        if udp:
            host, _, port = udp.rpartition(":")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((host or "0.0.0.0", int(port)))
            self.sock.setblocking(False)

    def processed_height(self, box, stream_w):
        """Height in pixels of a stream box in the image the detector processes."""
        h = box[3] - box[1]
        if not self.native_w or not stream_w:
            return h
        h *= self.native_w / stream_w                       # stream -> native pixels
        if not self.tiles and self.input_px:
            h *= self.input_px / self.native_w              # native -> shrunken detector input
        return h

    def miss_probability(self, box, truth):
        if self.miss_model != "pixel_height":
            return self.miss_rate
        stream_w = (truth.get("size") or [0])[0]
        return pixel_height_miss(self.processed_height(box, stream_w), truth.get("miss_factor", 1.0))

    def feed(self, truth, now):
        """Take one ground-truth message (as sent by the world) that arrived at `now`."""
        boxes = []
        for w in truth.get("workers", []):
            box = w.get("box")
            if not box or w.get("visible", 1.0) < self.min_visible:
                continue
            if self.rng.random() < self.miss_probability(box, truth):
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
    footage (V17), not on the twin's renderer. With `tiles`, it runs on full-resolution
    size x size tiles (overlapping by a quarter) instead of one downscaled frame."""

    def __init__(self, model, conf=0.4, nms=0.5, size=640, tiles=False):
        import cv2
        self.cv2, self.conf, self.nms, self.size, self.tiles = cv2, conf, nms, size, tiles
        self.net = cv2.dnn.readNetFromONNX(model)

    def run(self, frame, now=None):
        if not self.tiles:
            return self._run_one(frame)
        s, h, w = self.size, *frame.shape[:2]
        step = max(1, s * 3 // 4)
        boxes = []
        for y in range(0, max(1, h - s // 4), step):
            for x in range(0, max(1, w - s // 4), step):
                boxes += [(x0 + x, y0 + y, x1 + x, y1 + y) for x0, y0, x1, y1 in self._run_one(frame[y:y + s, x:x + s])]
        if not boxes:
            return []
        keep = self.cv2.dnn.NMSBoxes([[b[0], b[1], b[2] - b[0], b[3] - b[1]] for b in boxes], [1.0] * len(boxes), 0.0, self.nms)
        return [boxes[i] for i in keep]

    def _run_one(self, frame):
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
                              cfg.get("oracle_jitter_ms", 20), cfg.get("oracle_miss_rate", 0.02),
                              miss_model=cfg.get("miss_model", "fixed"), native_px=cfg.get("native_px"),
                              input_px=cfg.get("input_px"), tiles=cfg.get("tiles", False))
    if mode == "yolo":
        return YoloDetector(cfg["model"], cfg.get("conf", 0.4), tiles=cfg.get("tiles", False))
    raise ValueError(f"unknown detector mode {mode!r} (oracle or yolo)")
