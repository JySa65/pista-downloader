"""Rotating log file with the full app + yt-dlp log (timestamps, untruncated lines, home path anonymized)."""
import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_NAME = "pista.log"


def redact(text: str, home: str, platform: str = sys.platform) -> str:
    """Replace the user's home directory with '~' so shared logs don't reveal the user name.

    Windows paths are case-insensitive and may use either slash.
    """
    home = home.rstrip("/\\")
    if not home:
        return text
    if platform == "win32":
        parts = re.split(r"[\\/]+", home)
        pattern = r"[\\/]".join(re.escape(p) for p in parts)
        return re.sub(pattern + r"(?![^\\/\s\"'|:;,)\]])", "~", text, flags=re.IGNORECASE)
    return re.sub(re.escape(home) + r"(?![^/\s\"'|:;,)\]])", "~", text)


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record), str(Path.home()))


def _open_handler(directory: Path) -> tuple[Path, RotatingFileHandler]:
    """Rotating handler in `directory`, else in a temp folder (an unwritable log must not stop the app)."""
    import tempfile

    for d in (directory, Path(tempfile.gettempdir()) / "pista-logs", Path(tempfile.mkdtemp(prefix="pista-logs-"))):
        try:
            d.mkdir(parents=True, exist_ok=True)
            path = d / LOG_NAME
            return path, RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        except OSError:
            continue
    raise OSError("no writable log directory")  # unreachable in practice: mkdtemp just created one


def setup_logging(directory: Path) -> Path:
    """Attach (once) a rotating file handler to the 'pista' logger; returns the log path."""
    logger = logging.getLogger("pista")
    logger.setLevel(logging.INFO)
    for h in [h for h in logger.handlers if getattr(h, "_pista", False)]:
        logger.removeHandler(h)
        h.close()
    path, handler = _open_handler(directory)
    if path.parent != directory:
        sys.stderr.write(f"pista: no se puede escribir el registro en {directory}; usando {path}\n")
    handler.setFormatter(_RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler._pista = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    return path
