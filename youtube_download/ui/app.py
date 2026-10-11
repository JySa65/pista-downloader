"""NiceGUI desktop app with two tabs: Descargar and Reproductor."""
import asyncio
import importlib.util
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path

from nicegui import app, native, run, ui

from youtube_download import version

from youtube_download.core.applog import setup_logging
from youtube_download.core.batch import Result, human_size, human_time, short_error, summarize
from youtube_download.core.downloader import Cancelled, download, list_tracks
from youtube_download.core.system import default_outdir, has_ffmpeg, log_dir, open_path, read_clipboard
from youtube_download.core.urls import classify

from . import theme
from .components import Queue, ask_mix, button, summary_dialog
from .player import Player

QUALITIES = {"audio": ["128", "160", "192", "256", "320"], "video": ["360p", "480p", "720p", "1080p", "4K"]}
DEFAULT_QUALITY = {"audio": "192", "video": "720p"}
FFMPEG_MISSING = ("No se encontró ffmpeg. Instálalo para descargar (macOS: brew install ffmpeg · "
                  "Windows: winget install ffmpeg · Linux: sudo apt install ffmpeg).")
FORMATS = {"audio": "Audio · MP3", "video": "Video · MP4"}
TAGS = {"video": "Video", "playlist": "Playlist", "mix": "Mix"}
RETRY_DELAY = 10  # seconds before the automatic second attempt of failed items
logger = logging.getLogger("youtube_download")


async def pick_folder(start: str) -> str | None:
    """Native folder dialog; None if unavailable or cancelled."""
    if app.native.main_window is None:
        ui.notify("El selector de carpetas solo está disponible en la ventana de escritorio.", type="warning")
        return None
    import webview
    try:
        res = await app.native.main_window.create_file_dialog(webview.FileDialog.FOLDER, directory=start)
    except Exception as e:
        ui.notify(f"No se pudo abrir el selector: {e}", type="warning")
        return None
    return res[0] if res else None


@ui.page("/")
def index() -> None:
    theme.apply()
    log_path = setup_logging(log_dir())
    dark = False
    links: list[str] = []
    fmt, quality = "audio", "192"
    busy = False
    # Written from worker threads, read by the timer on the event loop.
    progress: dict = {"track": None, "pct": 0.0}
    cancel = threading.Event()

    def log(msg: str, level: int = logging.INFO) -> None:
        logger.log(level, msg)  # full line goes to the log file
        log_view.push(f"[{time.strftime('%H:%M:%S')}] {msg}")

    @ui.refreshable
    def link_list() -> None:
        if not links:
            with ui.element("div").classes("flex-1 flex items-center justify-center text-center px-4"):
                ui.label("Los links que añadas aparecerán aquí, uno por fila.").classes("text-xs yt-subtle")
            return
        for n, url in enumerate(links, start=1):
            kind = classify(url)
            with ui.element("div").classes("yt-linkrow w-full").props(f'title="{url}"'):
                ui.label(str(n)).classes("mono text-[11px] yt-subtle")
                ui.label(TAGS[kind]).classes("yt-tag" + ("" if kind == "video" else " list"))
                ui.label(re.sub(r"^https?://(www\.)?", "", url)).classes("mono text-[11px] yt-text2 truncate")
                button("×", "yt-ghost w-[22px] h-[22px] text-sm p-0", lambda u=url: set_links([x for x in links if x != u]))

    @ui.refreshable
    def quality_picker() -> None:
        ui.label("Calidad (kbps)" if fmt == "audio" else "Resolución").classes("yt-label")
        with ui.element("div").classes("yt-seg small w-full"):
            for q in QUALITIES[fmt]:
                button(q, "on" if q == quality else "", lambda q=q: set_quality(q))

    # ---------- title bar ----------
    with ui.element("div").classes("yt-bar"):
        with ui.row().classes("items-center gap-2 no-wrap"):
            ui.html(theme.ICON_SVG, sanitize=False).classes("w-5 h-5 flex")
            ui.label("YouTube → MP3").classes("text-[13px] font-semibold yt-text2")
            ui.label(f"v{version()}").classes("mono text-[11px] yt-subtle")
        with ui.element("div").classes("yt-seg"):
            tab_dl = button("Descargar", "on", lambda: show_tab("download"))
            tab_pl = button("Reproductor", "", lambda: show_tab("player"))
        with ui.row().classes("justify-end"):
            theme_btn = ui.element("button").classes("yt-btn h-7 text-xs px-2.5 yt-muted").on("click", lambda: toggle_theme())
            with theme_btn:
                theme_label = ui.label("Modo oscuro")

    def toggle_theme() -> None:
        nonlocal dark
        dark = not dark
        theme.set_theme(dark)
        theme_label.text = "Modo claro" if dark else "Modo oscuro"

    # ---------- download tab ----------
    download_tab = ui.element("div").classes("flex-1 min-h-0 w-full grid") \
        .style("grid-template-columns: 340px minmax(0, 1fr); grid-template-rows: minmax(0, 1fr)")
    with download_tab:
        with ui.column().classes("yt-panel yt-line-r px-6 py-5 gap-[14px] min-h-0 overflow-auto no-wrap"):
            with ui.column().classes("w-full gap-2"):
                with ui.row().classes("w-full justify-between items-baseline"):
                    ui.label("URLs").classes("yt-label")
                    detected = ui.label("vacío").classes("text-[11px] yt-subtle")
                # Multi-line: paste many links at once. Enter adds, Shift+Enter inserts a new line.
                draft = ui.textarea(placeholder="Pega uno o varios links (uno por línea) y pulsa Enter") \
                    .props("borderless dense rows=3").classes("yt-area w-full") \
                    .on("keydown.enter.exact.prevent", lambda: add_links(draft.value))
                with ui.element("div").classes("grid grid-cols-2 gap-2 w-full"):
                    button("Añadir", "yt-btn", lambda: add_links(draft.value))
                    button("Pegar", "yt-btn", lambda: paste()).props('title="Pegar links del portapapeles"')
                with ui.column().classes("yt-box w-full h-[100px] shrink-0 overflow-auto p-1.5 gap-1 no-wrap"):
                    link_list()
                with ui.element("div").classes("grid grid-cols-2 gap-2 w-full"):
                    button("Limpiar", "yt-btn", lambda: set_links([]))
                    load_btn = button("Cargar", "yt-primary", lambda: load())

            with ui.column().classes("w-full gap-4"):
                with ui.column().classes("w-full gap-1.5"):
                    ui.label("Carpeta de salida").classes("yt-label")
                    with ui.row().classes("w-full gap-1.5 no-wrap"):
                        outdir = ui.input(value=str(default_outdir())).props("borderless dense") \
                            .classes("yt-field flex-1 min-w-0")
                        button("Cambiar", "yt-btn text-xs", lambda: change_outdir())
                with ui.column().classes("w-full gap-1.5"):
                    ui.label("Formato").classes("yt-label")
                    with ui.element("div").classes("yt-seg two w-full"):
                        f_btns = {f: button(label, "on" if f == fmt else "", lambda f=f: set_format(f))
                                  for f, label in FORMATS.items()}
                with ui.column().classes("w-full gap-1.5"):
                    quality_picker()
                with ui.column().classes("w-full gap-1.5"):
                    with ui.row().classes("w-full justify-between"):
                        ui.label("Canciones por Mix").classes("yt-label")
                        mix_value = ui.label("50").classes("mono text-xs yt-text2")
                    mix_hint = ui.label().classes("text-xs yt-subtle leading-normal")
                    mix_limit = ui.slider(min=1, max=50, value=50).props("dense color=primary")

            ui.element("div").classes("flex-1")
            with ui.column().classes("w-full gap-1.5"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Registro").classes("yt-label")
                    with ui.row().classes("gap-1"):
                        button("Abrir registro", "yt-link", lambda: open_log()).props(f'title="{log_path}"')
                        expand_btn = button("Ampliar", "yt-link", lambda: toggle_log())
                log_view = ui.log(max_lines=1000).classes("yt-log w-full h-32 shrink-0")

        with ui.column().classes("min-h-0 gap-0 no-wrap"):
            with ui.row().classes("w-full items-center justify-between px-6 pt-5 pb-3.5 shrink-0"):
                with ui.row().classes("items-baseline gap-2.5"):
                    ui.label("Cola").classes("text-lg font-semibold")
                    counter = ui.label().classes("text-[13px] yt-muted")
                with ui.row().classes("gap-1"):
                    button("Todas", "yt-link", lambda: queue.select_all(True))
                    button("Ninguna", "yt-link", lambda: queue.select_all(False))
                    button("Limpiar cola", "yt-link", lambda: clear_queue()).props(
                        'title="Quita las terminadas, fallidas y no seleccionadas"')
            with ui.column().classes("flex-1 min-h-0 overflow-auto px-4 gap-0 w-full no-wrap"):
                queue = Queue(on_change=lambda: update_counter())
                queue.on_retry = lambda track_id: retry([track_id])
            with ui.row().classes("yt-panel yt-line-t w-full items-center gap-4 px-6 py-3.5 no-wrap shrink-0"):
                with ui.column().classes("flex-1 min-w-0 gap-1.5"):
                    with ui.row().classes("w-full justify-between text-xs yt-muted"):
                        status = ui.label("Listo.")
                        total_label = ui.label("0%").classes("mono")
                    with ui.element("div").classes("yt-track big w-full"):
                        total_fill = ui.element("div").classes("yt-fill")
                stop_btn = button("Detener", "yt-danger", cancel.set)
                stop_btn.props("disabled")
                dl_btn = button("Descargar seleccionadas", "yt-primary h-[38px]", lambda: start_download())

    # ---------- player tab ----------
    player_tab = ui.column().classes("flex-1 min-h-0 w-full gap-0 no-wrap")
    with player_tab:
        player = Player(get_outdir=lambda: outdir.value, pick_folder=pick_folder)
    player_tab.set_visibility(False)

    def show_tab(name: str) -> None:
        is_dl = name == "download"
        download_tab.set_visibility(is_dl)
        player_tab.set_visibility(not is_dl)
        tab_dl.classes(replace="on" if is_dl else "")
        tab_pl.classes(replace="" if is_dl else "on")
        if not is_dl:
            player.reload()

    def open_log() -> None:
        try:
            open_path(log_path)
        except OSError as e:
            ui.notify(f"No se pudo abrir el registro: {e}", type="warning")

    def toggle_log() -> None:
        tall = "h-80" in log_view.classes
        log_view.classes(remove="h-80" if tall else "h-32", add="h-32" if tall else "h-80")
        expand_btn.default_slot.children[0].text = "Ampliar" if tall else "Reducir"

    # ---------- links ----------
    def set_links(new: list[str]) -> None:
        links[:] = new
        counts = {k: sum(classify(u) == k for u in links) for k in TAGS}
        parts = [f"{counts['video']} video{'s' if counts['video'] > 1 else ''}" if counts["video"] else "",
                 f"{counts['playlist']} playlist" if counts["playlist"] else "",
                 f"{counts['mix']} Mix" if counts["mix"] else ""]
        detected.text = " · ".join(p for p in parts if p) or "vacío"
        link_list.refresh()

    def paste() -> None:
        # The webview blocks the JS clipboard API, so read it with the OS tool.
        text = read_clipboard()
        if text is None:
            ui.notify("No se pudo leer el portapapeles; pega el link en el campo (Ctrl/Cmd+V).", type="warning")
        else:
            add_links(text)

    def add_links(text: str) -> None:
        new = [u for u in re.split(r"[\s,]+", text or "") if re.match(r"https?://", u) and u not in links]
        if new:
            set_links(links + list(dict.fromkeys(new)))
        elif text and text.strip():
            ui.notify("No se encontró ninguna URL http/https.", type="warning")
        draft.value = ""

    # ---------- options ----------
    async def change_outdir() -> None:
        path = await pick_folder(outdir.value)
        if path:
            outdir.value = path

    def set_quality(q: str) -> None:
        nonlocal quality
        quality = q
        quality_picker.refresh()

    def set_format(f: str) -> None:
        nonlocal fmt
        fmt = f
        for k, b in f_btns.items():
            b.classes(replace="on" if k == f else "")
        set_quality(DEFAULT_QUALITY[f])

    def format_text() -> str:
        return f"MP3 {quality} kbps" if fmt == "audio" else f"MP4 {quality}"

    def on_mix(_=None) -> None:
        n = int(mix_limit.value)
        mix_value.text = str(n)
        mix_hint.text = f"Si pegas un Mix, se bajan hasta {n} canciones (máx. 50)."

    mix_limit.on_value_change(on_mix)
    on_mix()

    def update_counter() -> None:
        counter.text = f"{len(queue.selected())} de {len(queue.tracks)} seleccionadas"

    update_counter()

    # ---------- progress polling ----------
    def poll() -> None:
        if not busy or progress["track"] is None:
            return
        queue.set_state(progress["track"], "running", progress["pct"])
        set_total()

    def set_total() -> None:
        sel = [t.id for t in queue.selected()] or [t.id for t in queue.tracks]
        if not sel:
            return
        done = sum(100 if queue.state[i][0] in ("done", "skipped", "error") else queue.state[i][1] for i in sel)
        pct = done / len(sel)
        total_label.text = f"{pct:.0f}%"
        total_fill.style(f"width: {pct:.0f}%")

    ui.timer(0.2, poll)
    if not has_ffmpeg():
        log(FFMPEG_MISSING)

    def set_busy(value: bool) -> None:
        nonlocal busy
        busy = value
        for b in (dl_btn,):  # "Cargar" stays enabled: new tracks join the running batch
            if value:
                b.props("disabled")
            else:
                b.props(remove="disabled")
        if value:
            stop_btn.props(remove="disabled")
        else:
            stop_btn.props("disabled")

    # ---------- actions ----------
    async def load() -> None:
        if not links:
            ui.notify("Añade al menos una URL (http/https).", type="warning")
            return
        load_btn.props("disabled")
        if not busy:
            status.text = "Cargando…"
        limit = int(mix_limit.value)
        found, seen = [], set()
        try:
            for url in list(links):
                kind = classify(url)
                if kind == "mix":
                    kind = await ask_mix(limit)
                    if kind is None:
                        continue
                try:
                    result = await run.io_bound(list_tracks, url, kind, limit) or []
                except Exception as e:
                    log(f"❌ {url}: {e}", logging.ERROR)
                    continue
                log(f"→ {len(result)} pista(s) cargada(s) ({TAGS[kind]}).")
                for t in result:
                    if t.id not in seen:
                        seen.add(t.id)
                        found.append(t)
        finally:
            load_btn.props(remove="disabled")
        added = queue.add_tracks(found)
        log(f"Añadidas {added} pista(s) a la cola" + (" (se descargarán en este lote)." if busy else "."))
        if not busy:
            status.text = f"{len(queue.tracks)} pista(s) en la cola."
            set_total()

    def clear_queue() -> None:
        removed = queue.clear_finished(keep=progress["track"])
        log(f"Cola: {removed} pista(s) quitadas.")
        set_total()

    def retry(track_ids: list[str]) -> None:
        for tid in track_ids:
            if tid in queue.state:
                queue.checked[tid] = True
                queue.set_state(tid, "queued")
        queue.on_change()
        if not busy:
            asyncio.create_task(start_download())  # otherwise the running batch picks them up

    async def start_download() -> None:
        if busy:
            return
        if not queue.selected():
            ui.notify("No hay pistas seleccionadas.", type="warning")
            return
        if not has_ffmpeg():
            ui.notify(FFMPEG_MISSING, type="negative", multi_line=True)
            return
        if not (outdir.value or "").strip():
            ui.notify("Indica una carpeta de salida.", type="warning")
            return
        out = str(Path(outdir.value.strip()).expanduser())
        cancel.clear()
        for t in queue.selected():  # re-run anything selected that isn't finished
            if queue.state[t.id][0] in ("stopped", "error"):
                queue.set_state(t.id, "queued")
        set_busy(True)
        started = time.monotonic()
        results: dict[str, Result] = {}
        attempts: dict[str, int] = {}
        log(f"Iniciando descargas · {format_text()} · {out}")

        async def run_pending() -> None:
            while not cancel.is_set() and (t := queue.next_pending()) is not None:
                attempts[t.id] = attempts.get(t.id, 0) + 1
                done = sum(r.state != "error" for r in results.values())
                pending = sum(1 for x in queue.selected() if queue.state[x.id][0] == "queued")
                status.text = f"Descargando {done + 1} de {done + pending} · {format_text()}"
                log(f"↓ {t.title} (intento {attempts[t.id]})")
                progress.update(track=t.id, pct=0.0)

                def on_progress(pct: float, _msg: str) -> None:
                    progress["pct"] = min(pct, 99.0)

                try:
                    path = await run.io_bound(download, t, out, quality, t.playlist, on_progress, cancel, fmt)
                    size = Path(path).stat().st_size if path and Path(path).exists() else 0
                    results[t.id] = Result(t.title, "done" if path else "skipped", path, size)
                    queue.set_state(t.id, "done" if path else "skipped")
                    log(f"✅ {path}" if path else f"↷ Ya descargada: {t.title}")
                except Cancelled:
                    results[t.id] = Result(t.title, "stopped")
                    queue.set_state(t.id, "stopped")
                except Exception as e:
                    results[t.id] = Result(t.title, "error", error=str(e))
                    queue.errors[t.id] = short_error(str(e))
                    queue.set_state(t.id, "error")
                    log(f"❌ {t.title} (intento {attempts[t.id]}): {e}", logging.ERROR)
                finally:
                    progress["track"] = None
                set_total()

        await run_pending()
        # One automatic second pass for items that failed only once.
        again = [tid for tid, r in results.items() if r.state == "error" and attempts[tid] == 1]
        if again and not cancel.is_set():
            log(f"Reintentando {len(again)} pista(s) fallida(s) en {RETRY_DELAY} s…", logging.WARNING)
            status.text = f"Reintentando {len(again)} fallida(s) en {RETRY_DELAY} s…"
            for _ in range(RETRY_DELAY * 10):
                if cancel.is_set():
                    break
                await asyncio.sleep(0.1)
            if not cancel.is_set():
                for tid in again:
                    queue.set_state(tid, "queued")
                await run_pending()

        stopped = cancel.is_set()
        if stopped:
            log("Detenido.")
        status.text = "Detenido." if stopped else "Descarga finalizada."
        set_total()
        set_busy(False)
        summary = summarize(list(results.values()), time.monotonic() - started)
        log(f"Resumen: {summary.done} descargadas, {summary.skipped} ya estaban, {summary.failed} fallidas, "
            f"{summary.stopped} detenidas · {human_size(summary.total_bytes)} · {human_time(summary.elapsed)}")
        failed_ids = [tid for tid, r in results.items() if r.state == "error"]
        summary_dialog(
            summary, out,
            go_player=lambda: go_to_player(summary.first_new),
            open_folder=lambda: open_folder(out),
            retry_failed=(lambda: retry(failed_ids)) if failed_ids else None,
        )

    def go_to_player(first_new: str | None) -> None:
        show_tab("player")
        if first_new:
            player.play_path(Path(first_new))

    def open_folder(path: str) -> None:
        try:
            open_path(path)
        except OSError as e:
            ui.notify(f"No se pudo abrir la carpeta: {e}", type="warning")

def native_available() -> bool:
    if importlib.util.find_spec("webview") is None:
        return False
    if sys.platform.startswith("linux"):  # pywebview needs a GTK or Qt backend on Linux
        return any(importlib.util.find_spec(m) for m in ("gi", "qtpy"))
    return True


def run_app() -> None:
    browser = "--browser" in sys.argv or os.environ.get("YTMP3_BROWSER") == "1"
    if not browser and not native_available():
        print("Ventana nativa no disponible (falta pywebview o GTK/Qt); abriendo en el navegador.", file=sys.stderr)
        browser = True
    if browser:
        ui.run(reload=False, title="YouTube → MP3", favicon=theme.ICON_SVG)
    else:
        app.native.window_args["maximized"] = True  # create_window kwarg: Cocoa, WinForms, GTK and Qt honor it
        if sys.platform.startswith("linux"):
            # Window icon is honored only by the GTK/Qt backends; macOS/Windows use the bundle/exe icon.
            icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2] / "packaging")) / "icon.png"
            if icon.is_file():
                app.native.start_args["icon"] = str(icon)
            if getattr(sys, "frozen", False):
                app.native.start_args["gui"] = "qt"  # the Linux build bundles the Qt backend
        ui.run(native=True, reload=False, title="YouTube → MP3", window_size=(1100, 740),
               port=native.find_open_port(), favicon=theme.ICON_SVG)
