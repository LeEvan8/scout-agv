"""Hide-and-seek state machine: SEARCH -> DETECTED -> TRACKING -> CAUGHT -> SEARCH.

SEARCH    no confirmed person (other than already-caught ones)
DETECTED  a confirmed person is the current target, for less than LOCK_S
TRACKING  the same target has stayed in view for LOCK_S or more
CAUGHT    the teacher pressed "Student caught"; banner for CAUGHT_SHOW_S, then back to SEARCH.
          That track is remembered as caught and ignored (drawn grey) for the rest of the round.

Only "a person is here": track IDs are per-session numbers, never identities.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SEARCH, DETECTED, TRACKING, CAUGHT = "SEARCH", "DETECTED", "TRACKING", "CAUGHT"

LOCK_S = 1.0          # continuous sighting needed to go DETECTED -> TRACKING
LOST_S = 1.5          # keep the target this long after it disappears (short occlusions)
CAUGHT_SHOW_S = 3.0


@dataclass
class Game:
    state: str = SEARCH
    target_id: int | None = None
    target_since: float = 0.0
    last_seen: float = 0.0
    caught_at: float = 0.0
    caught_ids: set = field(default_factory=set)
    caught_count: int = 0
    _now: float = 0.0

    @property
    def target_lost(self) -> bool:
        """True while the target is briefly out of sight but still being waited for."""
        return self.target_id is not None and self.last_seen < self._now

    def update(self, tracks: list, now: float) -> None:
        """tracks: confirmed, visible tracks from the vision tracker (objects with .id and .score)."""
        self._now = now
        if self.state == CAUGHT:
            if now - self.caught_at >= CAUGHT_SHOW_S:
                self.state, self.target_id = SEARCH, None
            else:
                return

        candidates = [t for t in tracks if t.id not in self.caught_ids]
        ids = {t.id for t in candidates}

        if self.target_id in ids:
            self.last_seen = now
            if self.state == DETECTED and now - self.target_since >= LOCK_S:
                self.state = TRACKING
            return

        if self.target_id is not None and now - self.last_seen < LOST_S:
            return                                   # brief occlusion: keep waiting

        if candidates:
            best = max(candidates, key=lambda t: t.score)
            self.target_id, self.target_since, self.last_seen = best.id, now, now
            self.state = DETECTED
        else:
            self.target_id, self.state = None, SEARCH

    @property
    def can_catch(self) -> bool:
        return self.state in (DETECTED, TRACKING) and self.target_id is not None

    def catch(self, now: float) -> bool:
        if not self.can_catch:
            return False
        self.caught_ids.add(self.target_id)
        self.caught_count += 1
        self.state, self.caught_at, self.target_id = CAUGHT, now, None
        return True

    def new_round(self) -> None:
        self.caught_ids.clear()
        self.caught_count = 0
        self.state, self.target_id = SEARCH, None
