"""App-level state that outlives a page: Pista is a single-user desktop app, so there is one session.

When the window reloads, NiceGUI builds a new page while the running batch keeps going. The page reads
everything from here and attaches itself; the batch's UI side effects go to whichever page is attached
last (or nowhere, if none is open). Plain Python, so it can be tested without NiceGUI.
"""
from dataclasses import dataclass, field
from typing import Any, Callable

from pista.core.queue import QueueModel


class SharedQueue(QueueModel):
    """Queue data kept across pages; repaints go to the attached page's Queue view, if any."""

    view: Any = None

    def _changed(self) -> None:
        if self.view is not None:
            self.view._changed()

    def _state_changed(self, track_id: str) -> None:
        if self.view is not None:
            self.view._state_changed(track_id)


@dataclass
class Session:
    links: list[str] = field(default_factory=list)
    link_errors: dict[str, str] = field(default_factory=dict)  # url -> why it couldn't be loaded
    fmt: str = "audio"
    quality: str = "192"
    outdir: str | None = None  # None until a page sets its default
    busy: bool = False
    status: str = "Listo."
    last_summary: dict = field(default_factory=dict)  # kwargs for summary_dialog, reopened by «Ver resumen»
    runner: Any = None  # the running BatchRunner, if any
    log_lines: list[str] = field(default_factory=list)
    queue: SharedQueue = field(default_factory=SharedQueue)
    pages: list = field(default_factory=list)  # open pages, oldest first; the last one gets the updates
    ffmpeg_warned: bool = False  # the missing-ffmpeg warning is logged once per app run, not per page build

    @property
    def page(self) -> Any:
        return self.pages[-1] if self.pages else None

    def attach(self, page: Any) -> None:
        """`page` needs a `queue` attribute: the Queue view that paints `self.queue`."""
        self.pages.append(page)
        self.queue.view = page.queue

    def detach(self, page: Any) -> None:
        if page in self.pages:
            self.pages.remove(page)
        self.queue.view = self.page.queue if self.page else None

    def to_page(self, name: str, *args: Any) -> Any:
        """Call the attached page's `name(*args)`; nothing happens when no page is open."""
        page = self.page
        return None if page is None else getattr(page, name)(*args)

    def begin(self) -> bool:
        """Claim the single batch slot; False if a batch is already running (on this page or another)."""
        if self.busy:
            return False
        self.busy = True
        return True

    async def run_batch(self, make_runner: Callable[[], Any], set_busy: Callable[[bool], None],
                        on_error: Callable[[Exception], None]) -> tuple[Any, Any]:
        """Run one batch in the slot claimed by begin(); returns (runner, summary).

        On failure (on_error is called inside the except block) or cancellation the slot is released here;
        on success summary is set and the caller releases it once the summary is shown.
        """
        runner = summary = None
        try:  # everything after begin() is inside: any failure must release the batch slot
            runner = self.runner = make_runner()
            set_busy(True)
            summary = await runner.run()
        except Exception as e:  # never leave the UI stuck in «descargando»
            on_error(e)
        finally:
            self.runner = None
            if summary is None:  # failed or cancelled: the slot must not stay taken
                set_busy(False)
        return runner, summary


SESSION = Session()
