"""PoE watchdog on the v11 switch: ping the AI box every 10 s and power-cycle its port (4)
after 3 missed pings in a row.

`Watchdog` is the pure model (U25 checks it). The twin's live watchdog runs it from the
dashboard, which holds the Docker socket and so can "power-cycle the port" (kill and start the
orin container); see dashboard/server.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Watchdog:
    interval_s: float = 10.0
    misses: int = 3
    holdoff_s: float = 60.0           # after a power cycle, give the box time to boot
    _missed: int = 0
    _next_t: float = None
    _quiet_until: float = 0.0
    cycles: list = field(default_factory=list)

    def due(self, t):
        return self._next_t is None or t >= self._next_t

    def step(self, t, alive):
        """Record one ping at time t. Returns True when the port should be power-cycled now."""
        self._next_t = t + self.interval_s
        if t < self._quiet_until:
            return False
        self._missed = 0 if alive else self._missed + 1
        if self._missed >= self.misses:
            self._missed = 0
            self._quiet_until = t + self.holdoff_s
            self.cycles.append(t)
            return True
        return False


def simulate_hang(hang_t=0.0, boot_s=25.0, monitoring_s=10.0, phase=0.0, until=200.0, dog=None):
    """The box hangs at hang_t; after a power cycle it boots in boot_s and reaches Monitoring
    monitoring_s later. Pings start at `phase`. -> (power cycle t, back in Monitoring t) after the hang."""
    dog = dog or Watchdog()
    t, cycle_t = phase, None
    while t <= until:
        alive = t < hang_t or (cycle_t is not None and t >= cycle_t + boot_s)
        if dog.step(t, alive) and cycle_t is None:
            cycle_t = t
        t += dog.interval_s
    if cycle_t is None:
        return None, None
    return cycle_t - hang_t, cycle_t + boot_s + monitoring_s - hang_t
