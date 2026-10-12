"""The app-level session: a reloaded page reattaches to the running batch instead of starting empty."""
from types import SimpleNamespace

from pista.core.models import Track
from pista.ui.session import Session


class View:
    """Stands in for a page's Queue view."""

    def __init__(self) -> None:
        self.changed, self.painted = 0, []

    def _changed(self) -> None:
        self.changed += 1

    def _state_changed(self, track_id: str) -> None:
        self.painted.append(track_id)


def page(**callbacks):
    return SimpleNamespace(queue=View(), **callbacks)


def track(i: int) -> Track:
    return Track(f"vid{i:08d}", f"Song {i}", "Ch", 60, f"https://www.youtube.com/watch?v=vid{i:08d}", None)


def test_queue_updates_go_to_the_last_attached_page():
    s = Session()
    first, second = page(), page()
    s.attach(first)
    s.queue.add_tracks([track(1)])
    s.attach(second)  # the window reloaded
    s.queue.set_state("vid00000001", "running", 40.0)
    assert first.queue.painted == [] and second.queue.painted == ["vid00000001"]
    assert s.queue.state["vid00000001"] == ("running", 40.0)  # the data survived the reload


def test_detaching_the_current_page_falls_back_to_an_older_open_one():
    s = Session()
    first, second = page(), page()
    s.attach(first)
    s.attach(second)
    s.detach(second)
    assert s.page is first and s.queue.view is first.queue
    s.detach(first)
    s.detach(first)  # deleting twice is harmless
    assert s.page is None and s.queue.view is None


def test_detaching_an_old_page_keeps_the_current_one():
    s = Session()
    first, second = page(), page()
    s.attach(first)
    s.attach(second)
    s.detach(first)  # the old client is deleted after the reconnect timeout
    assert s.page is second and s.queue.view is second.queue


def test_to_page_calls_the_current_page_or_nothing():
    s = Session()
    assert s.to_page("status", "x") is None  # no page open: skipped, no crash
    s.queue.add_tracks([track(1)])  # repaints without a view are skipped too
    got = []
    s.attach(page(status=got.append))
    s.to_page("status", "Descargando 1 de 3")
    assert got == ["Descargando 1 de 3"]


def test_only_one_batch_at_a_time_across_pages():
    s = Session()
    assert s.begin() is True
    assert s.begin() is False  # a second page must append to the batch, not start another
    s.busy = False
    assert s.begin() is True
