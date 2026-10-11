"""Loading links into the queue: dialog choice, failures and messages (offline, fake list_tracks)."""
import asyncio

from yt_dlp.utils import DownloadError

from pista.core.loading import load_links, load_message
from pista.core.models import Track

MIX = "https://www.youtube.com/watch?v=AAAAAAAAAAA&list=RDTESTMIX0123456789&start_radio=1"
VIDEO = "https://www.youtube.com/watch?v=BBBBBBBBBBB"
PLAYLIST = "https://www.youtube.com/playlist?list=PLabc123"
BOT = "ERROR: [youtube] AAAAAAAAAAA: Sign in to confirm you’re not a bot. Use --cookies-from-browser"


def t(vid):
    return Track(vid, f"T {vid}", "C", 60, f"https://www.youtube.com/watch?v={vid}", None)


class Fake:
    def __init__(self, fail=None, empty=()):
        self.calls, self.fail, self.empty = [], fail or {}, set(empty)

    def __call__(self, url, kind, limit):
        self.calls.append((url, kind, limit))
        if url in self.fail:
            raise DownloadError(self.fail[url])
        if url in self.empty:
            return []
        if kind == "mix":
            return [t(f"M{i:010d}") for i in range(3)]
        if kind == "playlist":
            return [t("P0000000001"), t("P0000000002")]
        return [t(url.split("v=")[1][:11])]


def load(urls, list_fn, choice="video", sleeps=None):
    sleeps = [] if sleeps is None else sleeps

    async def choose(url):
        return choice

    async def sleep(s):
        sleeps.append(s)

    return asyncio.run(load_links(urls, list_fn, limit=50, choose_mix=choose, sleep=sleep))


def test_mix_then_only_this_video_loads_that_video():
    f = Fake()
    (o,) = load([MIX], f, choice="video")
    assert f.calls == [(MIX, "video", 50)] and [x.id for x in o.tracks] == ["AAAAAAAAAAA"] and o.error is None


def test_mix_then_full_mix():
    (o,) = load([MIX], Fake(), choice="mix")
    assert o.kind == "mix" and len(o.tracks) == 3


def test_mix_dialog_cancelled_keeps_the_link_without_error():
    (o,) = load([MIX], Fake(), choice=None)
    assert o.skipped and o.error is None and o.tracks == []


def test_plain_video_and_playlist():
    o1, o2 = load([VIDEO, PLAYLIST], Fake())
    assert [x.id for x in o1.tracks] == ["BBBBBBBBBBB"] and o2.kind == "playlist" and len(o2.tracks) == 2


def test_failure_keeps_link_with_friendly_reason_and_backs_off():
    sleeps = []
    f = Fake(fail={MIX: BOT})
    o1, o2 = load([MIX, VIDEO], f, sleeps=sleeps)
    assert o1.error == "YouTube pide verificar que no eres un robot. Espera unos minutos e inténtalo de nuevo."
    assert o1.tracks == [] and o2.tracks  # the next link still loads...
    assert sum(sleeps) >= 15  # ...after a pause, not immediately


def test_empty_result_is_an_error_not_a_silent_zero():
    (o,) = load([PLAYLIST], Fake(empty=[PLAYLIST]))
    assert o.error == "El link no tiene pistas disponibles."


def test_load_message_never_says_zero_added():
    ok = load([VIDEO], Fake())
    assert load_message(ok, added=1) == ("1 pista(s) añadidas al final de la cola.", "ok")
    assert load_message(ok, added=0) == ("La pista ya estaba en la cola.", "info")
    bad = load([MIX], Fake(fail={MIX: BOT}))
    text, kind = load_message(bad, added=0)
    assert kind == "error" and text.startswith("1 link no se pudo cargar: YouTube pide verificar")
    mixed = load([MIX, VIDEO], Fake(fail={MIX: "ERROR: Private video"}))
    text, kind = load_message(mixed, added=1)
    assert kind == "warning" and text == "1 pista(s) añadidas · 1 link no se pudo cargar: El video es privado."
