import pytest

import pista.core.downloader as dl
from pista.core.progress import DOWNLOAD_WEIGHT, batch_status, item_progress, phase_for_postprocessor, row_label
from pista.core.queue import QueueModel, progress_total

from tests.chaos.conftest import track


@pytest.mark.parametrize("key, phase", [
    ("ExtractAudio", "converting"), ("Metadata", "converting"), ("EmbedThumbnail", "converting"),
    ("Merger", "merging"), ("ThumbnailsConvertor", None), ("MoveFiles", None), ("Whatever", None),
])
def test_phase_for_postprocessor(key, phase):
    assert phase_for_postprocessor(key) == phase


def test_item_progress_weights_download_and_conversion():
    assert DOWNLOAD_WEIGHT == 85
    assert item_progress("queued", None, 0) == 0
    assert item_progress("running", "downloading", 50) == 42.5
    assert item_progress("running", "downloading", 100) == 85
    assert item_progress("running", "converting", 0) == 85 and item_progress("running", "merging", 0) == 85
    assert item_progress("done", None, 0) == item_progress("skipped", None, 0) == item_progress("error", None, 0) == 100
    assert item_progress("stopped", None, 40) == 34


def test_row_labels():
    assert row_label("running", 37.4, 0, "downloading") == "Descargando 37%"
    assert row_label("running", 0, 0, "converting") == "Convirtiendo…"
    assert row_label("running", 0, 0, "merging") == "Uniendo…"
    assert row_label("done", 100, 0, None) == "Listo"
    assert row_label("queued", 0, 1, None) == "Reintentando (2/3)"


def test_batch_status():
    assert batch_status("downloading", 2, 5, "MP3 192 kbps") == "Descargando 2 de 5 · MP3 192 kbps"
    assert batch_status("converting", 2, 5, "MP3 192 kbps") == "Convirtiendo 2 de 5…"
    assert batch_status("merging", 1, 1, "MP4 720p") == "Uniendo audio y video 1 de 1…"


def test_overall_progress_has_no_jump_at_the_end_of_the_download():
    m = QueueModel()
    m.add_tracks([track(0)])
    m.set_state("vid00000000", "running", 99, phase="downloading")
    assert progress_total(m) == pytest.approx(84.15)
    m.set_state("vid00000000", "running", 0, phase="converting")
    assert progress_total(m) == 85
    assert m.phase == {"vid00000000": "converting"}
    m.set_state("vid00000000", "done")
    assert progress_total(m) == 100 and m.phase == {}


def test_download_reports_phases_from_yt_dlp_hooks(tmp_path, monkeypatch):
    seen = []

    class Fake:
        def __init__(self, opts):
            self.opts = opts
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def extract_info(self, url, download=True):
            for hook in self.opts["progress_hooks"]:
                hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
                hook({"status": "finished"})
            for hook in self.opts["postprocessor_hooks"]:
                hook({"status": "started", "postprocessor": "ThumbnailsConvertor"})
                hook({"status": "started", "postprocessor": "ExtractAudio"})
                hook({"status": "finished", "postprocessor": "ExtractAudio"})
                hook({"status": "started", "postprocessor": "EmbedThumbnail"})
            return {"requested_downloads": [{"filepath": str(tmp_path / "a.mp3")}]}

    monkeypatch.setattr(dl, "_ydl", Fake)
    dl.download(track(0), tmp_path, "192", on_progress=lambda pct, phase: seen.append((phase, round(pct))))
    phases = [p for p, _ in seen]
    assert phases[0] == "downloading" and ("downloading", 50) in seen
    assert phases.index("converting") > phases.index("downloading")
    assert "converting" in phases and set(phases) <= {"downloading", "converting"}
