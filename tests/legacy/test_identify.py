"""Legacy identification: the identify step kept as switched-off code (run with pytest --legacy)."""
import pytest

from app_harness import alarm_event

from app.identify import PROVIDERS, IdentityProvider, PdpaError, StubProvider, check_pdpa, make_provider

RESULT_KEYS = {"result", "name", "subcon", "confidence", "reason"}


def test_stub_provider_returns_unknown_with_phase1_reason():
    r = make_provider({}).identify(None, (0, 0, 10, 10), 1)
    assert set(r) == RESULT_KEYS
    assert r["result"] == "unknown" and "V28" in r["reason"]


def test_phase1_alarm_still_runs_identify():
    event, loaded = alarm_event("app/config.yaml")
    assert loaded and event["identity"] == "unknown"


def test_v11_re_enabled_runs_identify():
    event, loaded = alarm_event("app/config.v11.yaml", {"enabled": True})
    assert loaded and event["identity"] == "unknown"
    assert event["kind"] == "alarm"


class FaceProvider(IdentityProvider):
    kind, uses_faces = "face_test", True

    def identify(self, frame, box, track_id):
        return {"result": "unknown", "name": None, "subcon": None, "confidence": 0.0, "reason": "test"}


def test_pdpa_gate_names_missing_fields():
    with pytest.raises(PdpaError) as e:
        check_pdpa(FaceProvider, {"pdpa": {"retention_days": 30}})
    assert str(e.value).endswith("must declare pdpa.consent_records (PDPA)")


def test_pdpa_gate_stops_start_up():
    PROVIDERS[FaceProvider.kind] = FaceProvider
    try:
        with pytest.raises(PdpaError, match="pdpa.consent_records, pdpa.retention_days"):
            make_provider({"provider": "face_test"})
        assert make_provider({"provider": "face_test",
                              "pdpa": {"consent_records": "/data/consent.db", "retention_days": 30}})
    finally:
        del PROVIDERS[FaceProvider.kind]


def test_stub_needs_no_pdpa():
    check_pdpa(StubProvider, {})


def test_ptz_re_added_fits_the_poe_budget():
    """Identification on, PTZ on a spare port: the PoE check includes its class reservation."""
    import catalog
    from devices.poe_model import check as poe_check
    site = catalog.load_site(profile="v11")
    extra = [{"port": 6, "category": "camera", "product": "ptz_4mp_25x_hik_ds2de4425iwde"}]
    off = poe_check(site, include_legacy=False, extra=extra)
    on = poe_check(site, include_legacy=True, extra=extra)
    assert on["reserved_w"] == off["reserved_w"] + 30.0 and on["ok"]
