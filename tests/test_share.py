"""share.sh against fake devtunnel and curl (tests/fakes/): no network, no real tunnel. Each test
runs a copy of the script in its own folder, so the real .share/ state is never touched.

Covers the remote-access scenarios added since phase 1: options refused while sharing, one
start or stop at a time, and the clean-up after a failed start.
"""
import fcntl
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKES = os.path.join(ROOT, "tests", "fakes")

pytestmark = pytest.mark.skipif(not shutil.which("bash") or not shutil.which("flock"), reason="needs bash and flock")


@pytest.fixture
def share(tmp_path):
    shutil.copy(os.path.join(ROOT, "share.sh"), tmp_path / "share.sh")
    log = tmp_path / "devtunnel.log"
    env = {**os.environ, "PATH": f"{FAKES}:{os.environ['PATH']}", "DEVTUNNEL": os.path.join(FAKES, "devtunnel"),
           "FAKE_LOG": str(log)}

    def run(*args, **extra):
        return subprocess.run(["bash", str(tmp_path / "share.sh"), *args], capture_output=True, text=True,
                              env={**env, **extra}, timeout=120)

    run.dir, run.log = tmp_path, log
    yield run
    run("stop")
    subprocess.run(["pkill", "-f", f"{FAKES}/devtunnel host"], capture_output=True)


def calls(run, verb):
    return [line for line in (run.log.read_text().splitlines() if run.log.exists() else []) if line.startswith(verb + " ")]


def test_start_status_stop(share):
    r = share("start")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "https://abc-8080.asse.devtunnels.ms" in r.stdout
    assert share("status").returncode == 0
    r = share("stop")
    assert r.returncode == 0 and not (share.dir / ".share").exists()
    assert len(calls(share, "delete")) == 1


def test_options_refused_while_sharing(share):
    assert share("start").returncode == 0
    for opts in (["--expires", "2d"], ["--org", "my-org"]):
        r = share("start", *opts)
        assert r.returncode != 0
        assert "would not apply" in r.stderr and "./share.sh stop" in r.stderr, r.stderr
    assert len(calls(share, "create")) == 1, "the running tunnel must be left unchanged"
    assert (share.dir / ".share" / "tunnel").exists()


def test_one_start_or_stop_at_a_time(share):
    with open(share.dir / "share.sh") as held:              # another start holds the lock
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for cmd in ("start", "stop"):
            r = share(cmd)
            assert r.returncode != 0 and "another ./share.sh start or stop is running" in r.stderr, r.stderr
    assert not calls(share, "create") and not (share.dir / ".share").exists()


def test_failed_start_cleans_up_rejected_rule(share):
    """The access rule is rejected after the tunnel was created: the tunnel is deleted again."""
    r = share("start", "--repo", "owner/repo")
    assert r.returncode != 0
    created = [c.split()[1] for c in calls(share, "create")]
    deleted = [c.split()[1] for c in calls(share, "delete")]
    assert created and deleted and deleted[0].startswith(created[0]), (created, deleted)
    assert not (share.dir / ".share").exists()


def test_failed_start_cleans_up_open_tunnel(share):
    """The anonymous check gets through: the host is stopped and the tunnel deleted."""
    r = share("start", FAKE_OPEN="1")
    assert r.returncode != 0 and "OPEN" in r.stdout + r.stderr
    assert calls(share, "delete") and not (share.dir / ".share").exists()
    assert subprocess.run(["pgrep", "-f", f"{FAKES}/devtunnel host"], capture_output=True).returncode != 0
