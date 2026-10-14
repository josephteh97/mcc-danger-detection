"""Simple IoU tracker: one ID per person across frames, kept through short detection gaps,
so each dwell timer belongs to one person."""
from __future__ import annotations


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _centre_close(a, b):
    """Fallback match for small or fast boxes: centres within half a box height."""
    h = max(a[3] - a[1], b[3] - b[1], 1.0)
    return abs((a[0] + a[2]) - (b[0] + b[2])) / 2 < 0.5 * h and abs((a[1] + a[3]) - (b[1] + b[3])) / 2 < 0.5 * h


class IoUTracker:
    def __init__(self, iou_threshold=0.3, max_age_s=2.0):
        self.iou_threshold, self.max_age_s = iou_threshold, max_age_s
        self.tracks, self._next = {}, 1          # id -> (box, last_seen)

    def update(self, boxes, now):
        """boxes: [(x0, y0, x1, y1)]. Returns {track_id: box} for the people seen this frame."""
        for tid in [t for t, (_, seen) in self.tracks.items() if now - seen > self.max_age_s]:
            del self.tracks[tid]
        pairs = sorted(((iou(tb, b), tid, j) for tid, (tb, _) in self.tracks.items()
                        for j, b in enumerate(boxes)), reverse=True)
        used_t, used_b, out = set(), set(), {}
        for score, tid, j in pairs:
            if tid in used_t or j in used_b:
                continue
            if score < self.iou_threshold and not _centre_close(self.tracks[tid][0], boxes[j]):
                continue
            used_t.add(tid)
            used_b.add(j)
            out[tid] = boxes[j]
        for j, b in enumerate(boxes):
            if j not in used_b:
                out[self._next] = b
                self._next += 1
        for tid, b in out.items():
            self.tracks[tid] = (b, now)
        return out
