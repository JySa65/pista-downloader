"""NiceGUI desktop app with two tabs: Descargar and Reproductor (layout: design v2)."""
import importlib.util
import logging
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from nicegui import app, background_tasks, core, run, ui

from pista import build_date, version
from pista.core.applog import setup_logging
from pista.core.batch import MAX_ATTEMPTS, human_size, human_time, short_error
from pista.core.loading import load_links, load_message
from pista.core.downloader import ARCHIVES, download, list_tracks, set_cookie_browser
from pista.core.settings import browsers_for, load_settings, save_settings
from pista.core.progress import batch_status
from pista.core.breaker import BREAKER
from pista.core.queue import BatchRunner, progress_total, stop_all
from pista.core.plan import plan_download
from pista.core.registry import REGISTRY, bootstrap_roots, existing_ids, recording
from yt_dlp.version import __version__ as yt_dlp_version

from pista.core.system import (
    LEGACY_APP_NAME, migrate_legacy, user_cache_dir, user_config_dir, default_outdir, find_deno, find_ffmpeg, has_ffmpeg, log_dir, open_path, read_clipboard, reveal_label, reveal_path,
)
from pista.core.links import open_url
from pista.core.report import REPO, current_os, issue_url
from pista.core.urls import classify, is_youtube

from . import theme
from .components import Queue, about_dialog, attrs, ask_mix, button, close_dialogs, confirm_dialog, log_class, log_file_dialog, summary_dialog
from .player import MiniPlayer, Player
from .security import HOST, harden, pick_port
from .session import SESSION as session

QUALITIES = {"audio": ["128", "160", "192", "256", "320"], "video": ["360p", "480p", "720p", "1080p", "4K"]}
DEFAULT_QUALITY = {"audio": "192", "video": "720p"}
FFMPEG_MISSING = ("No se encontró ffmpeg. Instálalo para descargar (macOS: brew install ffmpeg · "
                  "Windows: winget install ffmpeg · Linux: sudo apt install ffmpeg).")
FORMATS = {"audio": "Audio · MP3", "video": "Video · MP4"}
TAGS = {"video": "Video", "playlist": "Playlist", "mix": "Mix"}
FMT_NAME = {"audio": "MP3", "video": "MP4"}
RETRY_DELAY = 10  # seconds before the automatic second attempt of failed items
RECONNECT_TIMEOUT = 3600  # a locked or sleeping Mac drops the window's connection; keep the page alive meanwhile
logger = logging.getLogger("pista")
CONSENT = {"ok": False}  # «Confirmo que tengo derecho…»: remembered for this app session only
BOOTSTRAP = {"started": False}  # first-run library scan: once per app run


async def bootstrap_library(outdir: str) -> None:
    """First run only: fill the library registry from the songs already on disk, off the event loop."""
    if REGISTRY.ready or BOOTSTRAP["started"]:
        return
    BOOTSTRAP["started"] = True
    try:
        await run.io_bound(lambda: REGISTRY.bootstrap(bootstrap_roots(outdir)))
    except Exception:  # noqa: BLE001 — retried next start; the legacy archives keep counting meanwhile
        logger.warning("library registry bootstrap failed; using the legacy archives this run", exc_info=True)


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


# The batch outlives the page (a reload builds a new one), so its UI side effects go through the session
# to whichever page is open now, or nowhere.
def log(msg: str, level: int = logging.INFO) -> None:
    logger.log(level, msg)  # full line goes to the log file
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    session.log_lines.append(line)
    del session.log_lines[:-1000]
    session.to_page("show_log", line)


def set_status(text: str) -> None:
    session.status = text
    session.to_page("show_status", text)


def set_busy(value: bool) -> None:
    session.busy = value
    session.to_page("show_busy")


def safely(action, what: str) -> None:
    try:
        action()
    except OSError as e:
        ui.notify(f"No se pudo {what}: {e}", type="warning")


@ui.page("/")
def index() -> None:
    theme.apply()
    log_path = setup_logging(log_dir())
    settings_path = user_config_dir() / "settings.json"
    prefs = load_settings(settings_path)
    set_cookie_browser(prefs["browser"] if prefs["cookies"] else None)
    logger.info("v%s · yt-dlp %s · ffmpeg=%s · deno=%s", version(), yt_dlp_version, find_ffmpeg(), find_deno())
    dark = False
    log_open = False
    # Batch state lives in the session (a reload must show it again); these names alias its containers.
    links, link_errors, log_lines, last_summary = (
        session.links, session.link_errors, session.log_lines, session.last_summary)
    client = ui.context.client  # background tasks have no slot; UI they create must enter the page explicitly

    # Defined before the queue: a reloaded page paints existing rows (their meta shows the format) at once.
    def format_text() -> str:
        return f"MP3 {session.quality} kbps" if session.fmt == "audio" else f"MP4 {session.quality}"

    def fmt_short() -> str:
        return f"MP3 {session.quality}" if session.fmt == "audio" else f"MP4 {session.quality}"

    def show_log(line: str) -> None:
        last_log.text = line
        attrs(last_log, title=line)
        if log_open:
            with log_box:
                ui.label(line).classes(log_class(line))
            log_box.run_method("scrollTo", 0, 10 ** 9)

    @ui.refreshable
    def link_list() -> None:
        if not links:
            with ui.element("div").classes("flex-1 flex items-center justify-center text-center px-4"):
                ui.label("Los links añadidos aparecen aquí, uno por fila.").classes("text-xs yt-subtle")
            return
        for n, url in enumerate(links, start=1):
            kind = classify(url)
            error = link_errors.get(url)
            with attrs(ui.element("div").classes("yt-linkrow w-full" + (" err" if error else "")), title=url):
                ui.label(str(n)).classes("mono text-[11px] yt-subtle")
                ui.label(TAGS[kind]).classes("yt-tag" + ("" if kind == "video" else " list"))
                ui.label(re.sub(r"^https?://(www\.)?", "", url)).classes("mono text-[11px] yt-text2 truncate")
                button("×", "yt-ghost w-5 h-5 text-sm p-0", lambda u=url: set_links([x for x in links if x != u]))
                if error:
                    with ui.element("div").classes("yt-linkerr"):
                        attrs(ui.label(error).classes("yt-reason"), title=error)
                        button("↻ Reintentar", "yt-a text-xs shrink-0", lambda u=url: load([u]))

    @ui.refreshable
    def quality_picker() -> None:
        ui.label("Calidad (kbps)" if session.fmt == "audio" else "Resolución").classes("yt-label")
        with ui.element("div").classes("yt-seg small w-full"):
            for q in QUALITIES[session.fmt]:
                button(q, "on" if q == session.quality else "", lambda q=q: set_quality(q))

    # ---------- title bar ----------
    with ui.element("div").classes("yt-bar"):
        with ui.row().classes("items-center gap-2 no-wrap"):
            ui.html(theme.ICON_SVG, sanitize=False).classes("w-5 h-5 flex")
            ui.label("Pista").classes("text-[13px] font-semibold yt-text2")
            ui.label(f"v{version()}").classes("mono text-[11px] yt-subtle") \
                .props('title="Licencia GPLv3 (GNU General Public License v3.0 o posterior)"')
        with ui.element("div").classes("yt-seg"):
            tab_dl = button("Descargar", "on", lambda: show_tab("download"))
            tab_pl = button("Reproductor", "", lambda: show_tab("player"))
        with ui.row().classes("justify-end gap-1.5 no-wrap"):
            button("Acerca de", "yt-btn h-7 text-xs px-2.5 yt-muted", lambda: open_about())
            with ui.element("button").classes("yt-btn h-7 text-xs px-2.5 yt-muted").on("click", lambda: toggle_theme()):
                theme_label = ui.label("Modo oscuro")

    def open_about() -> None:
        about_dialog(version(), build_date(), theme.ICON_SVG, REPO)

    def toggle_theme() -> None:
        nonlocal dark
        dark = not dark
        theme.set_theme(dark)
        theme_label.text = "Modo claro" if dark else "Modo oscuro"

    # ---------- download tab ----------
    download_tab = ui.element("div").classes("flex-1 min-h-0 w-full grid") \
        .style("grid-template-columns: 340px minmax(0, 1fr); grid-template-rows: minmax(0, 1fr)")
    with download_tab:
        with ui.column().classes("yt-panel yt-line-r px-[22px] py-[18px] gap-4 min-h-0 overflow-auto no-wrap"):
            with ui.column().classes("w-full gap-2"):
                with ui.row().classes("w-full justify-between items-baseline"):
                    ui.label("Links").classes("yt-label")
                    detected = ui.label("vacío").classes("text-[11px] yt-subtle")
                with ui.row().classes("w-full gap-1.5 no-wrap items-stretch"):
                    # Multi-line: Enter is a new line; Ctrl/⌘+Enter or «+ Añadir» adds.
                    draft = ui.textarea(placeholder="Pega o escribe links, uno por línea") \
                        .props("borderless dense rows=4").classes("yt-area flex-1 min-w-0")
                    draft.on("keydown.enter.ctrl.prevent", lambda: add_links(draft.value))
                    draft.on("keydown.enter.meta.prevent", lambda: add_links(draft.value))
                    with ui.column().classes("w-[84px] shrink-0 gap-1.5"):
                        button("Pegar", "yt-btn flex-1 text-xs w-full", lambda: paste()) \
                            .props('title="Añade a la lista los links del portapapeles"')
                        button("+ Añadir", "yt-btn flex-1 text-xs w-full", lambda: add_links(draft.value)) \
                            .props('title="Añadir lo escrito (Ctrl/⌘ + Enter)"')
                with ui.column().classes("yt-box w-full h-[100px] shrink-0 overflow-auto p-[5px] gap-1 no-wrap"):
                    link_list()
                with ui.element("div").classes("grid gap-1.5 w-full").style("grid-template-columns: 1fr 2fr"):
                    button("Limpiar", "yt-btn h-[34px]", lambda: set_links([]))
                    with ui.element("button").classes("yt-primary h-[34px]").on("click", lambda: load()) as load_btn:
                        load_label = ui.label("Cargar")
                running_notice = ui.label("Descarga en curso. Lo que cargues se añade al final de la cola.") \
                    .classes("yt-notice w-full")
                running_notice.set_visibility(False)

            ui.element("div").classes("yt-sep")

            with ui.column().classes("w-full gap-[14px]"):
                with ui.column().classes("w-full gap-1.5"):
                    ui.label("Carpeta de salida").classes("yt-label")
                    with ui.row().classes("w-full gap-1.5 no-wrap"):
                        outdir = ui.input(value=session.outdir or str(default_outdir())).props("borderless dense") \
                            .classes("yt-field flex-1 min-w-0 h-[34px]")
                        button("Cambiar", "yt-btn text-xs h-[34px]", lambda: change_outdir())
                with ui.column().classes("w-full gap-1.5"):
                    ui.label("Formato").classes("yt-label")
                    with ui.element("div").classes("yt-seg two w-full"):
                        f_btns = {f: button(label, "on" if f == session.fmt else "", lambda f=f: set_format(f))
                                  for f, label in FORMATS.items()}
                with ui.column().classes("w-full gap-1.5"):
                    quality_picker()
                with ui.column().classes("w-full gap-1.5"):
                    with ui.row().classes("w-full justify-between"):
                        ui.label("Canciones por Mix").classes("yt-label")
                        mix_value = ui.label("50 / 50").classes("mono text-xs yt-text2")
                    mix_limit = ui.slider(min=1, max=50, value=50).props("dense color=primary")
                with ui.column().classes("w-full gap-1.5"):
                    # Optional: use the browser's YouTube session (yt-dlp cookiesfrombrowser). Off by default.
                    cookies_switch = ui.switch("Usar la sesión de YouTube de mi navegador", value=prefs["cookies"]) \
                        .props("dense color=primary").classes("yt-switch text-[13px]")
                    cookies_browser = ui.select(dict(browsers_for()), value=prefs["browser"]) \
                        .props("borderless dense options-dense").classes("yt-field w-full h-[34px]")
                    cookies_browser.set_visibility(prefs["cookies"])
                    ui.label("Ayuda cuando YouTube pide verificar que no eres un robot. Pista lee las cookies de "
                             "YouTube de ese navegador solo para descargar; no las guarda ni las envía a otro sitio.") \
                        .classes("text-xs yt-subtle leading-normal")

            ui.element("div").classes("flex-1")
            with ui.element("div").classes("yt-footnote"):
                ui.label("Descarga solo contenido del que tengas derechos. Tú eres responsable de su uso.")
                button("Aviso legal", "yt-a", lambda: open_about())

        with ui.column().classes("min-h-0 gap-0 no-wrap"):
            with ui.row().classes("w-full items-center justify-between px-6 pt-[18px] pb-3 shrink-0 no-wrap"):
                # If space runs out, the title/counter shrink (ellipsis); the action buttons never do.
                with ui.row().classes("items-baseline gap-2.5 no-wrap min-w-0"):
                    ui.label("Cola").classes("text-lg font-semibold shrink-0")
                    counter = ui.label().classes("text-[13px] yt-muted truncate min-w-0")
                with ui.row().classes("gap-1 items-center no-wrap shrink-0"):
                    button("Todas", "yt-link", lambda: queue.select_all(True)).props(
                        'title="Marca las pistas visibles (las que coinciden con la búsqueda)"')
                    button("Ninguna", "yt-link", lambda: queue.select_all(False)).props(
                        'title="Desmarca las pistas visibles (las que coinciden con la búsqueda)"')
                    ui.element("div").classes("yt-divider")
                    button("Limpiar cola", "yt-btn yt-sm", lambda: clear_queue()).props(
                        'title="Quita las terminadas, las fallidas y las desmarcadas"')
                    ui.input(placeholder="Buscar", value=session.queue.query, on_change=lambda e: queue.search(e.value)) \
                        .props("borderless dense").classes("yt-field w-[180px] h-8 ml-2")
            with ui.element("div").classes("yt-qhead shrink-0"):
                for h, cls in (("", ""), ("", ""), ("Título", ""), ("Estado", "text-center"), ("", ""), ("", "")):
                    ui.label(h).classes(cls)
            with ui.column().classes("flex-1 min-h-0 overflow-auto px-4 pb-2 gap-1 w-full no-wrap"):
                queue = Queue(on_change=lambda: update_counter(), fmt_label=lambda: fmt_short(), model=session.queue)
                queue.on_retry = lambda track_id: retry([track_id])
                queue.on_remove = lambda track_id: remove_item(track_id)

            # Registro: last line; «Expandir» shows full lines; «Abrir registro» shows the whole .log file.
            with ui.column().classes("yt-panel yt-line-t w-full gap-0 shrink-0 no-wrap"):
                with ui.row().classes("w-full items-center gap-2.5 py-[7px] pl-6 pr-4 no-wrap"):
                    ui.label("Registro").classes("yt-label")
                    last_log = ui.label(log_lines[-1] if log_lines else "Listo.").classes("yt-logline flex-1 min-w-0")
                    with ui.element("button").classes("yt-link").on("click", lambda: toggle_log()):
                        log_toggle = ui.label("Expandir")
                    button("Reportar un problema", "yt-link", lambda: open_url(issue_url(version(), current_os()))) \
                        .props('title="Abre un reporte en GitHub con la versión y el sistema ya completados"')
                    button("Abrir registro", "yt-btn yt-sm", lambda: log_file_dialog(
                        log_path, reveal_label(), lambda: safely(lambda: reveal_path(log_path), "mostrar el archivo")))
                log_box = ui.element("div").classes("yt-logbox h-[170px] mx-4 mb-2.5") \
                    .style("width: calc(100% - 32px)")
                log_box.set_visibility(False)

            # Global YouTube cooldown (429 / bot check): everything pauses; items stay queued.
            with ui.row().classes("yt-cooldown w-full items-center gap-3 px-6 py-2 no-wrap shrink-0") as cooldown_bar:
                cooldown_text = ui.label().classes("flex-1 min-w-0 text-[13px]")
                button("Reanudar ahora", "yt-btn yt-sm", lambda: (BREAKER.resume(), poll()))
                button("Detener", "yt-danger yt-sm", lambda: stop())
            cooldown_bar.set_visibility(False)
            mini_slot = ui.column().classes("w-full gap-0 shrink-0")  # now-playing bar, filled once the player exists
            with ui.row().classes("yt-panel yt-line-t w-full items-center gap-3 px-6 py-3 no-wrap shrink-0"):
                with ui.column().classes("flex-1 min-w-0 gap-1.5"):
                    with ui.row().classes("w-full justify-between text-xs yt-muted no-wrap gap-3"):
                        status = ui.label(session.status).classes("truncate min-w-0")
                        total_label = ui.label("0%").classes("mono")
                    with ui.element("div").classes("yt-track big w-full"):
                        total_fill = ui.element("div").classes("yt-fill")
                stop_btn = button("Detener", "yt-danger", lambda: stop())
                stop_btn.set_visibility(False)
                summary_btn = button("Ver resumen", "yt-btn h-[38px] px-3.5", lambda: summary_dialog(**last_summary))
                summary_btn.set_visibility(False)
                dl_btn = button("Descargar seleccionadas", "yt-primary h-[38px]", lambda: confirm_and_start())

    # ---------- player tab ----------
    player_tab = ui.column().classes("flex-1 min-h-0 w-full gap-0 no-wrap")
    with player_tab:
        player = Player(get_outdir=lambda: outdir.value, pick_folder=pick_folder)
    player_tab.set_visibility(False)
    with mini_slot:
        MiniPlayer(player, on_open=lambda: show_tab("player"))

    def show_tab(name: str) -> None:
        is_dl = name == "download"
        download_tab.set_visibility(is_dl)
        player_tab.set_visibility(not is_dl)
        tab_dl.classes(replace="on" if is_dl else "")
        tab_pl.classes(replace="" if is_dl else "on")
        if not is_dl:
            player.reload()

    def toggle_log() -> None:
        nonlocal log_open
        log_open = not log_open
        log_box.clear()
        if log_open:
            with log_box:
                for line in log_lines:
                    ui.label(line).classes(log_class(line))
            log_box.run_method("scrollTo", 0, 10 ** 9)
        log_box.set_visibility(log_open)
        log_toggle.text = "Contraer" if log_open else "Expandir"

    # ---------- links ----------
    def set_links(new: list[str]) -> None:
        links[:] = new
        for gone in set(link_errors) - set(links):
            link_errors.pop(gone)
        counts = {k: sum(classify(u) == k for u in links) for k in TAGS}
        parts = [f"{counts['video']} video{'s' if counts['video'] > 1 else ''}" if counts["video"] else "",
                 f"{counts['playlist']} playlist" if counts["playlist"] else "",
                 f"{counts['mix']} Mix" if counts["mix"] else ""]
        detected.text = " · ".join(p for p in parts if p) or "vacío"
        link_list.refresh()

    def paste() -> None:
        # The webview blocks the JS clipboard API, so read it with the OS tool (no console window).
        text = read_clipboard()
        if text is None:
            ui.notify("No se pudo leer el portapapeles; pega en el cuadro con Ctrl/⌘+V.", type="warning")
        elif not add_urls(text):
            ui.notify("El portapapeles no tiene links http/https.", type="warning")

    def add_urls(text: str) -> int:
        found = [u for u in re.split(r"[\s,]+", text or "") if re.match(r"https?://", u)]
        rejected = [u for u in found if not is_youtube(u)]
        if rejected:
            ui.notify(f"Solo se aceptan links de YouTube (youtube.com, youtu.be). Se ignoraron {len(rejected)}.",
                      type="warning")
        new = list(dict.fromkeys(u for u in found if is_youtube(u) and u not in links))
        dupes = {u for u in found if u in links}
        if dupes:
            ui.notify("Ese link ya está en la lista." if len(dupes) == 1 else f"{len(dupes)} links ya estaban en la lista.",
                      type="info")
        if new:
            set_links(links + new)
        return len(new) + len(rejected) + len(dupes)  # rejected and duplicate links already got their own message

    def add_links(text: str) -> None:
        if not add_urls(text) and text and text.strip():
            ui.notify("No se encontró ningún link http/https.", type="warning")
        draft.value = ""

    # ---------- options ----------
    async def change_outdir() -> None:
        path = await pick_folder(outdir.value)
        if path:
            outdir.value = path

    def set_quality(q: str) -> None:
        session.quality = q
        quality_picker.refresh()
        for tid in queue.rows:  # row meta shows the format
            queue.set_state(tid, *queue.state[tid])

    def set_format(f: str) -> None:
        if session.busy and f != session.fmt:
            ui.notify("Cambia el formato cuando termine la descarga en curso.", type="warning")
            return
        session.fmt = f
        queue.set_format(f)  # «Listo» is per format: re-evaluate every row
        for k, b in f_btns.items():
            b.classes(replace="on" if k == f else "")
        set_quality(DEFAULT_QUALITY[f])

    def on_cookies_change() -> None:
        prefs.update(cookies=bool(cookies_switch.value), browser=cookies_browser.value)
        save_settings(settings_path, prefs)  # only the choice, never cookies
        set_cookie_browser(prefs["browser"] if prefs["cookies"] else None)
        cookies_browser.set_visibility(prefs["cookies"])
        log("Sesión del navegador: " + (f"activada ({prefs['browser']})" if prefs["cookies"] else "desactivada"))

    cookies_switch.on_value_change(on_cookies_change)
    cookies_browser.on_value_change(on_cookies_change)

    outdir.on_value_change(lambda: setattr(session, "outdir", outdir.value))
    background_tasks.create(bootstrap_library(outdir.value or ""))
    mix_limit.on_value_change(lambda: setattr(mix_value, "text", f"{int(mix_limit.value)} / 50"))

    def update_counter() -> None:
        counter.text = f"{len(queue.selected())} de {len(queue.tracks)} seleccionadas"

    update_counter()

    # ---------- progress polling ----------
    def poll() -> None:
        cooling = BREAKER.is_open()
        cooldown_bar.set_visibility(cooling)
        if cooling:
            cooldown_text.text = BREAKER.message()
            if session.runner is not None:
                set_status(BREAKER.message())
        runner = session.runner
        if runner is None or runner.current is None:
            return
        # pct/phase are written by the download thread; only this timer touches the UI.
        queue.set_state(runner.current, "running", runner.pct, phase=runner.phase)
        set_status(batch_status(runner.phase, *runner.position, format_text()))
        set_total()

    def set_total() -> None:
        pct = progress_total(session.queue)  # download/conversion weighted per item
        total_label.text = f"{pct:.0f}%"
        total_fill.style(f"width: {pct:.0f}%")

    ui.timer(0.2, poll)

    def show_busy() -> None:
        value = session.busy
        stop_btn.set_visibility(value)  # «Descargar seleccionadas» stays enabled: it appends to the batch
        running_notice.set_visibility(value)
        load_label.text = "Cargar a la cola" if value else "Cargar"
        summary_btn.set_visibility(not value and bool(last_summary))

    # ---------- actions ----------
    async def load(only: list[str] | None = None) -> None:
        urls = list(only or links)
        if not urls:
            ui.notify("Añade al menos un link (http/https).", type="warning")
            return
        load_btn.props("disabled")
        try:
            outcomes = await load_links(urls, list_tracks, limit=int(mix_limit.value), choose_mix=lambda u: ask_mix(int(mix_limit.value)),
                                        run_io=run.io_bound)
        finally:
            load_btn.props(remove="disabled")
        found = []
        for o in outcomes:
            if o.error:
                link_errors[o.url] = o.error
                log(f"✗ {o.url}: {o.raw or o.error}", logging.ERROR)
            elif not o.skipped:
                link_errors.pop(o.url, None)
                log(f"→ {o.url} ({TAGS[o.kind].lower()}, {len(o.tracks)} pistas)")
                found += o.tracks
        dups = [t.id for t in found if t.id in queue.state]
        for tid in dups:  # re-added: make sure it's selected if it still has to be downloaded in this format
            if queue.state[tid][0] not in ("done", "skipped"):
                queue.checked[tid] = True
        dup_pending = sum(queue.state[tid][0] in ("queued", "stopped", "error") for tid in set(dups))
        if dups:
            queue._changed()
        added = queue.add_tracks(found, new=session.busy)
        loaded = {o.url for o in outcomes if o.tracks}
        set_links([u for u in links if u not in loaded])  # failed or cancelled links stay, with their reason
        text, kind = load_message(outcomes, added, dup_pending, FMT_NAME[session.fmt])
        log(text, logging.ERROR if kind == "error" else logging.WARNING if kind == "warning" else logging.INFO)
        ui.notify(text, type={"ok": "positive", "info": "info", "warning": "warning", "error": "negative"}[kind],
                  multi_line=True)
        if not session.busy:
            set_status(text if kind in ("error", "warning") else f"{len(queue.tracks)} pista(s) en la cola.")
            set_total()

    def stop() -> None:
        if session.runner is not None:
            session.runner.stop()
        close_dialogs()  # preview, log file and Mix question

    def remove_item(track_id: str) -> None:
        if session.runner is not None:
            session.runner.cancel_item(track_id)  # the worker drops it when the download aborts
        track = queue.remove(track_id)
        if track:
            log(f"− {track.title} — quitada de la cola")
        set_total()

    def clear_queue() -> None:
        removed = queue.clear_finished(keep=session.runner.current if session.runner else None)
        log(f"Cola limpiada: {removed} quitadas.")
        set_total()

    def in_page(action) -> None:
        with client.layout:
            action()

    def retry(track_ids: list[str]) -> None:
        for tid in track_ids:
            if tid not in queue.state:
                continue
            if queue.fails.get(tid, 0) >= MAX_ATTEMPTS:
                queue.fails[tid] = MAX_ATTEMPTS - 1  # a manual retry always gets one more attempt
            queue.checked[tid] = True
            queue.set_state(tid, "queued")
            title = next(t.title for t in queue.tracks if t.id == tid)
            log(f"↻ {title} — reintentando ({queue.fails.get(tid, 0) + 1}/{MAX_ATTEMPTS})", logging.WARNING)
        queue.on_change()
        if not session.busy:
            background_tasks.create(start_download())  # otherwise the running batch picks them up

    def make_plan(consent: bool = False, include_existing: bool = False):
        out = Path((outdir.value or "").strip()).expanduser()
        items = [(t, queue.state[t.id][0], bool(queue.checked.get(t.id))) for t in queue.tracks]
        existing = existing_ids(REGISTRY, session.fmt, [t.id for t in queue.tracks], out / ARCHIVES[session.fmt])
        return plan_download(items, session.fmt, session.quality, existing, session.busy, consent, include_existing)

    async def confirm_and_start() -> None:
        if not queue.tracks:
            ui.notify("La cola está vacía.", type="warning")
            return
        if not has_ffmpeg():
            ui.notify(FFMPEG_MISSING, type="negative", multi_line=True)
            return
        if not (outdir.value or "").strip():
            ui.notify("Indica una carpeta de salida.", type="warning")
            return
        plan = await confirm_dialog(make_plan, lambda: outdir.value, change_outdir, CONSENT)
        if plan is None:
            return
        for tid in plan.skip:  # already in the library in this format: no network needed
            queue.mark_done(tid, session.fmt, None, 0)
        for tid in plan.pending:
            if tid in queue.state and queue.state[tid][0] == "stopped":
                queue.set_state(tid, "queued")
        if session.busy:
            log(f"{plan.count} pista(s) añadidas a la descarga en curso.")
        else:
            await start_download()

    async def start_download() -> None:
        # Only one batch across pages: a second page appends to it (see confirm_and_start), never runs another.
        if not has_ffmpeg() or not (outdir.value or "").strip() or not session.begin():
            return
        out = ""

        def make_runner() -> BatchRunner:  # runs inside run_batch's guard: a failure here releases the slot too
            nonlocal out
            out = str(Path(outdir.value.strip()).expanduser())
            # Runs to the end even if this page is reloaded meanwhile: from here on, UI goes through the session.
            return BatchRunner(
                session.queue, recording(download, REGISTRY), out=out, quality=session.quality, fmt=session.fmt, run_io=run.io_bound,
                retry_delay=RETRY_DELAY, log=log, status=set_status, fmt_text=format_text(),
                on_progress=lambda: session.to_page("set_total"))

        def failed(e: Exception) -> None:
            logger.exception("batch failed")
            session.to_page("notify", f"La descarga se interrumpió por un error: {short_error(str(e))}", "negative")

        runner, summary = await session.run_batch(make_runner, set_busy, failed)
        if summary is None:
            return
        try:
            results = runner.results
            session.to_page("set_total")
            log(f"Resumen: {summary.done} descargadas, {summary.skipped} ya estaban, {summary.failed} fallidas, "
                f"{summary.stopped} detenidas · {human_size(summary.total_bytes)} · {human_time(summary.elapsed)}")
            failed_ids = [tid for tid, r in results.items() if r.state == "error"]
            last_summary.clear()
            last_summary.update(
                summary=summary, folder=out, processed=len(results),
                go_player=lambda: session.to_page("go_to_player", summary.first_new),
                open_folder=lambda: safely(lambda: open_path(out), "abrir la carpeta"),
                retry_failed=(lambda: session.to_page("retry", failed_ids)) if failed_ids else None,
            )
        finally:
            set_busy(False)  # the slot is app-wide: a failure here must not block every later batch
        session.to_page("show_summary")  # no page open: «Ver resumen» shows it later

    def go_to_player(first_new: str | None) -> None:
        show_tab("player")
        if first_new:
            ui.timer(0, lambda: player.play_path(Path(first_new)), once=True)

    # Attach last: from now on the session's updates (log, status, progress, rows, summary) land here.
    view = SimpleNamespace(
        queue=queue, show_log=show_log, show_status=lambda text: setattr(status, "text", text),
        set_total=set_total, show_busy=show_busy, retry=retry, go_to_player=go_to_player,
        notify=lambda text, kind: in_page(lambda: ui.notify(text, type=kind)),
        show_summary=lambda: in_page(lambda: summary_dialog(**last_summary)))
    session.attach(view)
    client.on_delete(lambda: session.detach(view))
    set_links(list(links))
    set_total()
    show_busy()
    if not has_ffmpeg() and not session.ffmpeg_warned:  # once per run: reloads would repeat it in the log
        session.ffmpeg_warned = True
        log(FFMPEG_MISSING, logging.WARNING)


def native_available() -> bool:
    if importlib.util.find_spec("webview") is None:
        return False
    if sys.platform.startswith("linux"):  # pywebview needs a GTK or Qt backend on Linux
        return any(importlib.util.find_spec(m) for m in ("gi", "qtpy"))
    return True


def run_app() -> None:
    app.on_shutdown(stop_all)  # closing the window stops downloads (yt-dlp keeps .part files resumable)
    migrate_legacy(user_cache_dir(app=LEGACY_APP_NAME), user_cache_dir())  # <= 0.2.x logs and preview cache
    # YTMP3_BROWSER: pre-rename name of the same switch, still honored.
    browser = "--browser" in sys.argv or "1" in (os.environ.get("PISTA_BROWSER"), os.environ.get("YTMP3_BROWSER"))
    if not browser and not native_available():
        print("Ventana nativa no disponible (falta pywebview o GTK/Qt); abriendo en el navegador.", file=sys.stderr)
        browser = True
    port = pick_port()
    harden(app, core.sio, port)  # loopback Host only, socket.io only from the app's own origin
    if browser:
        # `show` opens the default browser; the server still only listens on 127.0.0.1.
        ui.run(reload=False, title="Pista", favicon=theme.ICON_SVG, host=HOST, port=port,
               reconnect_timeout=RECONNECT_TIMEOUT, show=os.environ.get("PISTA_NO_BROWSER") != "1")
    else:
        app.native.window_args["maximized"] = True  # create_window kwarg: Cocoa, WinForms, GTK and Qt honor it
        if sys.platform.startswith("linux"):
            # Window icon is honored only by the GTK/Qt backends; macOS/Windows use the bundle/exe icon.
            icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2] / "packaging")) / "icon.png"
            if icon.is_file():
                app.native.start_args["icon"] = str(icon)
            if getattr(sys, "frozen", False):
                app.native.start_args["gui"] = "qt"  # the Linux build bundles the Qt backend
        ui.run(native=True, reload=False, title="Pista", window_size=(1100, 740),
               host=HOST, port=port, reconnect_timeout=RECONNECT_TIMEOUT, favicon=theme.ICON_SVG)
