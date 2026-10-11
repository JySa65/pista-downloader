"""Completion is per format: an MP3 being done must not block the MP4 (and vice versa)."""
import asyncio

from pista.core.loading import LoadOutcome, load_message
from pista.core.plan import plan_download
from pista.core.queue import BatchRunner, QueueModel

from tests.chaos.conftest import track


def model(n=1, fmt="audio"):
    m = QueueModel(fmt=fmt)
    m.add_tracks([track(i) for i in range(n)])
    return m


def run_batch(m, fmt, path_for=lambda t: f"/o/{t.id}.x"):
    asyncio.run(BatchRunner(m, lambda t, *a: path_for(t), out="/o", quality="192", fmt=fmt).run())


def test_mp3_done_then_switch_to_mp4_is_pending_again():
    m = model()
    run_batch(m, "audio")
    tid = "vid00000000"
    assert m.state[tid][0] == "done" and m.done[tid]["audio"][0] == "/o/vid00000000.x"
    m.set_format("video")
    assert m.state[tid][0] == "queued" and m.other_formats(tid) == ["audio"]
    plan = plan_download([(t, m.state[t.id][0], True) for t in m.tracks], "video", "720p", set(), False, True)
    assert plan.count == 1 and plan.can_start and not any("ya están" in n for _, n in plan.notes)
    run_batch(m, "video")
    assert m.state[tid][0] == "done" and set(m.done[tid]) == {"audio", "video"}
    m.set_format("audio")
    assert m.state[tid][0] == "done" and m.other_formats(tid) == ["video"]


def test_size_follows_the_selected_format(tmp_path):
    mp3, mp4 = tmp_path / "a.mp3", tmp_path / "a.mp4"
    mp3.write_bytes(b"x" * 300)
    mp4.write_bytes(b"x" * 900)
    m = model()
    run_batch(m, "audio", lambda t: str(mp3))
    assert m.sizes["vid00000000"] == 300
    m.set_format("video")
    assert "vid00000000" not in m.sizes  # no MP4 yet: no size shown for it
    run_batch(m, "video", lambda t: str(mp4))
    assert m.sizes["vid00000000"] == 900
    m.set_format("audio")
    assert m.sizes["vid00000000"] == 300


def test_archive_skip_is_per_format():
    m = model()
    m.mark_done("vid00000000", "audio", None, 0)  # «Ya estaba» in MP3 via the archive
    assert m.state["vid00000000"][0] == "skipped"
    m.set_format("video")
    assert m.state["vid00000000"][0] == "queued"


def test_errors_and_stops_are_left_alone_by_a_format_switch():
    m = model(2)
    m.set_state("vid00000000", "error")
    m.set_state("vid00000001", "stopped")
    m.set_format("video")
    assert [m.state[t.id][0] for t in m.tracks] == ["error", "stopped"]


def test_readding_a_track_done_only_in_the_other_format_says_it_will_download():
    outcome = [LoadOutcome("https://youtu.be/x", "video", tracks=[track(0)])]
    assert load_message(outcome, added=0, dup_pending=1, fmt_name="MP4") == \
        ("La pista ya estaba en la cola; se descargará en MP4.", "info")
    assert load_message(outcome, added=0, dup_pending=0, fmt_name="MP4") == \
        ("La pista ya estaba en la cola (ya descargada en MP4).", "info")
