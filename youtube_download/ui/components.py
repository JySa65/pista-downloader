"""Download queue, preview dialog and Mix dialog."""
import webbrowser
from collections.abc import Callable

from nicegui import app, run, ui

from youtube_download.core.batch import Summary, human_size, human_time
from youtube_download.core.downloader import preview_clip
from youtube_download.core.models import Track
from youtube_download.core.system import user_cache_dir

PREVIEW_DIR = user_cache_dir() / "previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
app.add_media_files("/media", PREVIEW_DIR)


def hhmmss(seconds: float | None) -> str:
    if not seconds:
        return "?"
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def button(text: str, cls: str, on_click: Callable | None = None, stop: bool = False) -> ui.element:
    """Plain <button> styled by theme classes; stop=True keeps the click from reaching the row."""
    b = ui.element("button").classes(cls)
    with b:
        ui.label(text)
    if on_click:
        b.on("click.stop" if stop else "click", on_click)
    return b


async def ask_mix(limit: int) -> str | None:
    with ui.dialog() as dialog, ui.card().classes("yt-modal w-[420px] max-h-[90vh] overflow-auto p-[22px] gap-[14px]"):
        ui.label("Esta URL es parte de un Mix").classes("text-[15px] font-semibold")
        ui.label(f"¿Solo este video o el Mix completo (máx. {limit})?").classes("text-[13px] yt-muted")
        with ui.row().classes("w-full justify-end gap-2 mt-1"):
            button("Solo este video", "yt-btn", lambda: dialog.submit("video"))
            button("Mix completo", "yt-primary", lambda: dialog.submit("mix"))
    choice = await dialog
    dialog.delete()
    return choice


def open_preview(track: Track) -> None:
    """YouTube embed first; the clip button swaps in a local 30 s clip (and back)."""
    embed = f"https://www.youtube.com/embed/{track.id}?autoplay=1"
    showing_clip = False

    with ui.dialog() as dialog, ui.card().classes("yt-modal w-[780px] max-h-[90vh] p-0 gap-0 overflow-auto no-wrap"):
        with ui.row().classes("w-full items-center justify-between no-wrap gap-4 py-[14px] pl-5 pr-4"):
            with ui.column().classes("min-w-0 gap-0.5"):
                ui.label(track.title).classes("text-sm font-semibold truncate w-full")
                ui.label(f"{track.channel} · {hhmmss(track.duration)}").classes("text-xs yt-muted")
            button("×", "yt-ghost w-8 h-8 text-lg", dialog.close)
        player = ui.element("div").classes("mx-4 aspect-video rounded-lg overflow-hidden").style("width: calc(100% - 32px)")

        def show_embed() -> None:
            nonlocal showing_clip
            showing_clip = False
            player.clear()
            with player:
                ui.element("iframe").props(
                    f'src="{embed}" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen'
                ).classes("w-full h-full border-0")
            clip_text.text = "¿No carga? Ver clip de 30 s"

        async def toggle_clip() -> None:
            nonlocal showing_clip
            if showing_clip:
                show_embed()
                return
            clip_text.text = "Descargando clip…"
            try:
                path = await run.io_bound(preview_clip, track.url, PREVIEW_DIR)
            except Exception as e:
                ui.notify(f"No se pudo descargar el clip: {e}", type="negative")
                clip_text.text = "¿No carga? Ver clip de 30 s"
                return
            if path is None:  # app shutting down
                return
            player.clear()
            with player:
                ui.video(f"/media/{path.name}", autoplay=True).classes("w-full h-full")
            showing_clip = True
            clip_text.text = "Ver video completo"

        with ui.row().classes("w-full items-center justify-between px-4 py-3"):
            with ui.element("button").classes("yt-link").on("click", toggle_clip):
                clip_text = ui.label()
            button("Abrir en el navegador", "yt-btn h-8 text-xs", lambda: webbrowser.open(track.url))
        show_embed()
    dialog.on("hide", dialog.delete)
    dialog.open()


def summary_dialog(summary: Summary, folder: str, go_player: Callable[[], None],
                   open_folder: Callable[[], None], retry_failed: Callable[[], None] | None) -> None:
    """End-of-batch summary (after the automatic retry pass)."""
    with ui.dialog() as dialog, ui.card().classes("yt-modal yt-summary w-[520px] max-h-[90vh] overflow-auto p-[22px] gap-[14px]"):
        ui.label("Descarga finalizada").classes("text-[15px] font-semibold")
        with ui.element("div").classes("grid grid-cols-4 gap-2 w-full"):
            for label, n, cls in (("Descargadas", summary.done, "ok"), ("Ya estaban", summary.skipped, ""),
                                  ("Fallidas", summary.failed, "err" if summary.failed else ""),
                                  ("Detenidas", summary.stopped, "")):
                with ui.column().classes("yt-box p-2.5 gap-0 items-start"):
                    ui.label(str(n)).classes(f"yt-stat {cls} text-xl font-semibold mono")
                    ui.label(label).classes("text-[11px] yt-muted")
        ui.label(f"{human_size(summary.total_bytes)} · {human_time(summary.elapsed)}").classes("text-[13px] yt-muted")
        ui.label(folder).classes("mono text-xs yt-text2 break-all")
        if summary.failures:
            ui.label("Fallidas").classes("yt-label")
            with ui.column().classes("yt-box w-full p-2 gap-1 max-h-40 overflow-auto no-wrap"):
                for title, reason in summary.failures:
                    with ui.column().classes("gap-0 w-full"):
                        ui.label(title).classes("text-[13px] font-medium truncate w-full")
                        ui.label(reason).classes("text-xs yt-error")
        with ui.row().classes("w-full justify-end gap-2 mt-1"):
            button("Cerrar", "yt-btn", dialog.close)
            if retry_failed:
                button("Reintentar fallidas", "yt-btn", lambda: (dialog.close(), retry_failed()))
            button("Abrir carpeta", "yt-btn", open_folder)
            go = button("Ir al reproductor", "yt-primary", lambda: (dialog.close(), go_player()))
            if not summary.first_new:
                go.props('title="No hay archivos nuevos; se abre la biblioteca"')
    dialog.on("hide", dialog.delete)
    dialog.open()


STATES = {  # state -> (pill class, fill class, label)
    "queued": ("", "", "En cola"),
    "running": ("run", "", None),  # label is the percentage
    "done": ("ok", "ok", "Listo"),
    "skipped": ("ok", "ok", "Ya estaba"),
    "error": ("err", "err", "Error"),
    "stopped": ("", "", "Detenida"),
}


class Queue:
    """Checkable track rows with a status pill and progress bar each."""

    def __init__(self, on_change: Callable[[], None]) -> None:
        self.tracks: list[Track] = []
        self.checked: dict[str, bool] = {}
        self.state: dict[str, tuple[str, float]] = {}
        self.rows: dict[str, tuple[ui.element, ui.element, ui.label, ui.element]] = {}
        self.errors: dict[str, str] = {}
        self.retry_shown: dict[str, bool] = {}
        self.on_retry: Callable[[str], None] = lambda track_id: None
        self.on_change = on_change
        self.render()

    def set_tracks(self, tracks: list[Track]) -> None:
        self.tracks = tracks
        self.checked = {t.id: True for t in tracks}
        self.state = {t.id: ("queued", 0.0) for t in tracks}
        self.render.refresh()
        self.on_change()

    def add_tracks(self, tracks: list[Track]) -> int:
        """Append new tracks (deduplicated by video id), checked and queued; returns how many were added."""
        new = [t for t in dict((t.id, t) for t in tracks).values() if t.id not in self.state]
        self.tracks += new
        for t in new:
            self.checked[t.id] = True
            self.state[t.id] = ("queued", 0.0)
        if new:
            self.render.refresh()
            self.on_change()
        return len(new)

    def next_pending(self) -> Track | None:
        """Next checked, queued track; re-read each time so tracks added mid-download are picked up."""
        return next((t for t in self.tracks if self.checked.get(t.id) and self.state[t.id][0] == "queued"), None)

    def clear_finished(self, keep: str | None) -> int:
        """Drop finished, failed, stopped and unchecked rows; never the one downloading (`keep`)."""
        drop = {t.id for t in self.tracks if t.id != keep and (
            not self.checked.get(t.id) or self.state[t.id][0] in ("done", "skipped", "error", "stopped"))}
        self.tracks = [t for t in self.tracks if t.id not in drop]
        for d in (self.checked, self.state, self.errors):
            for k in drop:
                d.pop(k, None)
        self.render.refresh()
        self.on_change()
        return len(drop)

    def select_all(self, value: bool) -> None:
        self.checked = {t.id: value for t in self.tracks}
        self.render.refresh()
        self.on_change()

    def toggle(self, track_id: str) -> None:
        self.checked[track_id] = not self.checked[track_id]
        self.render.refresh()
        self.on_change()

    def selected(self) -> list[Track]:
        return [t for t in self.tracks if self.checked.get(t.id)]

    def set_state(self, track_id: str, state: str, pct: float = 0.0) -> None:
        self.state[track_id] = (state, pct)
        if track_id not in self.rows:
            return
        fill, pill_el, pill, actions = self.rows[track_id]
        pill_cls, fill_cls, label = STATES[state]
        width = 100 if state in ("done", "skipped", "error") else pct
        fill.classes(replace=f"yt-fill {fill_cls}").style(f"width: {width:.0f}%")
        pill_el.classes(replace=f"yt-pill {pill_cls}")
        pill.text = label or f"{pct:.0f}%"
        pill_el.props(f'title="{self.errors.get(track_id, "")}"' if state == "error" else 'title=""')
        if self.retry_shown.get(track_id) != (state == "error"):
            self._actions(actions, track_id)

    def _actions(self, actions: ui.element, track_id: str) -> None:
        track = next(t for t in self.tracks if t.id == track_id)
        error = self.state[track_id][0] == "error"
        self.retry_shown[track_id] = error
        actions.clear()
        with actions:
            if error:
                button("Reintentar", "yt-link", lambda: self.on_retry(track_id), stop=True)
            button("▶ Ver", "yt-link", lambda: open_preview(track), stop=True)

    @ui.refreshable_method
    def render(self) -> None:
        self.rows, self.retry_shown = {}, {}
        if not self.tracks:
            with ui.element("div").classes("h-full w-full flex items-center justify-center"):
                ui.label("Pega una o más URLs y pulsa «Cargar».").classes("text-[13px] yt-subtle")
            return
        for t in self.tracks:
            on = self.checked[t.id]
            with ui.element("div").classes("yt-row").on("click", lambda t=t: self.toggle(t.id)):
                with ui.element("div").classes("yt-check on" if on else "yt-check"):
                    ui.label("✓" if on else "")
                if t.thumbnail:
                    ui.element("img").props(f'src="{t.thumbnail}" loading="lazy"').classes("yt-thumb")
                else:
                    ui.element("div").classes("yt-thumb")
                with ui.column().classes("min-w-0 gap-[3px]"):
                    ui.label(t.title).classes("text-[13px] font-medium truncate w-full")
                    ui.label(f"{t.channel} · {hhmmss(t.duration)}").classes("text-xs yt-muted")
                    with ui.element("div").classes("yt-track w-full"):
                        fill = ui.element("div").classes("yt-fill")
                with ui.element("div").classes("yt-pill") as pill_el:
                    pill = ui.label()
                actions = ui.element("div").classes("yt-actions")
            self.rows[t.id] = (fill, pill_el, pill, actions)
            self._actions(actions, t.id)
            self.set_state(t.id, *self.state[t.id])
