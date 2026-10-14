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
