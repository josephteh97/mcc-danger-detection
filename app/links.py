"""Links from the Orin to the outside world: serial devices, laser aim angles and the
offline uplink queue. Only the adapters here change when a real device replaces an
emulator; the protocol seen by the rest of the app stays the same.
"""
from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time

log = logging.getLogger("links")


# --------------------------------------------------------------------------- aim geometry

def aim_angles(arm_xy, heading_deg, pivot_h_m, target_xy):
    """Pan (degrees from the arm's forward direction, counter-clockwise positive) and tilt
    (degrees below horizontal) that put the beam on target_xy at ground level."""
    dx, dy = target_xy[0] - arm_xy[0], target_xy[1] - arm_xy[1]
    bearing = math.degrees(math.atan2(dy, dx))
    pan = (bearing - heading_deg + 180.0) % 360.0 - 180.0
    tilt = math.degrees(math.atan2(pivot_h_m, math.hypot(dx, dy)))
    return pan, tilt


def beam_ground_point(arm_xy, heading_deg, pivot_h_m, pan, tilt):
    """Where a beam at (pan, tilt) meets the ground, or None if it points at or above the horizon."""
    if tilt <= 0.0:
        return None
    reach = pivot_h_m / math.tan(math.radians(min(tilt, 90.0)))
    a = math.radians(heading_deg + pan)
    return arm_xy[0] + reach * math.cos(a), arm_xy[1] + reach * math.sin(a)


# --------------------------------------------------------------------------- serial lines

class SerialLine:
    """A newline-delimited text line on a serial device (a pty in the twin, a USB tty on site).

    The device may disappear (cable unplugged) and come back; the line reopens itself at
    most once a second and bumps `generation` so callers can resend state.
    """

    def __init__(self, path, reopen_s=1.0):
        self.path, self.reopen_s = path, reopen_s
        self.fd, self.generation = None, 0
        self._buf, self._next_try = b"", 0.0
        self._open()

    @property
    def connected(self):
        return self.fd is not None

    def _open(self):
        now = time.monotonic()
        if now < self._next_try:
            return
        self._next_try = now + self.reopen_s
        try:
            fd = os.open(self.path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError:
            return
        try:
            import termios
            import tty
            tty.setraw(fd)
            attrs = termios.tcgetattr(fd)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except Exception:      # not a tty (e.g. a FIFO in tests)
            pass
        self.fd, self._buf = fd, b""
        self.generation += 1
        log.info("serial %s connected", self.path)

    def _drop(self, why):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            log.warning("serial %s lost: %s", self.path, why)
        self.fd = None

    def send(self, line):
        if self.fd is None:
            self._open()
            if self.fd is None:
                return False
        try:
            os.write(self.fd, (line.strip() + "\n").encode())
            return True
        except BlockingIOError:
            return False
        except OSError as e:
            self._drop(e)
            return False

    def readlines(self):
        if self.fd is None:
            self._open()
            if self.fd is None:
                return []
        while True:
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                break
            except OSError as e:
                self._drop(e)
                break
            if not chunk:
                self._drop("end of file")
                break
            self._buf += chunk
        *lines, self._buf = self._buf.split(b"\n")
        return [ln.decode(errors="replace").strip() for ln in lines if ln.strip()]

    def close(self):
        self._drop("closed")


# --------------------------------------------------------------------------- relay board

STROBE, FLOODLIGHT, LASER_POWER, SPARE = 1, 2, 3, 4


class LineRelayAdapter:
    """The twin's readable relay protocol: 'R <channel> <0|1>'."""

    def encode(self, channel, on):
        return f"R {channel} {1 if on else 0}"


class HexRelayAdapter:
    """Typical USB relay board frame: A0 <channel> <state> <checksum>, sent as hex text.
    Only this adapter changes on site; check the frame against the board's datasheet."""

    def encode(self, channel, on):
        state = 1 if on else 0
        return bytes([0xA0, channel, state, (0xA0 + channel + state) & 0xFF]).hex()


class Relays:
    def __init__(self, line, adapter=None):
        self.line, self.adapter = line, adapter or LineRelayAdapter()
        self.state, self._gen = {}, line.generation

    def set(self, channel, on):
        on = bool(on)
        if self.state.get(channel) != on:
            self.state[channel] = on
            self.line.send(self.adapter.encode(channel, on))

    def poll(self):
        """Read acknowledgements; resend every channel after the board reconnects."""
        lines = self.line.readlines()
        if self.line.generation != self._gen:
            self._gen = self.line.generation
            for ch, on in self.state.items():
                self.line.send(self.adapter.encode(ch, on))
        return lines


# --------------------------------------------------------------------------- laser arm

class ArmLink:
    """The Orin side of the arm protocol: AIM / LASER / HB / PARK out, POS in."""

    def __init__(self, line, offline_after_s=1.0):
        self.line = line if isinstance(line, SerialLine) else SerialLine(line)
        self.offline_after_s = offline_after_s
        self.pos, self.last_pos_t = None, None
        self.was_online = None

    def send(self, cmd):
        return self.line.send(cmd)

    def point_at(self, pan, tilt, laser=True):
        self.send(f"AIM {pan:.2f} {tilt:.2f}")
        self.send(f"LASER {1 if laser else 0}")
        self.send("HB")

    def park(self):
        self.send("HB")
        self.send("PARK")

    def poll(self, now=None):
        now = time.monotonic() if now is None else now
        for ln in self.line.readlines():
            parts = ln.split()
            if len(parts) == 4 and parts[0] == "POS":
                try:
                    self.pos = (float(parts[1]), float(parts[2]), parts[3] == "1")
                    self.last_pos_t = now
                except ValueError:
                    pass
        online = self.online(now)
        if online != self.was_online:
            (log.info if online else log.error)("arm online" if online else "arm offline")
            self.was_online = online
        return self.pos

    def online(self, now=None):
        now = time.monotonic() if now is None else now
        return self.last_pos_t is not None and now - self.last_pos_t <= self.offline_after_s


# --------------------------------------------------------------------------- uplink queue

class Uplink:
    """Events queue on disk and go out strictly in order, one in flight at a time.

    `publish(payload)` must return a handle with `is_published()`; a row is deleted only
    once its handle reports the broker's acknowledgement. Delivery is at-least-once: every
    payload carries `seq` so the cloud can drop a duplicate after a crash.
    """

    def __init__(self, path, publish, retry_s=60.0):
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS q (seq INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT)")
        self.publish, self.retry_s = publish, retry_s
        self._pending = None          # (seq, handle, sent_at)
        self.sent = 0

    def put(self, event):
        cur = self.db.execute("INSERT INTO q (body) VALUES (?)", (json.dumps(event),))
        return cur.lastrowid

    def __len__(self):
        return self.db.execute("SELECT COUNT(*) FROM q").fetchone()[0]

    def _payload(self, seq, body):
        event = json.loads(body)
        event["seq"] = seq
        return json.dumps(event)

    def flush(self, now=None, max_n=20):
        now = time.monotonic() if now is None else now
        for _ in range(max_n):
            if self._pending is not None:
                seq, handle, sent_at = self._pending
                try:
                    done = handle is not None and handle.is_published()
                except Exception:          # the publish itself failed: send it again
                    done, sent_at = False, -1e9
                if done:
                    self.db.execute("DELETE FROM q WHERE seq = ?", (seq,))
                    self._pending, self.sent = None, self.sent + 1
                    continue
                if now - sent_at < self.retry_s:
                    return
                row = self.db.execute("SELECT seq, body FROM q WHERE seq = ?", (seq,)).fetchone()
                self._pending = None
                if row is None:
                    continue
            else:
                row = self.db.execute("SELECT seq, body FROM q ORDER BY seq LIMIT 1").fetchone()
                if row is None:
                    return
            try:
                handle = self.publish(self._payload(*row))
            except Exception as e:     # broker unreachable: try again later
                log.debug("uplink publish failed: %s", e)
                handle = None
            # a failed publish is retried after 1 s; an unacknowledged one after retry_s
            self._pending = (row[0], handle, now if handle is not None else now - self.retry_s + 1.0)
            if handle is None:
                return


class MqttPublisher:
    """QoS 1 publisher for the cloud broker over the 4G link (paho-mqtt 2.x)."""

    def __init__(self, broker, topic, port=1883, client_id=None):
        import paho.mqtt.client as mqtt
        self.topic = topic
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id or "")
        self.client.reconnect_delay_set(1, 10)
        self.client.connect_async(broker, port, keepalive=10)
        self.client.loop_start()

    def __call__(self, payload):
        if not self.client.is_connected():
            raise ConnectionError("broker not connected")
        return self.client.publish(self.topic, payload, qos=1)

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()
