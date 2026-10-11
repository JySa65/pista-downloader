"""'Reproductor' tab: browse MP3/MP4 files in a folder and play them (cover art or video)."""
import base64
import random
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from nicegui import app, ui

from pista.core.applog import redact
from pista.core.library import cover_bytes, scan, split_artist
from pista.core.system import default_outdir

from .components import attrs, button, hhmmss

_routes: dict[str, str] = {}


def shown(path: str | Path) -> str:
    """Folder as displayed: home directory shortened to ~."""
    return redact(str(path), str(Path.home()))  # folder -> media url prefix


def media_url(folder: Path, file: Path) -> str:
    key = str(folder.resolve())
    if key not in _routes:
        _routes[key] = f"/library/{len(_routes)}"
        app.add_media_files(_routes[key], key)  # path-traversal safe, supports range requests
    return f"{_routes[key]}/{quote(file.relative_to(folder).as_posix())}"


class Player:
    def __init__(self, get_outdir: Callable[[], str], pick_folder: Callable) -> None:
        self.get_outdir = get_outdir
        self.pick_folder = pick_folder
        self.folder: Path | None = None  # None = follow the download folder
        self.extra: list[str] = []
        self.files: list[Path] = []
        self.cur: int | None = None
        self.playing = False
        self.duration = 0.0
        self.shuffle = self.repeat = False
        self.video: ui.video | None = None  # set while an MP4 plays in the cover area

        with ui.element("div").classes("flex-1 min-h-0 w-full grid") \
                .style("grid-template-columns: minmax(0, 1fr) 380px; grid-template-rows: minmax(0, 1fr)"):
            with ui.column().classes("min-h-0 gap-0 no-wrap"):
                with ui.row().classes("w-full items-center justify-between no-wrap px-6 pt-5 pb-3 shrink-0"):
                    with ui.row().classes("items-center gap-3 no-wrap min-w-0"):
                        ui.label("Biblioteca").classes("text-lg font-semibold")
                        with ui.element("button").classes("yt-btn yt-folderbtn h-8 mono text-xs flex items-center gap-2"):
                            self.folder_label = ui.label().classes("truncate min-w-0")
                            ui.label("▼").classes("text-[10px] yt-muted")
                            self.menu = ui.menu().props("auto-close").classes("yt-menu")
                        self.count = ui.label().classes("text-[13px] yt-muted whitespace-nowrap")
                    self.query = ui.input(placeholder="Buscar", on_change=lambda: self.render.refresh()) \
                        .props("borderless dense").classes("yt-field w-[200px] h-8")
                with ui.element("div").classes("yt-libhead shrink-0"):
                    for h in ("#", "Tipo", "Título", "Artista"):
                        ui.label(h)
                    ui.label("Dur.").classes("text-right")
                with ui.column().classes("flex-1 min-h-0 overflow-auto px-4 py-1.5 gap-0 w-full no-wrap"):
                    self.render()
            with ui.column().classes("yt-panel yt-line-l px-7 py-6 gap-[18px] min-h-0 overflow-auto no-wrap"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Reproduciendo").classes("yt-label")
                    self.fmt_tag = ui.label("MP3").classes("yt-fmt pad")
                    self.fmt_tag.set_visibility(False)
                self.cover = ui.element("div").classes("yt-cover w-full overflow-hidden shrink-0")
                self.show_placeholder()
                with ui.column().classes("gap-1 w-full"):
                    self.title = ui.label("—").classes("text-lg font-semibold leading-snug")
                    self.artist = ui.label().classes("text-sm yt-muted")
                with ui.column().classes("gap-1 w-full"):
                    self.seek = ui.slider(min=0, max=1000, value=0).props("dense color=primary")
                    self.seek.on("change", lambda e: self.duration and self.media().seek(e.args / 1000 * self.duration))
                    with ui.row().classes("w-full justify-between mono text-[11px] yt-muted"):
                        self.pos_label = ui.label("0:00")
                        self.dur_label = ui.label("0:00")

        with ui.element("div").classes("yt-line-t w-full h-[76px] shrink-0 grid items-center px-6") \
                .style("grid-template-columns: 1fr auto 1fr; background: var(--bar)"):
            with ui.row().classes("gap-1.5"):
                self.shuffle_btn = button("Aleatorio", "yt-toggle", lambda: self.toggle("shuffle"))
                self.repeat_btn = button("Repetir", "yt-toggle", lambda: self.toggle("repeat"))
            with ui.row().classes("items-center gap-3.5 no-wrap"):
                button("◀◀", "yt-skip", self.prev)
                with ui.element("button").classes("yt-play").on("click", self.toggle_play):
                    self.play_icon = ui.label("▶")
                button("▶▶", "yt-skip", lambda: self.step(1))
            with ui.row().classes("items-center justify-end gap-2.5 no-wrap"):
                ui.label("Volumen").classes("text-xs yt-muted")
                self.volume = ui.slider(min=0, max=100, value=70, on_change=self.set_volume) \
                    .props("dense color=primary").classes("w-[120px]")

        self.audio = self.wire(ui.audio("", controls=False, autoplay=True).classes("hidden"))
        ui.keyboard(on_key=self.on_key, ignore=["input", "textarea"])

    def on_key(self, e) -> None:
        if e.key == "Escape" and e.action.keydown:
            self.set_full(False)

    def set_full(self, full: bool) -> None:
        """In-window fullscreen for the MP4 (a fixed overlay; works in every webview)."""
        if self.video is None:
            return
        self.cover.classes(add="full" if full else "", remove="" if full else "full")
        self.full_text.text = "Salir (Esc)" if full else "⛶ Pantalla completa"

    def wire(self, el):
        """Same transport events for the hidden <audio> and the MP4 <video>."""
        el.on("timeupdate", self.on_time, js_handler="(e) => emit(e.target.currentTime, e.target.duration)",
              throttle=0.5)
        el.on("ended", self.on_ended)
        el.on("play", lambda: self.set_playing(True))
        el.on("pause", lambda: self.set_playing(False))
        return el

    def media(self):
        return self.video or self.audio

    def show_placeholder(self) -> None:
        self.cover.classes(replace="yt-cover w-full overflow-hidden shrink-0")
        self.cover.clear()
        with self.cover:
            ui.label("portada")

    def show_cover(self, f: Path) -> None:
        """Cover embedded in the MP3 at download time; placeholder when there is none."""
        found = cover_bytes(f) if f.suffix.lower() == ".mp3" else None
        self.show_placeholder()
        if not found:
            return
        data, mime = found
        self.cover.clear()
        with self.cover:
            attrs(ui.element("img"), src=f"data:{mime};base64,{base64.b64encode(data).decode()}", alt="portada") \
                .classes("w-full h-full object-cover")

    # --- library ---
    def root(self) -> Path:
        return self.folder or self.outdir()

    def outdir(self) -> Path:
        return Path(self.get_outdir()).expanduser() if self.get_outdir() else default_outdir()

    def reload(self) -> None:
        self.files = scan(self.root())
        if self.cur is not None and self.cur >= len(self.files):
            self.cur = None
        self.folder_label.text = shown(self.root())
        attrs(self.folder_label, title=str(self.root()))
        self.count.text = f"{len(self.files)} archivos"
        self.build_menu()
        self.render.refresh()

    def build_menu(self) -> None:
        out = str(self.outdir())
        home = Path.home()
        common = [str(p) for p in (home / "Music", home / "Downloads") if p.is_dir()]
        options = dict.fromkeys([out, *common, *self.extra])
        self.menu.clear()
        with self.menu:
            for path in options:
                with ui.menu_item(on_click=lambda p=path: self.set_folder(p)):
                    with ui.row().classes("w-full justify-between no-wrap gap-2.5 items-center"):
                        ui.label(shown(path)).classes("mono text-xs truncate" + (" text-primary" if Path(path) == self.root() else ""))
                        ui.label("carpeta de descarga" if path == out else "").classes("text-[11px] yt-subtle")
            ui.separator()
            ui.menu_item("Elegir otra carpeta…", on_click=self.choose).classes("text-primary")

    def set_folder(self, path: str) -> None:
        out = str(self.outdir())
        self.folder = None if path == out else Path(path)
        self.reload()

    async def choose(self) -> None:
        path = await self.pick_folder(str(self.root()))
        if path:
            self.extra.append(path)
            self.set_folder(path)

    @ui.refreshable_method
    def render(self) -> None:
        q = (self.query.value or "").lower() if hasattr(self, "query") else ""
        if not self.files:
            ui.label("No hay MP3 ni MP4 en esta carpeta.").classes("text-[13px] yt-subtle self-center py-10")
        for i, f in enumerate(self.files):
            artist, title = split_artist(f.stem)
            if q and q not in f.stem.lower():
                continue
            cur = i == self.cur
            with ui.element("div").classes("yt-librow w-full" + (" cur" if cur else "")).on("click", lambda i=i: self.play(i)):
                ui.label("▶" if cur and self.playing else f"{i + 1:02d}").classes("n mono text-xs yt-subtle")
                is_video = f.suffix.lower() == ".mp4"
                ui.label("MP4" if is_video else "MP3").classes("yt-fmt" + (" mp4" if is_video else ""))
                ui.label(title).classes("t text-[13px] font-medium truncate")
                ui.label(artist or f.parent.name).classes("text-[13px] yt-muted truncate")
                ui.label(hhmmss(self.duration) if cur and self.duration else "—").classes("mono text-xs yt-muted text-right")

    # --- playback ---
    def play(self, i: int) -> None:
        if not self.files:
            return
        self.cur = i % len(self.files)
        f = self.files[self.cur]
        artist, title = split_artist(f.stem)
        self.title.text, self.artist.text = title, artist or f.parent.name
        self.duration = 0.0
        src = media_url(self.root(), f)
        is_video = f.suffix.lower() == ".mp4"
        self.fmt_tag.text = "MP4" if is_video else "MP3"
        self.fmt_tag.classes(replace="yt-fmt pad" + (" mp4" if is_video else ""))
        self.fmt_tag.set_visibility(True)
        if is_video:
            self.audio.pause()
            self.cover.clear()
            self.cover.classes(replace="yt-videobox shrink-0")
            with self.cover:
                self.video = self.wire(ui.video(src, controls=True, autoplay=True))
                with ui.element("button").classes("yt-fullbtn").on(
                        "click", lambda: self.set_full("full" not in self.cover.classes)):
                    self.full_text = ui.label("⛶ Pantalla completa")
        else:
            if self.video is not None:
                self.video.pause()
                self.video = None
            self.show_cover(f)
            self.audio.set_source(src)
        self.set_volume()
        self.render.refresh()

    def play_path(self, path: Path) -> None:
        """Show the library containing `path` and play it (used after a download batch)."""
        self.reload()
        try:
            path.relative_to(self.root())
        except ValueError:
            self.set_folder(str(path.parent))
        resolved = [f.resolve() for f in self.files]
        if path.resolve() in resolved:
            self.play(resolved.index(path.resolve()))

    def step(self, d: int) -> None:
        if not self.files:
            return
        if self.shuffle:
            self.play(random.randrange(len(self.files)))
        else:
            self.play((self.cur if self.cur is not None else -1) + d)

    def prev(self) -> None:
        if self.seek.value > 0 and self.duration and self.seek.value / 1000 * self.duration > 3:
            self.media().seek(0)
        else:
            self.step(-1)

    def toggle_play(self) -> None:
        if self.cur is None:
            self.step(1)
        elif self.playing:
            self.media().pause()
        else:
            self.media().play()

    def toggle(self, name: str) -> None:
        setattr(self, name, not getattr(self, name))
        btn = self.shuffle_btn if name == "shuffle" else self.repeat_btn
        btn.classes(replace="yt-toggle on" if getattr(self, name) else "yt-toggle")

    def set_playing(self, playing: bool) -> None:
        self.playing = playing
        self.play_icon.text = "❚❚" if playing else "▶"
        self.render.refresh()

    def set_volume(self) -> None:
        el = self.media()
        ui.run_javascript(f"const m = getHtmlElement({el.id}); if (m) m.volume = {self.volume.value / 100}")

    def on_time(self, e) -> None:
        pos, dur = e.args
        if dur and dur != self.duration:
            self.duration = dur
            self.dur_label.text = hhmmss(dur)
            self.render.refresh()
        self.pos_label.text = hhmmss(pos) if pos else "0:00"
        if self.duration:
            self.seek.value = pos / self.duration * 1000

    def on_ended(self) -> None:
        if self.repeat:
            self.media().seek(0)
            self.media().play()
        else:
            self.step(1)
