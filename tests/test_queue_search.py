"""Queue search: which rows show, and «Todas/Ninguna» acting on the shown rows only."""
from pista.core.models import Track
from pista.core.queue import QueueModel, matches


def track(tid: str, title: str, channel: str = "Canal") -> Track:
    return Track(id=tid, title=title, channel=channel, duration=None, url=f"https://youtu.be/{tid}", thumbnail=None)


def test_matches_title_and_channel_case_insensitive():
    t = track("a", "Buenos Días", "Los Fabulosos")
    assert matches(t, "buenos")
    assert matches(t, "FABULOSOS")
    assert not matches(t, "noches")


def test_empty_query_matches_everything():
    assert matches(track("a", "x"), "")
    assert matches(track("a", "x"), "   ")


def test_accents_are_folded_both_ways():
    t = track("a", "Buenos Días", "Canción")
    assert matches(t, "dias")
    assert matches(t, "cancion")
    assert matches(track("b", "Buenos dias"), "Días")


def model() -> QueueModel:
    m = QueueModel()
    m.add_tracks([track("a", "Uno"), track("b", "Dos"), track("c", "Tres", "Uno Records")])
    return m


def test_visible_follows_the_query():
    m = model()
    assert [t.id for t in m.visible()] == ["a", "b", "c"]
    m.query = "uno"
    assert [t.id for t in m.visible()] == ["a", "c"]


def test_select_all_acts_on_visible_rows_only_when_filtered():
    m = model()
    m.query = "dos"
    m.select_all(False)
    assert m.checked == {"a": True, "b": False, "c": True}
    m.query = ""
    m.select_all(False)
    assert m.checked == {"a": False, "b": False, "c": False}
    m.query = "uno"
    m.select_all(True)
    assert m.checked == {"a": True, "b": False, "c": True}


def test_filter_does_not_change_selection_or_downloads():
    m = model()
    m.query = "dos"
    assert [t.id for t in m.selected()] == ["a", "b", "c"]
    assert m.next_pending().id == "a"
