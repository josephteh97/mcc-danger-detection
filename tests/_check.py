"""Shared reporter for the quick checks.

Each check prints one line: ID, PASS or FAIL, what was measured and the pass criterion.
A script exits 0 when every check matches its expected outcome: every check is expected
to pass except V11 (the battery runs flat over three heavily overcast days; second finding).
It exits 1 on any regression, or if V11 starts passing so the matrix needs updating.
"""
from __future__ import annotations

import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

KNOWN_FAIL = {"V11": "second finding: fit a second battery or 1,000 W of panels, or use site power"}
CHECKS = []      # (id, title, function) registered by the @check decorator


def check(cid, title):
    def deco(fn):
        CHECKS.append((cid, title, fn))
        return fn
    return deco


def run_one(cid, title, fn):
    """Returns (passed, measured, criterion). An exception counts as a fail."""
    try:
        passed, measured, criterion = fn()
        return bool(passed), str(measured), str(criterion)
    except Exception as e:          # report and keep going
        return False, f"error: {e.__class__.__name__}: {e}", "runs without error\n" + traceback.format_exc()


def main(script):
    import logging
    logging.basicConfig(level=logging.ERROR)
    logging.getLogger("links").setLevel(logging.CRITICAL)      # "arm offline" is expected noise here
    t0 = time.monotonic()
    bad, n_pass, n_known = [], 0, 0
    for cid, title, fn in CHECKS:
        passed, measured, criterion = run_one(cid, title, fn)
        expected_fail = cid in KNOWN_FAIL
        status = "PASS" if passed else ("FAIL (known)" if expected_fail else "FAIL")
        print(f"{cid}  {status:12s} {title}: {measured}  [pass when {criterion.splitlines()[0]}]", flush=True)
        if not passed and not expected_fail:
            print("      " + "\n      ".join(criterion.splitlines()[1:]) if "\n" in criterion else "", end="")
        if passed:
            n_pass += 1
            if expected_fail:
                bad.append(f"{cid} now passes: update the validation matrix (it was a known fail)")
        elif expected_fail:
            n_known += 1
        else:
            bad.append(f"{cid} failed")
    print(f"{script}: {len(CHECKS)} checks, {n_pass} pass, {n_known} known fail"
          f"{', ' + str(len(bad)) + ' unexpected' if bad else ''} ({time.monotonic() - t0:.1f} s)")
    for b in bad:
        print(f"  UNEXPECTED: {b}")
    sys.exit(1 if bad else 0)
