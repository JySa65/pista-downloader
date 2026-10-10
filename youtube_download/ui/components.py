"""Track list and preview dialog."""
import tempfile
from pathlib import Path

from nicegui import app, run, ui

from youtube_download.core.downloader import preview_clip
from youtube_download.core.models import Track

PREVIEW_DIR = Path(tempfile.gettempdir()) / "youtube_download_previews"
PREVIEW_DIR.mkdir(exist_ok=True)
app.add_media_files("/media", PREVIEW_DIR)


def hhmmss(seconds: float | None) -> str:
    if not seconds:
        return "?"
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def open_preview(track: Track) -> None:
    """Dialog with the YouTube embed; a button swaps in a local 30 s clip."""
    with ui.dialog() as dialog, ui.card().classes("w-[860px] max-w-full"):
        with ui.row().classes("w-full items-center"):
            ui.label(track.title).classes("text-lg font-medium grow")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")
        player = ui.column().classes("w-full")
        with player:
            ui.element("iframe").props(
                f'src="https://www.youtube.com/embed/{track.id}?autoplay=1" '
                'allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen'
            ).classes("w-full aspect-video rounded")

        async def load_clip() -> None:
            clip_btn.props("loading")
            try:
                path = await run.io_bound(preview_clip, track.url, PREVIEW_DIR)
            except Exception as e:
                ui.notify(f"No se pudo descargar el clip: {e}", type="negative")
                clip_btn.props(remove="loading")
                return
            if path is None:  # app shutting down
                return
            player.clear()
            with player:
                ui.video(f"/media/{path.name}", autoplay=True).classes("w-full rounded")
            clip_btn.set_visibility(False)

        clip_btn = ui.button("¿No carga? Ver clip de 30 s", icon="movie", on_click=load_clip).props("flat")
    dialog.on("hide", dialog.delete)
    dialog.open()


class TrackList:
    """Checkable list of tracks with a progress bar per row."""

    def __init__(self) -> None:
        self.tracks: list[Track] = []
        self.checked: dict[str, bool] = {}
        self.bars: dict[str, ui.linear_progress] = {}
        self.render()

    def set_tracks(self, tracks: list[Track]) -> None:
        self.tracks = tracks
        self.checked = {t.id: True for t in tracks}
        self.render.refresh()

    def select_all(self, value: bool) -> None:
        self.checked = {t.id: value for t in self.tracks}
        self.render.refresh()

    def selected(self) -> list[Track]:
        return [t for t in self.tracks if self.checked.get(t.id)]

    @ui.refreshable_method
    def render(self) -> None:
        self.bars = {}
        if not self.tracks:
            ui.label("Pega una o más URLs y pulsa «Cargar».").classes("text-gray-500 py-8 self-center")
            return
        for t in self.tracks:
            with ui.card().classes("w-full p-2").props("flat bordered"):
                with ui.row().classes("w-full items-center no-wrap gap-3"):
                    ui.checkbox(value=self.checked[t.id],
                                on_change=lambda e, t=t: self.checked.__setitem__(t.id, e.value))
                    if t.thumbnail:
                        ui.image(t.thumbnail).classes("w-28 rounded").props("ratio=1.78")
                    with ui.column().classes("grow gap-0 min-w-0"):
                        ui.label(t.title).classes("font-medium truncate w-full")
                        ui.label(f"{t.channel} · {hhmmss(t.duration)}").classes("text-sm text-gray-500")
                        self.bars[t.id] = ui.linear_progress(value=0, show_value=False).classes("mt-1")
                    ui.button("▶ Ver", on_click=lambda t=t: open_preview(t)).props("flat dense")
