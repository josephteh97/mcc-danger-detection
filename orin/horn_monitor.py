"""Twin test tool (not part of the app): logs when sound starts on the horn sink.

parec reads the null sink's monitor; a 4410-byte block whose peak sample exceeds 500 counts
as sound, with 0.5 s of hold-off between reports. Each line: <wall time> SOUND.
"""
import array
import subprocess
import sys
import time

proc = subprocess.Popen(["parec", "-d", "horn.monitor", "--raw", "--format=s16le", "--channels=1",
                         "--rate=44100"], stdout=subprocess.PIPE)
while True:
    block = proc.stdout.read(4410)
    if not block:
        sys.exit(1)
    a = array.array("h", block[: len(block) // 2 * 2])
    if a and max(map(abs, a)) > 500:
        print(time.time(), "SOUND", flush=True)
        time.sleep(0.5)
        proc.stdout.read(44100)          # drop what was captured during the hold-off
