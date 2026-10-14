"""The 37 quick checks under pytest (for the JUnit report). V11 is an expected failure."""
import importlib

import pytest

import _check

for _m in ("smoke", "smoke_links", "smoke_weather", "smoke_catalog", "smoke_trial"):
    importlib.import_module(_m)


@pytest.mark.parametrize("cid,title,fn", _check.CHECKS, ids=[c[0] for c in _check.CHECKS])
def test_quick(cid, title, fn):
    passed, measured, criterion = _check.run_one(cid, title, fn)
    if cid in _check.KNOWN_FAIL:
        if passed:
            pytest.fail(f"{cid} now passes: update the validation matrix (it was a known fail)")
        pytest.xfail(f"{cid} known fail: {measured} ({_check.KNOWN_FAIL[cid]})")
    assert passed, f"{measured} (pass when {criterion})"
