"""Static checks on the stack definition. They need no Docker and guard the fixes to the guide's
snippets (design D18):

- the world pipeline, whose folded `command:` split ffmpeg's options into separate commands
- fixed addresses inside Docker's dynamic range
- an encoder output that browsers cannot decode
- the missing PulseAudio daemon package
"""
import ipaddress
import os
import re
import subprocess

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    with open(os.path.join(ROOT, path)) as f:
        return f.read()


def _code(text):
    """Non-comment lines, with backslash continuations joined into one logical line each."""
    lines = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return [line.strip() for line in re.sub(r"\\\n\s*", " ", lines).splitlines()]


COMPOSE = yaml.safe_load(_read("compose.yaml"))
SERVICES = COMPOSE["services"]


def test_world_runs_its_script():
    """The pipeline lives in world/entrypoint.sh, where YAML folding and Compose's own
    word-splitting cannot touch it."""
    assert "command" not in SERVICES["world"]
    assert 'CMD ["sh", "world/entrypoint.sh"]' in _read("world/Dockerfile")
    for script in ("world/entrypoint.sh", "orin/entrypoint.sh"):
        subprocess.run(["sh", "-n", os.path.join(ROOT, script)], check=True)


def test_world_encoder_is_one_command_with_browser_output():
    """The renderer pipes into one ffmpeg command that holds the encoder and the RTSP output, and
    encodes 4:2:0: libx264 keeps BGR input as 4:4:4 otherwise, which browsers cannot decode."""
    lines = _code(_read("world/entrypoint.sh"))
    i = next(n for n, line in enumerate(lines) if line.startswith("ffmpeg "))
    ffmpeg = lines[i]
    assert lines[i - 1].startswith("python3 world/world.py") and lines[i - 1].endswith("|")
    assert "-c:v libx264" in ffmpeg and "-f rtsp" in ffmpeg
    assert "-pix_fmt yuv420p" in ffmpeg[ffmpeg.index("-c:v libx264"):]


def test_fixed_addresses_outside_dynamic_range():
    """A container without a fixed address must never be able to take one that is fixed."""
    nets = {}
    for name, net in COMPOSE["networks"].items():
        for cfg in ((net or {}).get("ipam") or {}).get("config", []):
            nets[name] = (ipaddress.ip_network(cfg["subnet"]),
                          ipaddress.ip_network(cfg["ip_range"]) if "ip_range" in cfg else None)
    fixed = [(svc, net, ipaddress.ip_address(opts["ipv4_address"]))
             for svc, s in SERVICES.items() if isinstance(s.get("networks"), dict)
             for net, opts in s["networks"].items() if opts and "ipv4_address" in opts]
    assert len(fixed) >= 6
    for svc, net, addr in fixed:
        subnet, dynamic = nets[net]
        assert addr in subnet, f"{svc}: {addr} is outside {net} {subnet}"
        assert dynamic is not None, f"{net} has fixed addresses but no ip_range"
        assert addr not in dynamic, f"{svc}: {addr} is inside {net}'s dynamic range {dynamic}"


def test_orin_image_has_pulseaudio_daemon():
    """'pulseaudio-utils' has only the clients; without the daemon the horn sink never exists."""
    assert re.search(r"\bpulseaudio\b(?!-)", " ".join(_code(_read("orin/Dockerfile"))))
    assert any("module-null-sink sink_name=horn" in line for line in _code(_read("orin/entrypoint.sh")))
