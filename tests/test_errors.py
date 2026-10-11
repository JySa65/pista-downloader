import pytest

from pista.core.batch import BOT_HINT

from pista.core.batch import Result, friendly_error, strip_ansi, summarize
from pista.core.downloader import base_opts

BOT = ("\x1b[0;31mERROR:\x1b[0m [youtube] jNQXAC9IVRw: Sign in to confirm you’re not a bot. Use --cookies-from-browser "
       "or --cookies for the authentication. See  https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp")


def test_strip_ansi():
    assert strip_ansi("\x1b[0;31mERROR:\x1b[0m boom \x1b[1m!") == "ERROR: boom !"
    assert strip_ansi("plain") == "plain" and strip_ansi("") == ""


@pytest.mark.parametrize("raw, expected", [
    (BOT, "YouTube pide verificar que no eres un robot. Espera unos minutos e inténtalo de nuevo. " + BOT_HINT),
    ("ERROR: [youtube] x: HTTP Error 429: Too Many Requests",
     "YouTube está limitando las descargas (demasiadas solicitudes). Espera unos minutos e inténtalo de nuevo."),
    ("ERROR: [youtube] x: Private video. Sign in if you've been granted access to this video",
     "El video es privado."),
    ("ERROR: [youtube] x: Video unavailable. This video has been removed by the uploader", "El video no está disponible."),
    ("ERROR: [youtube] x: Video unavailable", "El video no está disponible."),
    ("ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate for some users.",
     "El video tiene restricción de edad."),
    ("ERROR: [youtube] x: The uploader has not made this video available in your country",
     "El video no está disponible en tu país."),
    ("ERROR: [youtube] x: Join this channel to get access to members-only content like this video",
     "El video es solo para miembros del canal."),
    ("ERROR: [youtube] x: Unable to download webpage: <urlopen error [Errno 8] nodename nor servname provided, or not known>",
     "Sin conexión o no se encontró el servidor. Revisa tu internet."),
    ("ERROR: unable to download video data: <urlopen error timed out>", "Sin conexión o no se encontró el servidor. Revisa tu internet."),
    ("ERROR: [youtube] x: \x1b[0;31msomething new\x1b[0m happened", "something new happened"),
])
def test_friendly_error(raw, expected):
    assert friendly_error(raw) == expected


def test_summary_uses_friendly_reasons():
    s = summarize([Result("A", "error", error=BOT)], 1)
    assert s.failures == [("A", "YouTube pide verificar que no eres un robot. Espera unos minutos e inténtalo de nuevo. " + BOT_HINT)]


def test_yt_dlp_output_has_no_colors():
    assert base_opts(None, None, None)["no_color"] is True
