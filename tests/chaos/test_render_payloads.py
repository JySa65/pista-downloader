"""13: hostile metadata inside error reasons, the summary and log lines still renders inert."""
import asyncio
import re

from nicegui import Client, core
from nicegui.page import page

from pista.core.batch import Result, summarize
from pista.ui.components import Queue, log_file_dialog, summary_dialog

from .conftest import PAYLOAD, track

DANGEROUS = re.compile(r"^(on\w+|innerHTML|innerText|textContent|srcdoc|style|href)$", re.IGNORECASE)


def render(build):
    async def main():
        core.loop = asyncio.get_running_loop()
        client = Client(page("/"), request=None)
        with client:
            build()
            await asyncio.sleep(0.05)
        return [(type(el).__name__, dict(el.props), getattr(el, "text", None)) for el in client.elements.values()]
    return asyncio.run(main())


def assert_inert(elements):
    assert [p for _, p, _ in elements if any(DANGEROUS.match(k) for k in p)] == []


def test_error_reason_payload_in_queue():
    def build():
        q = Queue(on_change=lambda: None, fmt_label=lambda: "MP3")
        q.add_tracks([track(0, title=PAYLOAD)])
        q.errors["vid00000000"] = PAYLOAD
        q.set_state("vid00000000", "error")
    els = render(build)
    assert_inert(els)
    assert sum(1 for _, _, text in els if text == PAYLOAD) >= 2  # title and reason shown as text


def test_summary_and_log_file_payloads(tmp_path):
    log = tmp_path / "pista.log"
    log.write_text(f"2026-01-01 ERROR pista: ✗ {PAYLOAD}\n", "utf-8")

    def build():
        s = summarize([Result(PAYLOAD, "error", error=f"ERROR: {PAYLOAD}")], 1, ended_at="10:00", processed=1)
        summary_dialog(s, PAYLOAD, 1, lambda: None, lambda: None, lambda: None)
        log_file_dialog(log, "Mostrar", lambda: None)
    els = render(build)
    assert_inert(els)
    assert any(text and PAYLOAD in text for _, _, text in els)
