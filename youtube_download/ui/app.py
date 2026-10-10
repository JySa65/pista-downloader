"""NiceGUI desktop app: load URLs, pick tracks, download MP3."""
import os
import subprocess
import sys
import threading

from nicegui import app, run, ui

from youtube_download.core.downloader import Cancelled, download, list_tracks
from youtube_download.core.urls import classify

from .components import TrackList


async def ask_mix(limit: int) -> str | None:
    with ui.dialog() as dialog, ui.card():
        ui.label(f"¿Solo este video o el Mix completo (máx. {limit})?")
        with ui.row().classes("w-full justify-end"):
            ui.button("Solo este video", on_click=lambda: dialog.submit("video")).props("flat")
            ui.button("Mix completo", on_click=lambda: dialog.submit("mix"))
    choice = await dialog
    dialog.delete()
    return choice


@ui.page("/")
def index() -> None:
    dark = ui.dark_mode(True)
    # Written from worker threads, read by the timer on the event loop.
    progress = {"track": None, "pct": 0.0, "msg": ""}
    cancel = threading.Event()

    with ui.header().classes("items-center justify-between"):
        ui.label("YouTube → MP3").classes("text-xl font-medium")
        ui.switch("Modo oscuro").bind_value(dark)

    with ui.column().classes("w-full max-w-5xl mx-auto gap-4 p-4"):
        urls = ui.textarea("URLs (una por línea)").classes("w-full").props("outlined autogrow")

        with ui.row().classes("w-full items-center gap-4"):
            outdir = ui.input("Carpeta de salida", value=os.path.expanduser("~/Music")).classes("grow")
            if app.native.main_window is not None:
                async def pick_folder() -> None:
                    import webview
                    try:
                        res = await app.native.main_window.create_file_dialog(
                            webview.FileDialog.FOLDER, directory=outdir.value)
                    except Exception as e:
                        ui.notify(f"No se pudo abrir el selector: {e}", type="warning")
                        return
                    if res:
                        outdir.value = res[0]
                ui.button(icon="folder_open", on_click=pick_folder).props("flat round")
            kbps = ui.select(["128", "160", "192", "256", "320"], value="192", label="Calidad MP3").classes("w-32")
            mix_limit = ui.number("Límite Mix", value=50, min=1, max=500, precision=0).classes("w-28")

        with ui.row().classes("gap-2"):
            ui.button("Pegar", icon="content_paste", on_click=lambda: paste()).props("outline")
            load_btn = ui.button("Cargar", icon="search", on_click=lambda: load())
            dl_btn = ui.button("Descargar seleccionadas", icon="download", on_click=lambda: start_download())
            stop_btn = ui.button("Detener", icon="stop", color="negative", on_click=cancel.set)
            stop_btn.disable()

        with ui.row().classes("gap-2"):
            ui.button("Todas", on_click=lambda: tracks.select_all(True)).props("flat dense")
            ui.button("Ninguna", on_click=lambda: tracks.select_all(False)).props("flat dense")

        tracks = TrackList()

        overall = ui.linear_progress(value=0, show_value=False).props("size=10px rounded")
        status = ui.label("Listo.").classes("text-sm text-gray-500")
        log = ui.log(max_lines=500).classes("w-full h-40")

    def poll() -> None:
        bar = tracks.bars.get(progress["track"])
        if bar is not None:
            bar.value = progress["pct"] / 100
        if progress["msg"]:
            status.text = progress["msg"]

    ui.timer(0.2, poll)

    async def paste() -> None:
        text = await ui.clipboard.read()
        if not text and sys.platform == "darwin":  # webview may block the JS clipboard
            text = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        if text:
            urls.value = (urls.value.rstrip() + "\n" + text.strip()).strip()

    async def load() -> None:
        lines = [ln.strip() for ln in urls.value.splitlines() if ln.strip().startswith("http")]
        if not lines:
            ui.notify("Pega al menos una URL (http/https).", type="warning")
            return
        load_btn.props("loading")
        found, seen = [], set()
        try:
            for url in dict.fromkeys(lines):
                kind = classify(url)
                if kind == "mix":
                    kind = await ask_mix(int(mix_limit.value or 50))
                    if kind is None:
                        continue
                log.push(f"→ {url} ({kind})")
                try:
                    result = await run.io_bound(list_tracks, url, kind, int(mix_limit.value or 50)) or []
                except Exception as e:
                    log.push(f"❌ {url}: {e}")
                    continue
                for t in result:
                    if t.id not in seen:
                        seen.add(t.id)
                        found.append(t)
        finally:
            load_btn.props(remove="loading")
        tracks.set_tracks(found)
        status.text = f"{len(found)} pista(s) cargada(s)."

    async def start_download() -> None:
        selected = tracks.selected()
        if not selected:
            ui.notify("No hay pistas seleccionadas.", type="warning")
            return
        out = os.path.expanduser(outdir.value or "").strip()
        if not out:
            ui.notify("Indica una carpeta de salida.", type="warning")
            return
        cancel.clear()
        dl_btn.disable(); load_btn.disable(); stop_btn.enable()
        overall.value = 0
        log.push(f"▶ Descargando {len(selected)} pista(s) en {out}")

        for i, t in enumerate(selected, start=1):
            if cancel.is_set():
                break
            progress.update(track=t.id, pct=0.0, msg=f"[{i}/{len(selected)}] {t.title}")

            def on_progress(pct: float, msg: str, i=i, t=t) -> None:
                progress.update(pct=pct, msg=f"[{i}/{len(selected)}] {t.title} — {msg}")

            try:
                path = await run.io_bound(download, t, out, kbps.value, t.playlist, on_progress, cancel)
                log.push(f"✅ {path}" if path else f"↷ Ya descargada: {t.title}")
            except Cancelled:
                break
            except Exception as e:
                log.push(f"❌ {t.title}: {e}")
            overall.value = i / len(selected)

        stopped = cancel.is_set()
        if stopped:
            log.push("⏹ Detenido por el usuario.")
        progress.update(track=None, msg="Detenido." if stopped else "Descarga finalizada.")
        dl_btn.enable(); load_btn.enable(); stop_btn.disable()


def run_app() -> None:
    ui.run(native=True, reload=False, title="YouTube → MP3", window_size=(1100, 820), dark=True)
