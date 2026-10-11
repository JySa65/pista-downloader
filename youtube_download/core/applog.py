"""Rotating log file with the full app + yt-dlp log (timestamps, untruncated lines, home path anonymized)."""
import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_NAME = "youtube-download.log"


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


def setup_logging(directory: Path) -> Path:
    """Attach (once) a rotating file handler to the 'youtube_download' logger; returns the log path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_NAME
    logger = logging.getLogger("youtube_download")
    logger.setLevel(logging.INFO)
    for h in [h for h in logger.handlers if getattr(h, "_ytmp3", False)]:
        logger.removeHandler(h)
        h.close()
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(_RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler._ytmp3 = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    return path
