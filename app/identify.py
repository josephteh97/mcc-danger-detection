"""Helmet tag and uniform logo identification, run only on people who trigger an alarm.

Legacy code: version 11 is detection-only and runs with `identify.enabled: false`, so the app
does not import this module. It is kept so identification can come back with a new provider
and configuration, without touching the alarm state machine or the actuation.

Phase 1 stub: the twin's product checks (V28) show no catalogue camera reaches the 250 px/m
needed to read a helmet tag from the pole, so this returns 'unknown' until a longer lens,
PTZ zoom-on-alarm or a second close camera is chosen.
"""
from __future__ import annotations

PDPA_FIELDS = ("consent_records", "retention_days")


def identify(frame, box):
    return {"tag": None, "logo": None, "result": "unknown",
            "reason": "pole camera cannot resolve helmet tags (V28)"}


class IdentityProvider:
    """One way of naming the person who triggered an alarm. A provider that handles faces
    (`uses_faces = True`) must store any face templates encrypted."""
    kind = "base"
    uses_faces = False

    def __init__(self, cfg=None):
        self.cfg = cfg or {}

    def identify(self, frame, box, track_id):
        """-> {"result", "name", "subcon", "confidence", "reason"}"""
        raise NotImplementedError


class StubProvider(IdentityProvider):
    """The phase-1 stub as a provider: always 'unknown', with its reason."""
    kind = "stub"

    def identify(self, frame, box, track_id):
        r = identify(frame, box)
        return {"result": r["result"], "name": None, "subcon": None, "confidence": 0.0, "reason": r["reason"]}


PROVIDERS = {StubProvider.kind: StubProvider}


class PdpaError(RuntimeError):
    pass


def check_pdpa(provider_cls, cfg):
    """A face-recognition provider may only start with consent records and a retention period declared."""
    if not provider_cls.uses_faces:
        return
    pdpa = cfg.get("pdpa") or {}
    missing = [f"pdpa.{f}" for f in PDPA_FIELDS if pdpa.get(f) in (None, "")]
    if missing:
        raise PdpaError(f"identify provider '{provider_cls.kind}' uses face recognition: "
                        f"the config must declare {', '.join(missing)} (PDPA)")


def make_provider(cfg):
    """The provider named by `identify.provider` (default: the stub), after the PDPA gate."""
    name = cfg.get("provider", StubProvider.kind)
    if name not in PROVIDERS:
        raise ValueError(f"unknown identify provider {name!r} (available: {', '.join(PROVIDERS)})")
    check_pdpa(PROVIDERS[name], cfg)
    return PROVIDERS[name](cfg)
