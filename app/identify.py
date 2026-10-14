"""Helmet tag and uniform logo identification, run only on people who trigger a warning.

Phase 1 stub: the twin's product checks (V28) show no catalogue camera reaches the 250 px/m
needed to read a helmet tag from the pole, so this returns 'unknown' until a longer lens,
PTZ zoom-on-alarm or a second close camera is chosen.
"""


def identify(frame, box):
    return {"tag": None, "logo": None, "result": "unknown",
            "reason": "pole camera cannot resolve helmet tags (V28)"}
