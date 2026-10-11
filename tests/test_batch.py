import logging

from youtube_download.core.batch import Result, human_size, human_time, short_error, summarize
from youtube_download.core.applog import setup_logging


def test_summarize_counts_sizes_failures_and_first_new():
    results = [
        Result("A", "done", "/m/a.mp3", 3_000_000),
        Result("B", "skipped"),
        Result("C", "error", error="ERROR: [youtube] abc: unable to download video data: HTTP Error 403: Forbidden"),
        Result("D", "done", "/m/d.mp3", 1_000_000),
        Result("E", "stopped"),
    ]
    s = summarize(results, 125.4)
    assert (s.done, s.skipped, s.failed, s.stopped) == (2, 1, 1, 1)
    assert s.total_bytes == 4_000_000
    assert s.elapsed == 125.4
    assert s.failures == [("C", "unable to download video data: HTTP Error 403: Forbidden")]
    assert s.first_new == "/m/a.mp3"


def test_summarize_empty():
    s = summarize([], 0)
    assert (s.done, s.failed, s.total_bytes, s.first_new, s.failures) == (0, 0, 0, None, [])


def test_short_error_strips_prefixes_and_truncates():
    assert short_error("ERROR: [youtube] xYz-123_ab: Sign in to confirm you're not a bot") == \
        "Sign in to confirm you're not a bot"
    assert short_error("") == "Error desconocido"
    long = short_error("x" * 500)
    assert len(long) <= 120 and long.endswith("…")
    assert short_error("line one\nline two") == "line one"


def test_human_size_and_time():
    assert human_size(0) == "0 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(4_000_000) == "3.8 MB"
    assert human_time(5) == "5 s"
    assert human_time(125.4) == "2 min 5 s"
    assert human_time(3725) == "1 h 2 min"


def test_setup_logging_writes_rotating_file(tmp_path):
    path = setup_logging(tmp_path)
    logging.getLogger("youtube_download.yt_dlp").warning("hello %s", "world")
    logging.getLogger("youtube_download").info("x" * 3000)
    for h in logging.getLogger("youtube_download").handlers:
        h.flush()
    text = path.read_text("utf-8")
    assert path.name == "youtube-download.log"
    assert "WARNING youtube_download.yt_dlp: hello world" in text
    assert "x" * 3000 in text  # full, untruncated lines
    setup_logging(tmp_path)  # idempotent: no duplicate handlers
    assert len([h for h in logging.getLogger("youtube_download").handlers if getattr(h, "_ytmp3", False)]) == 1
