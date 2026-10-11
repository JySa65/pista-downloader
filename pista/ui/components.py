"""Download queue, preview dialog and Mix dialog."""
from collections.abc import Callable
from pathlib import Path

from nicegui import app, run, ui

from pista.core.batch import Summary, human_size, human_time, status_label
from pista.core.downloader import preview_clip
from pista.core.links import is_release_url, is_video_url, open_url
from pista.core.models import Track
from pista.core.plan import Plan
from pista.core.queue import QueueModel
from pista.core.system import writable_dir
from pista.core.updates import fetch_latest, update_status

PREVIEW_DIR = writable_dir("previews")  # falls back to a temp folder if the cache can't be written
app.add_media_files("/media", PREVIEW_DIR)


def hhmmss(seconds: float | None) -> str:
    if not seconds:
        return "?"
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def attrs(el: ui.element, **values: str | bool) -> ui.element:
    """Set element props one key at a time.

    Never pass data through `.props("k=v …")`: NiceGUI parses that string, so a quote inside a title,
    URL or path would inject extra props (e.g. `onerror`, `innerHTML`) into the app window.
    Keys use `_` for `-` (e.g. aria_disabled).
    """
    for key, value in values.items():
        el.props[key.replace("_", "-")] = value
    return el


def button(text: str, cls: str, on_click: Callable | None = None, stop: bool = False) -> ui.element:
    """Plain <button> styled by theme classes; stop=True keeps the click from reaching the row."""
    b = ui.element("button").classes(cls)
    with b:
        ui.label(text)
    if on_click:
        b.on("click.stop" if stop else "click", on_click)
    return b


def closable(dialog: ui.dialog) -> ui.dialog:
    """Register a dialog that «Detener» should close (Mix question, preview, log file)."""
    dialogs = getattr(ui.context.client, "yt_closable", None)
    if dialogs is None:
        dialogs = ui.context.client.yt_closable = set()
    dialogs.add(dialog)
    dialog.on("hide", lambda: dialogs.discard(dialog))
    return dialog


def close_dialogs() -> int:
    dialogs = list(getattr(ui.context.client, "yt_closable", ()))
    for d in dialogs:
        d.close()
    return len(dialogs)


async def ask_mix(limit: int) -> str | None:
    with closable(ui.dialog()) as dialog, ui.card().classes("yt-modal w-[420px] max-h-[90vh] overflow-auto p-[22px] gap-[14px]"):
        ui.label("Hay un Mix en los links").classes("text-[15px] font-semibold")
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

    with closable(ui.dialog()) as dialog, ui.card().classes("yt-modal w-[780px] max-h-[90vh] p-0 gap-0 overflow-auto no-wrap"):
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
                attrs(ui.element("iframe"), src=embed, allow="autoplay; encrypted-media; picture-in-picture",
                      allowfullscreen=True).classes("w-full h-full border-0")
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
            button("Abrir en el navegador", "yt-btn h-8 text-xs",
                   lambda: open_url(track.url, is_video_url) or ui.notify("Link no válido.", type="warning"))
        show_embed()
    dialog.on("hide", dialog.delete)
    dialog.open()


PILL = {  # state -> (pill class, bar class)
    "queued": ("", ""), "running": ("run", ""), "done": ("ok", "ok"), "skipped": ("line", "ok"),
    "error": ("err", "err"), "stopped": ("line", ""),
}


class Queue(QueueModel):
    """Checkable track rows. Every row has the same fixed height and columns, whatever its state.

    State lives in QueueModel (pista/core/queue.py); this class only paints it.
    """

    def __init__(self, on_change: Callable[[], None], fmt_label: Callable[[], str]) -> None:
        super().__init__()
        self.rows: dict[str, dict] = {}
        self.on_change = on_change
        self.fmt_label = fmt_label
        self.on_retry: Callable[[str], None] = lambda track_id: None
        self.on_remove: Callable[[str], None] = lambda track_id: None
        self.render()

    def _changed(self) -> None:
        self.render.refresh()
        self.on_change()

    def _state_changed(self, track_id: str) -> None:
        self._paint(track_id)

    def meta(self, t: Track) -> str:
        size = self.sizes.get(t.id)
        return f"{t.channel} · {hhmmss(t.duration)} · {self.fmt_label()}" + (f" · {human_size(size)}" if size else "")

    def _paint(self, track_id: str) -> None:
        row = self.rows.get(track_id)
        if row is None or track_id not in self.state:
            return
        state, pct = self.state[track_id]
        pill_cls, bar_cls = PILL[state]
        if state == "queued" and self.fails.get(track_id):
            pill_cls = "amb"
        width = 100 if state in ("done", "skipped") else pct
        row["fill"].classes(replace=f"yt-fill {bar_cls}").style(f"width: {width:.0f}%")
        row["pill"].classes(replace=f"yt-pill {pill_cls}")
        row["pill_text"].text = status_label(state, pct, self.fails.get(track_id, 0))
        error = state == "error"
        row["el"].classes(replace="yt-row" + (" err" if error else "") + ("" if self.checked.get(track_id) else " off"))
        row["reason"].text = self.errors.get(track_id, "") if error else ""
        row["reason"].set_visibility(error)
        row["bar"].set_visibility(not error and state != "skipped")
        row["meta"].text = self.meta(row["track"])
        if row["error_shown"] != error:
            self._action(row, error)

    def _action(self, row: dict, error: bool) -> None:
        row["error_shown"] = error
        row["action"].clear()
        track = row["track"]
        with row["action"]:
            if error:
                button("↻ Reintentar", "yt-retry", lambda: self.on_retry(track.id), stop=True)
            else:
                button("▶ Ver", "yt-link w-full h-7", lambda: open_preview(track), stop=True)

    @ui.refreshable_method
    def render(self) -> None:
        self.rows = {}
        if not self.tracks:
            with ui.element("div").classes("h-full w-full flex items-center justify-center"):
                ui.label("Pega uno o más links y pulsa «Cargar».").classes("text-[13px] yt-subtle")
            return
        for t in self.tracks:
            on = self.checked[t.id]
            el = ui.element("div").classes("yt-row").on("click", lambda t=t: self.toggle(t.id))
            with el:
                with ui.element("div").classes("yt-check on" if on else "yt-check"):
                    ui.label("✓" if on else "")
                if t.thumbnail:
                    attrs(ui.element("img"), src=t.thumbnail, loading="lazy", alt="").classes("yt-thumb dim")
                else:
                    ui.element("div").classes("yt-thumb dim")
                with ui.element("div").classes("yt-text dim"):
                    with ui.element("div").classes("yt-titleline"):
                        attrs(ui.label(t.title).classes("yt-title"), title=t.title)
                        if t.id in self.new:
                            ui.label("Nuevo").classes("yt-new")
                    meta = ui.label().classes("yt-meta")
                    with ui.element("div").classes("yt-third"):
                        bar = ui.element("div").classes("yt-track")
                        with bar:
                            fill = ui.element("div").classes("yt-fill")
                        reason = ui.label().classes("yt-reason")
                with ui.element("div").classes("yt-pill") as pill:
                    pill_text = ui.label()
                action = ui.element("div").classes("yt-actions")
                button("×", "yt-remove", lambda t=t: self.on_remove(t.id), stop=True).props('title="Quitar de la cola"')
            row = dict(el=el, track=t, fill=fill, bar=bar, reason=reason, meta=meta, pill=pill,
                       pill_text=pill_text, action=action, error_shown=None)
            self.rows[t.id] = row
            self._paint(t.id)


def summary_dialog(summary: Summary, folder: str, processed: int, go_player: Callable[[], None],
                   open_folder: Callable[[], None], retry_failed: Callable[[], None] | None) -> None:
    """End-of-batch summary (after the automatic retry pass, or when stopped)."""
    with ui.dialog() as dialog, ui.card().classes("yt-modal yt-summary w-[540px] max-h-[90vh] overflow-auto p-0 gap-0 no-wrap"):
        with ui.column().classes("px-6 pt-[22px] pb-1 gap-1 w-full"):
            ui.label("Descarga detenida" if summary.stopped else "Descarga terminada").classes("text-[17px] font-semibold")
            ui.label(summary.subtitle or f"{processed} pistas procesadas").classes("text-[13px] yt-muted")
        with ui.element("div").classes("grid grid-cols-4 gap-2 px-6 py-4 w-full"):
            for label, n, cls in (("Descargadas", summary.done, "ok"), ("Ya estaban", summary.skipped, "plain"),
                                  ("Fallidas", summary.failed, "err"), ("Detenidas", summary.stopped, "plain")):
                with ui.element("div").classes(f"yt-card {cls}"):
                    ui.label(str(n)).classes("text-2xl font-semibold")
                    ui.label(label).classes("k text-xs")
        with ui.element("div").classes("grid gap-x-4 gap-y-1.5 px-6 pb-4 text-[13px] w-full") \
                .style("grid-template-columns: auto minmax(0, 1fr)"):
            for k, v in (("Peso total", human_size(summary.total_bytes)), ("Tiempo", human_time(summary.elapsed)),
                         ("Carpeta", folder)):
                ui.label(k).classes("yt-muted")
                ui.label(v).classes("mono text-xs break-all")
        if summary.failures:
            with ui.element("div").classes("yt-failbox mx-6 mb-4").style("width: calc(100% - 48px)"):
                ui.label("Fallidas").classes("h")
                for title, reason in summary.failures:
                    with ui.element("div").classes("r"):
                        ui.label(title).classes("truncate min-w-0")
                        attrs(ui.label(reason).classes("yt-error truncate min-w-0 text-right"), title=reason)
        with ui.row().classes("yt-panel yt-line-t w-full gap-2 px-6 py-3.5 no-wrap items-center"):
            button("Cerrar", "yt-ghostbtn", dialog.close)
            ui.element("div").classes("flex-1")
            if retry_failed:
                button("Reintentar fallidas", "yt-danger yt-md", lambda: (dialog.close(), retry_failed()))
            button("Abrir carpeta", "yt-btn", open_folder)
            button("Ir al reproductor", "yt-primary", lambda: (dialog.close(), go_player()))
    dialog.on("hide", dialog.delete)
    dialog.open()


def log_file_dialog(path: Path, reveal_text: str, reveal: Callable[[], None]) -> None:
    """Whole .log file, untruncated, with a button to show it in the OS file manager."""
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()[-5000:]
    except OSError as e:
        lines = [f"No se pudo leer el registro: {e}"]
    with closable(ui.dialog()) as dialog, ui.card().classes("yt-modal w-[820px] h-[540px] max-w-[95vw] max-h-[90vh] p-0 gap-0 no-wrap"):
        with ui.row().classes("yt-line-b w-full items-center justify-between no-wrap gap-3 py-3 pl-5 pr-3.5"):
            ui.label(str(path)).classes("mono text-xs yt-text2 truncate min-w-0")
            with ui.row().classes("gap-1.5 no-wrap shrink-0"):
                button(reveal_text, "yt-btn h-[30px] text-xs", reveal)
                button("×", "yt-ghost w-[30px] h-[30px] text-lg", dialog.close)
        with ui.element("div").classes("yt-logbox flex-1 w-full rounded-none border-0 px-5 py-3.5"):
            for line in lines:
                ui.label(line).classes(log_class(line))
    dialog.on("hide", dialog.delete)
    dialog.open()


def log_class(line: str) -> str:
    if " ERROR " in line or "✗" in line:
        return "err"
    if " WARNING " in line or "↻" in line:
        return "amb"
    return "ok" if "✓" in line else ""


async def confirm_dialog(make_plan: Callable[[bool], Plan], folder: Callable[[], str],
                         change_folder: Callable, consent: dict) -> Plan | None:
    """«¿Descargar N pista(s)?» review; returns the plan to run, or None if cancelled."""
    with closable(ui.dialog()) as dialog, ui.card().classes("yt-modal yt-confirm w-[500px] max-w-[95vw] max-h-[90vh] overflow-auto p-0 gap-0 no-wrap"):

        @ui.refreshable
        def body() -> None:
            plan = make_plan(consent["ok"])
            with ui.column().classes("px-6 pt-[22px] pb-1.5 gap-1 w-full"):
                ui.label(f"¿Descargar {plan.count} pista(s)?").classes("text-[17px] font-semibold")
                ui.label("Revisa antes de empezar.").classes("text-[13px] yt-muted")
            with ui.element("div").classes("grid items-center gap-x-[18px] gap-y-2.5 px-6 pt-3.5 pb-4 text-[13px] w-full") \
                    .style("grid-template-columns: auto minmax(0, 1fr)"):
                ui.label("Carpeta").classes("yt-muted")
                with ui.row().classes("gap-2 items-center no-wrap min-w-0"):
                    attrs(ui.label(folder()).classes("mono text-xs truncate flex-1 min-w-0"), title=folder())
                    button("Cambiar", "yt-btn h-7 text-xs px-2.5", lambda: change())
                for k, v, mono in (("Formato", plan.format_label, False), ("Peso estimado", f"~{human_size(plan.size_bytes)}", True),
                                   ("Duración total", hhmmss(plan.duration) if plan.duration else "—", True)):
                    ui.label(k).classes("yt-muted")
                    ui.label(v).classes("mono text-xs" if mono else "")
            if plan.notes:
                with ui.column().classes("mx-6 mb-4 gap-1.5").style("width: calc(100% - 48px)"):
                    for kind, text in plan.notes:
                        ui.label(text).classes(f"yt-note yt-note-{kind}")
            with ui.element("div").classes("yt-consent mx-6 mb-4").style("width: calc(100% - 48px)") \
                    .on("click", lambda: toggle_consent()):
                with ui.element("div").classes("yt-check on" if consent["ok"] else "yt-check"):
                    ui.label("✓" if consent["ok"] else "")
                ui.label("Confirmo que tengo derecho a descargar este contenido (es mío, tiene licencia libre o "
                         "tengo permiso) y que soy responsable de su uso.")
            with ui.row().classes("yt-panel yt-line-t w-full justify-end gap-2 px-6 py-3.5 no-wrap"):
                button("Cancelar", "yt-btn", lambda: dialog.submit(None))
                go = button("Descargar", "yt-primary yt-confirm-go", lambda: dialog.submit(plan) if plan.can_start else None)
                if not plan.can_start:
                    # Not the `disabled` attribute: Quasar forces [disabled] to opacity .6 (!important, layered).
                    go.classes("yt-inactive").props('aria-disabled="true"')

        async def change() -> None:
            await change_folder()
            body.refresh()

        def toggle_consent() -> None:
            consent["ok"] = not consent["ok"]
            body.refresh()

        body()
    result = await dialog
    dialog.delete()
    return result


DEVELOPER = (("Nombre", "jysa65", None),
             ("GitHub", "github.com/JySa65", "https://github.com/JySa65"),
             ("Sitio web", "jysa65.dev", "https://jysa65.dev/es/"))
LEGAL = (
    "Esta herramienta se ofrece «tal cual», sin garantías. Úsala solo con contenido propio, con licencia libre "
    "o del que tengas permiso del titular de los derechos.",
    "Tú eres responsable de cumplir las leyes de derechos de autor de tu país y las condiciones de uso de cada "
    "plataforma. El desarrollador no se hace responsable del uso que se le dé.",
    "No está afiliada, patrocinada ni aprobada por YouTube ni Google. Las marcas mencionadas pertenecen a sus dueños.",
)


def link(text: str, url: str, cls: str = "yt-a") -> ui.element:
    """Opens in the default browser (no console window), not inside the app window."""
    return attrs(button(text, cls, lambda: open_url(url)), title=url)


def about_dialog(version: str, build: str, icon_svg: str, repo: str) -> None:
    found = {"url": None}

    async def check_updates() -> None:
        status.text, status_link.visible = "Buscando…", False
        release = await run.io_bound(fetch_latest)
        kind, message, url = update_status(release, version)
        status.text = message
        status.classes(replace=f"text-xs yt-upd-{kind}")
        found["url"] = url
        status_link.visible = bool(url)

    with closable(ui.dialog()) as dialog, ui.card().classes("yt-modal yt-about w-[480px] max-w-[95vw] max-h-[90vh] p-0 gap-0 no-wrap"):
        with ui.column().classes("flex-1 min-h-0 overflow-auto pb-4 gap-0 w-full no-wrap"):
            with ui.element("div").classes("grid items-center px-6 pt-[22px] pb-4 gap-x-4 gap-y-1 w-full") \
                    .style("grid-template-columns: 56px minmax(0, 1fr)"):
                ui.html(icon_svg.replace('width="20" height="20"', 'width="56" height="56"'), sanitize=False) \
                    .classes("flex").style("grid-row: span 2")
                with ui.column().classes("gap-[3px]"):
                    ui.label("Pista").classes("text-[17px] font-semibold")
                    ui.label(f"Versión {version} · build {build}").classes("mono text-xs yt-muted")
                ui.label("Descarga audio y video por lotes o por Mix, y reprodúcelos desde tu carpeta.") \
                    .classes("text-xs yt-muted leading-normal")
            with ui.element("div").classes("yt-about-box mx-6").style("width: calc(100% - 48px)"):
                ui.label("Desarrollador").classes("yt-about-h")
                with ui.element("div").classes("grid gap-x-3 gap-y-1.5 px-3.5 py-2.5 text-[13px]") \
                        .style("grid-template-columns: 80px minmax(0, 1fr)"):
                    for key, value, url in DEVELOPER:
                        ui.label(key).classes("yt-muted")
                        link(value, url, "yt-a justify-self-start") if url else ui.label(value)
            with ui.column().classes("yt-legal mx-6 mt-3.5 gap-1.5").style("width: calc(100% - 48px)"):
                ui.label("Aviso legal").classes("yt-about-k")
                for paragraph in LEGAL:
                    ui.label(paragraph)
            with ui.row().classes("px-6 pt-2.5 gap-1 text-xs yt-subtle items-baseline"):
                ui.label("Usa yt-dlp y FFmpeg (software libre, con sus propias licencias). © 2026 jysa65 ·")
                link("Licencia GPLv3", f"https://github.com/{repo}/blob/main/LICENSE")
                ui.label("·")
                link("Avisos de terceros", f"https://github.com/{repo}/blob/main/.github/THIRD_PARTY_NOTICES.md")
            with ui.row().classes("px-6 pt-3 gap-2 items-center no-wrap"):
                status = ui.label().classes("text-xs")
                status_link = button("Ver la versión nueva", "yt-a text-xs",
                                     lambda: open_url(found["url"], is_release_url))
                status_link.visible = False
        with ui.row().classes("yt-panel yt-line-t w-full justify-end gap-2 px-6 py-3.5 no-wrap shrink-0"):
            button("Buscar actualizaciones", "yt-btn h-[34px]", check_updates)
            button("Cerrar", "yt-primary h-[34px]", dialog.close)
    dialog.on("hide", dialog.delete)
    dialog.open()
