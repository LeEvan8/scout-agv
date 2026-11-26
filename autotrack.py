"""Auto-tracking (Phase 2 step 4): turn IN PLACE to keep the target centred. Never drives forward.

Steers only when ALL of these hold, otherwise returns 0 with the reason:
  - the teacher is holding T (and no manual drive key: the app checks that)
  - the robot is armed
  - there is a target and it was seen in THIS frame
  - the video is fresh (frame age <= MAX_AGE_S)
  - it has not been turning non-stop for longer than MAX_TURN_S (wrong camera direction, camera not on
    the robot, ...). Then it stays blocked until T is released.
Speed is level-1 at most (MAX_PCT). The firmware's 30 % cap and 250 ms deadman still apply on top.
"""
from __future__ import annotations

from dataclasses import dataclass

CENTER_BAND = 0.15     # target within +/-15 % of the image centre -> stand still
MIN_PCT = 3.0          # slowest turn (dead-zone compensated firmware: 3 % = slow crawl)
MAX_PCT = 10.0         # = teleop level 1
MAX_AGE_S = 0.4        # never steer on video older than this
MAX_TURN_S = 4.0       # non-stop turning longer than this -> block until T is released


@dataclass
class AutoTracker:
    turning_since: float | None = None
    blocked: bool = False
    turn: float = 0.0
    reason: str = "hold T"

    def update(self, holding: bool, armed: bool, result, target_id: int | None, now: float) -> float:
        """Return turn percent: + = turn right (left wheel forward, right wheel back), - = turn left."""
        self.turn = 0.0
        if not holding:
            self.blocked, self.turning_since, self.reason = False, None, "hold T"
            return 0.0
        if self.blocked:
            self.reason = f"STOPPED: turned > {MAX_TURN_S:.0f} s - check camera, release T"
            return 0.0
        if not armed:
            return self._idle("robot not armed (R)")
        if result is None or result.age > MAX_AGE_S:
            return self._idle("video too old")
        target = next((t for t in result.tracks if t.id == target_id), None)
        if target is None or target.misses > 0:
            return self._idle("no target in this frame")

        width = result.image.shape[1]
        cx = (target.head[0] + target.head[2]) / 2
        error = (cx - width / 2) / (width / 2)              # -1 left edge .. +1 right edge
        if abs(error) <= CENTER_BAND:
            return self._idle("target centred")

        frac = (abs(error) - CENTER_BAND) / (1 - CENTER_BAND)
        self.turn = (MIN_PCT + frac * (MAX_PCT - MIN_PCT)) * (1 if error > 0 else -1)
        if self.turning_since is None:
            self.turning_since = now
        elif now - self.turning_since > MAX_TURN_S:
            self.blocked, self.turn = True, 0.0
            self.reason = f"STOPPED: turned > {MAX_TURN_S:.0f} s - check camera, release T"
            return 0.0
        self.reason = f"turning {'right' if self.turn > 0 else 'left'} {abs(self.turn):.0f}%"
        return self.turn

    def _idle(self, why: str) -> float:
        self.turning_since, self.reason = None, why
        return 0.0
