"""4: update check against a hostile/broken server (local HTTP server, no internet)."""
import http.server
import json
import threading

import pytest

from pista.core.links import is_release_url
from pista.core.updates import fetch_latest, update_status

GOOD = {"tag_name": "v9.9.9", "html_url": "https://github.com/JySa65/pista-downloader/releases/tag/v9.9.9"}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/ok":
            self._send(200, json.dumps(GOOD).encode())
        elif self.path == "/badjson":
            self._send(200, b"<html>not json")
        elif self.path == "/404":
            self._send(404, b'{"message": "Not Found"}')
        elif self.path == "/500":
            self._send(500, b"oops")
        elif self.path == "/slow":
            threading.Event().wait(3)
            self._send(200, json.dumps(GOOD).encode())
        elif self.path == "/redirect-offhost":
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{self.server.server_port}/ok")  # other host name
            self.end_headers()
        elif self.path == "/list":
            self._send(200, b"[1, 2, 3]")
        elif self.path == "/numbers":
            self._send(200, json.dumps({"tag_name": 10, "html_url": None}).encode())

    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.mark.parametrize("path", ["/badjson", "/404", "/500"])
def test_broken_responses_give_a_friendly_error(server, path):
    kind, message, url = update_status(fetch_latest(url=server + path, timeout=2), "0.3.1")
    assert kind == "error" and url is None and "No se pudo comprobar" in message


def test_timeout_is_bounded(server):
    import time
    t0 = time.monotonic()
    assert fetch_latest(url=server + "/slow", timeout=0.5) is None
    assert time.monotonic() - t0 < 2


def test_good_release(server):
    assert update_status(fetch_latest(url=server + "/ok", timeout=2), "0.3.1")[0] == "new"


def test_off_repo_release_page_is_never_opened():
    evil = {"tag_name": "v9.9.9", "html_url": "https://evil.example/pista.exe"}
    kind, _, url = update_status(evil, "0.3.1")
    assert not is_release_url(url)  # the UI only opens it through open_url(url, is_release_url)


@pytest.mark.parametrize("path", ["/list", "/numbers"])
def test_unexpected_json_shapes_give_a_friendly_error(server, path):
    kind, message, url = update_status(fetch_latest(url=server + path, timeout=2), "0.3.1")
    assert kind == "error" and url is None


def test_redirect_to_another_host_is_not_followed(server):
    assert fetch_latest(url=server + "/redirect-offhost", timeout=2) is None


@pytest.mark.parametrize("release", [[1, 2], "v1.0.0", {"tag_name": 10}, {"tag_name": None}, {"tag_name": "v1", "html_url": 5}])
def test_update_status_never_raises(release):
    kind, message, url = update_status(release, "0.3.1")
    assert kind in ("new", "latest", "error") and (url is None or isinstance(url, str))
