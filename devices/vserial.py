"""A virtual serial port: a pty whose device end is symlinked at a fixed path.

socat (or a test) opens the link path as if it were /dev/ttyUSB0; the emulator reads and
writes the pty master. The emulator keeps its own handle on the device end so the master
never sees EIO while no one is connected.
"""
import os
import time
import tty


class VirtualSerial:
    def __init__(self, link):
        self.master, self._slave = os.openpty()
        tty.setraw(self._slave)                # no echo, no newline translation
        os.set_blocking(self.master, False)
        self.link = link
        if os.path.dirname(link):
            os.makedirs(os.path.dirname(link), exist_ok=True)
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink(os.ttyname(self._slave), link)
        self._buf = b""

    def readlines(self):
        while True:
            try:
                chunk = os.read(self.master, 4096)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:                    # nobody on the far end
                break
            if not chunk:
                break
            self._buf += chunk
        *lines, self._buf = self._buf.replace(b"\r", b"\n").split(b"\n")
        return [ln.decode(errors="replace").strip() for ln in lines if ln.strip()]

    def write_line(self, line):
        try:
            os.write(self.master, (line + "\n").encode())
            return True
        except (BlockingIOError, OSError):    # no reader and the buffer is full: drop it
            return False

    def fileno(self):
        return self.master

    def close(self):
        for fd in (self.master, self._slave):
            try:
                os.close(fd)
            except OSError:
                pass
        if os.path.lexists(self.link):
            os.unlink(self.link)


class TcpPort:
    """The same interface as VirtualSerial, on a TCP listening port: the v11 laser controller's
    Ethernet link. One client at a time; a new connection replaces the old one."""

    def __init__(self, addr):
        import socket
        host, _, port = addr.rpartition(":")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host or "0.0.0.0", int(port)))
        self.sock.listen(4)
        self.sock.setblocking(False)
        self.addr, self.client, self._buf = f"{host or '0.0.0.0'}:{self.sock.getsockname()[1]}", None, b""

    def _accept(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except (BlockingIOError, InterruptedError):
                return
            conn.setblocking(False)
            self._drop()
            self.client, self._buf = conn, b""

    def _drop(self):
        if self.client is not None:
            try:
                self.client.close()
            except OSError:
                pass
        self.client = None

    def readlines(self):
        self._accept()
        while self.client is not None:
            try:
                chunk = self.client.recv(4096)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                self._drop()
                break
            if not chunk:                      # the app closed the link
                self._drop()
                break
            self._buf += chunk
        *lines, self._buf = self._buf.replace(b"\r", b"\n").split(b"\n")
        return [ln.decode(errors="replace").strip() for ln in lines if ln.strip()]

    def write_line(self, line):
        if self.client is None:
            return False
        try:
            self.client.sendall((line + "\n").encode())
            return True
        except OSError:
            self._drop()
            return False

    def fileno(self):
        return (self.client or self.sock).fileno()

    def close(self):
        self._drop()
        self.sock.close()


def open_port(link=None, tcp=None):
    """A VirtualSerial at `link` (phase 1, behind socat) or a TcpPort on `tcp` (v11)."""
    return TcpPort(tcp) if tcp else VirtualSerial(link)


class JsonlState:
    """Append-only JSONL state log, written on change and at least every `every_s`."""

    def __init__(self, path, every_s=1.0):
        self.path, self.every_s = path, every_s
        self._last, self._last_t = None, 0.0
        if path and os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)

    def write(self, record, key):
        if not self.path:
            return
        now = time.monotonic()
        if key == self._last and now - self._last_t < self.every_s:
            return
        self._last, self._last_t = key, now
        import json
        try:
            if os.path.getsize(self.path) > 20_000_000:    # keep the log bounded
                os.replace(self.path, self.path + ".1")
        except OSError:
            pass
        with open(self.path, "a") as f:
            f.write(json.dumps(record) + "\n")
