"""The v11 laser controller's Ethernet links: the relay and arm emulators on TCP, the app's
TcpLine, and reconnection after the controller restarts (no Docker needed)."""
import os
import socket
import time

import pytest
from smoke_links import Emulator, drive

from app.links import ArmLink, Relays, SerialLine, TcpLine, make_line


def free_addr():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"127.0.0.1:{s.getsockname()[1]}"


def wait_lines(line, want, timeout=3.0):
    got, end = [], time.monotonic() + timeout
    while time.monotonic() < end:
        got += line.readlines()
        if want in got:
            return got
        time.sleep(0.02)
    return got


def test_make_line_picks_transport():
    assert isinstance(make_line("127.0.0.1:1"), TcpLine)


def test_relay_over_ethernet_and_reconnect():
    addr = free_addr()
    line = None
    try:
        with Emulator("relay_emulator.py", tcp=addr):
            line = TcpLine(addr)                       # the controller is up before the app connects
            relays = Relays(line)
            relays.set(1, True)
            assert "OK 1 1" in wait_lines(line, "OK 1 1")
            assert line.send("R 9 1") and "ERR" in wait_lines(line, "ERR")
            gen = line.generation
        line.readlines()                               # notices the far end has gone
        with Emulator("relay_emulator.py", tcp=addr):
            t0, acks = time.monotonic(), []
            while time.monotonic() - t0 < 2.0 and "OK 1 1" not in acks:
                acks += relays.poll()                  # resends channel state after reconnecting
                time.sleep(0.02)
            assert line.generation > gen and "OK 1 1" in acks, f"no reconnect within 2 s ({acks})"
    finally:
        if line:
            line.close()


def test_arm_over_ethernet():
    addr = free_addr()
    with Emulator("arm_emulator.py", tcp=addr):
        arm = ArmLink(addr)
        try:
            assert drive(arm, 3.0, ("AIM 10 20", "LASER 1", "HB")), "no POS report over TCP"
        finally:
            arm.line.close()


def _pty_pair():
    master, slave = os.openpty()
    line = SerialLine(os.ttyname(slave))
    os.close(slave)
    os.set_blocking(master, False)

    def read():
        try:
            return os.read(master, 65536)
        except BlockingIOError:
            return b""
    return line, read, lambda: os.close(master)


def _tcp_pair():
    srv = socket.create_server(("127.0.0.1", 0))
    line = TcpLine(f"127.0.0.1:{srv.getsockname()[1]}")
    peer, _ = srv.accept()
    srv.close()
    peer.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    end = time.monotonic() + 2.0
    while not line.connected and time.monotonic() < end:
        line.readlines()
        time.sleep(0.01)
    line.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    peer.setblocking(False)

    def read():
        try:
            return peer.recv(65536)
        except BlockingIOError:
            return b""
    return line, read, peer.close


@pytest.mark.parametrize("pair", [_pty_pair, _tcp_pair], ids=["serial", "tcp"])
def test_full_buffer_keeps_lines_whole(pair):
    """Commands sent while the far end isn't reading wait whole and go out in order: none is split
    or glued onto the next, and a command the link refuses is refused whole."""
    line, read, close = pair()
    try:
        sent, queued = [], False
        for i in range(20000):
            cmd = f"AIM {i} {'0' * 40}"
            if not line.send(cmd):
                break
            sent.append(cmd)
            queued |= bool(line._out)
        assert queued, "the device took everything; the test never filled its buffer"
        got, buf, end = [], b"", time.monotonic() + 10.0
        while len(got) < len(sent) and time.monotonic() < end:
            line.readlines()                           # sends what is waiting
            buf += read()
            *lines, buf = buf.split(b"\n")
            got += [ln.decode() for ln in lines]
        assert got == sent
    finally:
        line.close()
        close()
