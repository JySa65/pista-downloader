"""Rotating log file with the full app + yt-dlp log (timestamps, untruncated lines)."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_NAME = "youtube-download.log"


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
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler._ytmp3 = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    return path
