"""Regression: untrusted metadata (titles, thumbnails, URLs, paths) must never become extra element props.

NiceGUI parses `.props("k=v ...")` strings, so `.props(f'title="{x}"')` with x = 'a" onerror="…' injected
attributes (and `innerHTML`) into the app window.
"""
import asyncio
import re
from pathlib import Path

from nicegui import Client, core
from nicegui.page import page

from pista.core.models import Track
from pista.ui.components import Queue

PAYLOADS = [
    'Song " innerHTML="<img src=x onerror=document.title=\'PWNED\'>',
    'x" onmouseover="document.title=\'PWNED\'" y="',
    "x' onclick='alert(1)",
]
DANGEROUS = re.compile(r"^(on\w+|innerHTML|innerText|textContent|srcdoc|style|href)$", re.IGNORECASE)


def render(tracks):
    async def main():
        core.loop = asyncio.get_running_loop()
        client = Client(page("/"), request=None)
        with client:
            q = Queue(on_change=lambda: None, fmt_label=lambda: "MP3")
            q.add_tracks(tracks)
            await asyncio.sleep(0.05)  # let the refreshable re-render
            for t in tracks:
                q.errors[t.id] = t.title
                q.set_state(t.id, "error")
        return [dict(el.props) for el in client.elements.values()]
    return asyncio.run(main())


def test_queue_rows_keep_payloads_inside_a_single_prop():
    tracks = [Track(f"id{i}", p, p, 60, "https://www.youtube.com/watch?v=AAAAAAAAAAA", f'https://i.ytimg.com/x.jpg{p}')
              for i, p in enumerate(PAYLOADS)]
    props = render(tracks)
    injected = [p for p in props if any(DANGEROUS.match(k) for k in p)]
    assert injected == []
    titles = {p["title"] for p in props if "title" in p}
    assert set(PAYLOADS) <= titles  # the full text survives, verbatim, as one title value
    srcs = {p["src"] for p in props if "src" in p}
    assert {f"https://i.ytimg.com/x.jpg{p}" for p in PAYLOADS} <= srcs


def test_no_props_strings_built_from_data_in_ui_code():
    offenders = []
    for f in Path(__file__).parent.parent.joinpath("pista", "ui").glob("*.py"):
        for n, line in enumerate(f.read_text("utf-8").splitlines(), 1):
            if re.search(r"\.props\(\s*f['\"]", line) or re.search(r"\.props\([^)]*['\"]\s*\+", line):
                offenders.append(f"{f.name}:{n}: {line.strip()}")
    assert offenders == []
