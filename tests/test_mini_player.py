"""Now-playing summary shared by the Reproductor panel and the mini player on the Descargar tab."""
from pathlib import Path

from pista.core.library import Entry
from pista.ui.player import Player, now_playing, play_icon


def entry(title: str = "Canción", artist: str = "Artista") -> Entry:
    return Entry(path=Path("/m/a.mp3"), fmt="MP3", title=title, artist=artist, duration=180.0)


def test_nothing_loaded_is_none():
    assert now_playing(None) is None


def test_title_and_artist():
    assert now_playing(entry()) == ("Canción", "Artista")


def test_unknown_artist_is_blank():
    assert now_playing(entry(artist="—")) == ("Canción", "")


def test_play_icon_matches_transport():
    assert play_icon(True) == "❚❚"
    assert play_icon(False) == "▶"


def test_changed_notifies_every_listener():
    p = Player.__new__(Player)  # no UI: only the listener list
    p.listeners = []
    calls = []
    p.listeners += [lambda: calls.append(1), lambda: calls.append(2)]
    p.changed()
    assert calls == [1, 2]
