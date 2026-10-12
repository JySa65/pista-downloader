from pista.core.models import Track
from pista.core.plan import archived_ids, estimate_bytes, plan_download, video_sizes


def t(id_, dur=200, sizes=None):
    return Track(id_, f"T{id_}", "C", dur, f"https://youtu.be/{id_}", None, video_sizes=sizes or {})


def test_estimate_audio_from_duration_and_kbps():
    assert estimate_bytes(t("a", 200), "audio", "192") == 200 * 192_000 // 8  # 4.8 MB


def test_estimate_video_prefers_extracted_size_then_bitrate_table():
    assert estimate_bytes(t("v", 100, {"720p": 12_345_678}), "video", "720p") == 12_345_678
    assert estimate_bytes(t("v", 100), "video", "720p") == 100 * 2_500_000 // 8
    assert estimate_bytes(t("v", None), "video", "720p") == 0


def test_video_sizes_from_formats_picks_best_mp4_video_plus_m4a_audio_per_cap():
    formats = [
        {"vcodec": "avc1", "acodec": "none", "ext": "mp4", "height": 360, "filesize": 3_000_000},
        {"vcodec": "avc1", "acodec": "none", "ext": "mp4", "height": 720, "filesize_approx": 9_000_000},
        {"vcodec": "vp9", "acodec": "none", "ext": "webm", "height": 1080, "filesize": 20_000_000},
        {"vcodec": "none", "acodec": "mp4a", "ext": "m4a", "filesize": 1_000_000},
        {"vcodec": "none", "acodec": "opus", "ext": "webm", "filesize": 900_000},
    ]
    sizes = video_sizes(formats)
    assert sizes["360p"] == 4_000_000
    assert sizes["720p"] == 10_000_000
    assert sizes["1080p"] == 10_000_000  # best mp4 <= 1080 is the 720p one
    assert video_sizes([]) == {}


def test_archived_ids_reads_yt_dlp_archive(tmp_path):
    p = tmp_path / ".downloaded-audio.txt"
    p.write_text("youtube abc\nyoutube def\n\n", "utf-8")
    assert archived_ids(p) == {"abc", "def"}
    assert archived_ids(tmp_path / "missing.txt") == set()


def test_plan_counts_pending_size_duration_and_notes():
    items = [
        (t("q", 100), "queued", True),
        (t("s", 50), "stopped", True),
        (t("arch", 70), "queued", True),     # already in the library -> skipped
        (t("d", 60), "done", True),          # already downloaded in this queue
        (t("e", 80), "error", True),         # needs «Reintentar»
        (t("off", 90), "queued", False),     # not selected
    ]
    p = plan_download(items, "audio", "128", existing={"arch"}, running=False)
    assert p.count == 2 and p.pending == ["q", "s"] and p.skip == ["arch"]
    assert p.format_label == "Audio · MP3 128 kbps"
    assert p.size_bytes == (100 + 50) * 128_000 // 8
    assert p.duration == 150
    assert p.notes == [
        ("plain", "2 ya existen en tu biblioteca y se omitirán."),
        ("err", "1 fallida(s) no se incluyen. Usa «Reintentar» en su fila."),
    ]


def test_plan_running_and_nothing_pending_notes():
    p = plan_download([(t("d"), "done", True)], "video", "720p", existing=set(), running=True)
    assert p.count == 0 and p.format_label == "Video · MP4 720p"
    assert p.notes == [
        ("plain", "1 ya existen en tu biblioteca y se omitirán."),
        ("info", "Ya hay una descarga en curso; estas se añaden a la misma cola."),
        ("warn", "No hay pistas pendientes seleccionadas."),
    ]


def test_consent_required_to_start():
    items = [(t("q", 100), "queued", True)]
    assert plan_download(items, "audio", "128", set(), running=False).can_start is False
    assert plan_download(items, "audio", "128", set(), running=False, consent=True).can_start is True
    assert plan_download([], "audio", "128", set(), running=False, consent=True).can_start is False


def test_include_existing_redownloads_library_songs():
    items = [(t("q", 100), "queued", True), (t("lib", 70), "queued", True), (t("d", 60), "done", True)]
    skip = plan_download(items, "audio", "128", existing={"lib"}, running=False, consent=True)
    assert skip.pending == ["q"] and skip.skip == ["lib"] and skip.existing == 1
    assert skip.notes == [("plain", "2 ya existen en tu biblioteca y se omitirán.")]
    again = plan_download(items, "audio", "128", existing={"lib"}, running=False, consent=True, include_existing=True)
    assert again.pending == ["q", "lib"] and again.skip == [] and again.existing == 1
    assert again.size_bytes == (100 + 70) * 128_000 // 8
    assert again.notes == [("plain", "1 ya existen en tu biblioteca y se volverán a descargar."),
                           ("plain", "1 ya existen en tu biblioteca y se omitirán.")]


def test_only_existing_songs_can_start_only_when_redownloading():
    items = [(t("lib", 70), "queued", True)]
    assert plan_download(items, "audio", "128", {"lib"}, running=False, consent=True).can_start is False
    assert plan_download(items, "audio", "128", {"lib"}, False, True, include_existing=True).can_start is True
