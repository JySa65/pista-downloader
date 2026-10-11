"""Already OK: network reads are bounded. yt-dlp defaults to a 20 s timeout when socket_timeout isn't set."""
from yt_dlp.networking.common import DEFAULT_TIMEOUT

from pista.core.downloader import base_opts


def test_network_reads_time_out():
    timeout = base_opts(None, None, None).get("socket_timeout") or DEFAULT_TIMEOUT
    assert 5 <= timeout <= 60
