"""Global YouTube circuit breaker: after a 429 / bot check, pause ALL YouTube activity for a cooldown."""
import threading
import time

import pytest

from pista.core.breaker import BASE_COOLDOWN, MAX_COOLDOWN, Breaker, CooldownActive, YouTubeGate


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_cooldown_starts_at_2_min_and_doubles_up_to_30():
    c = Clock()
    b = Breaker(clock=c)
    assert (BASE_COOLDOWN, MAX_COOLDOWN) == (120, 1800) and not b.is_open()
    b.trip()
    assert b.is_open() and b.remaining() == 120
    c.t += 120
    assert not b.is_open()
    b.trip()
    assert b.remaining() == 240
    for _ in range(10):
        c.t += b.remaining()
        b.trip()
    assert b.remaining() == 1800


def test_success_resets_and_manual_resume():
    c = Clock()
    b = Breaker(clock=c)
    b.trip(); c.t += 120; b.trip()
    assert b.remaining() == 240
    b.resume()
    assert not b.is_open()
    b.record_success()
    b.trip()
    assert b.remaining() == 120  # back to the base after a success


def test_trip_while_open_does_not_extend_the_wait():
    c = Clock()
    b = Breaker(clock=c)
    b.trip(); c.t += 30; b.trip()
    assert b.remaining() == 90


def test_countdown_text():
    c = Clock()
    b = Breaker(clock=c)
    b.trip(); c.t += 8
    assert b.message() == "YouTube limitó las peticiones. Reanudando en 1:52…"
    b.resume()
    assert b.message() == ""


def test_gate_serializes_youtube_activity():
    gate = YouTubeGate(Breaker())
    active, overlap = [0], []

    def work():
        with gate.use():
            active[0] += 1
            overlap.append(active[0])
            time.sleep(0.02)
            active[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max(overlap) == 1  # never two YouTube operations at once


def test_gate_refuses_while_cooling_down():
    c = Clock()
    gate = YouTubeGate(Breaker(clock=c))
    gate.breaker.trip()
    with pytest.raises(CooldownActive):
        with gate.use():
            pass
    c.t += 120
    with gate.use():
        pass
