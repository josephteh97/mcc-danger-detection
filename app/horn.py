"""Horn speaker: caution chime, warning tone and alarm siren on an audio sink.

Tones are generated once as WAV files and played with paplay on the configured PulseAudio
sink ('horn' in the twin, the USB audio card on the pole). The warning and siren repeat
until stopped. Without paplay (e.g. on a bare host) the horn only logs what it would play.
"""
from __future__ import annotations

import logging
import math
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import wave

log = logging.getLogger("horn")
RATE = 44100


def _tone(segments, amp=0.8):
    """segments: [(freq_hz_start, freq_hz_end, seconds)], freq 0 = silence."""
    samples, phase = [], 0.0
    for f0, f1, dur in segments:
        n = int(RATE * dur)
        for i in range(n):
            f = f0 + (f1 - f0) * i / max(1, n)
            if f <= 0:
                samples.append(0)
                continue
            phase += 2 * math.pi * f / RATE
            samples.append(int(32767 * amp * math.sin(phase)))
    return samples


TONES = {
    "chime": [(880, 880, 0.18), (660, 660, 0.25)],
    "warning": [(1000, 1000, 0.5), (0, 0, 0.5)],
    "siren": [(600, 1200, 0.6), (1200, 600, 0.6)],
}


class Horn:
    def __init__(self, sink="horn"):
        self.sink = sink
        self.player = shutil.which("paplay")
        self.dir = tempfile.mkdtemp(prefix="horn-")
        self.files = {}
        for name, segs in TONES.items():
            path = os.path.join(self.dir, f"{name}.wav")
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                pcm = _tone(segs)
                w.writeframes(struct.pack(f"<{len(pcm)}h", *pcm))
            self.files[name] = path
        self.current, self._proc, self._lock = None, None, threading.Lock()
        self._loop_name, self._stop = None, threading.Event()
        if not self.player:
            log.warning("paplay not found: horn sounds are logged only")

    def _play_once(self, name):
        if not self.player:
            log.info("horn: %s", name)
            time.sleep(0.5)
            return
        with self._lock:
            self._proc = subprocess.Popen([self.player, f"--device={self.sink}", self.files[name]],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc = self._proc
        proc.wait()

    def chime(self):
        if self._loop_name is None:
            threading.Thread(target=self._play_once, args=("chime",), daemon=True).start()

    def play(self, name):
        """Repeat `name` ('warning' or 'siren') until stop() or another play()."""
        if self._loop_name == name:
            return
        self.stop()
        self._loop_name, self._stop = name, threading.Event()
        stop = self._stop

        def loop():
            while not stop.is_set():
                self._play_once(name)
        threading.Thread(target=loop, daemon=True).start()
        log.info("horn: %s on", name)

    def stop(self):
        if self._loop_name is None:
            return
        self._stop.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
        log.info("horn: %s off", self._loop_name)
        self._loop_name = None

    @property
    def on(self):
        return self._loop_name
