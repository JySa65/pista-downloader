"""Global pacing of YouTube activity.

- Breaker: after a rate limit (HTTP 429) or bot check, pause ALL YouTube activity (listing, downloads,
  previews, retries) for a cooldown: 2 min, doubling up to 30 min; a success resets it.
- YouTubeGate: one YouTube operation at a time (listing, download and preview never overlap), and none
  while the breaker is open.
"""
import threading
import time
from contextlib import contextmanager

BASE_COOLDOWN = 120
MAX_COOLDOWN = 1800


class CooldownActive(Exception):
    """YouTube activity is paused; str() is the user-facing countdown message."""


class Breaker:
    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self.until = 0.0
        self.next_cooldown = BASE_COOLDOWN
        self._lock = threading.Lock()

    def trip(self) -> None:
        with self._lock:
            if self.is_open():
                return  # already pausing; don't stack waits
            self.until = self.clock() + self.next_cooldown
            self.next_cooldown = min(MAX_COOLDOWN, self.next_cooldown * 2)

    def resume(self) -> None:
        """«Reanudar ahora»."""
        self.until = 0.0

    def record_success(self) -> None:
        self.next_cooldown = BASE_COOLDOWN

    def remaining(self) -> float:
        return max(0.0, self.until - self.clock())

    def is_open(self) -> bool:
        return self.remaining() > 0

    def message(self) -> str:
        left = self.remaining()
        if not left:
            return ""
        m, s = divmod(int(left + 0.999), 60)
        return f"YouTube limitó las peticiones. Reanudando en {m}:{s:02d}…"


class YouTubeGate:
    def __init__(self, breaker: Breaker) -> None:
        self.breaker = breaker
        self._lock = threading.Lock()

    @contextmanager
    def use(self):
        """Hold the single YouTube slot. Raises CooldownActive while the breaker is open."""
        if self.breaker.is_open():
            raise CooldownActive(self.breaker.message())
        with self._lock:
            if self.breaker.is_open():  # opened while we waited for the slot
                raise CooldownActive(self.breaker.message())
            yield


BREAKER = Breaker()
GATE = YouTubeGate(BREAKER)
