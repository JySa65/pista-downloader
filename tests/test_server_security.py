"""Local server hardening: only 127.0.0.1/localhost Host headers, socket.io only from the app's own origin."""
import asyncio

import httpx
from nicegui import core

from pista.ui.security import allowed_origins, harden, pick_port

PORT = 47123
HANDSHAKE = "/_nicegui_ws/socket.io/?EIO=4&transport=polling"


def request(path, host, origin=None):
    async def go():
        headers = {"host": host}
        if origin:
            headers["origin"] = origin
        async with httpx.AsyncClient(transport=httpx.ASGITransport(core.app), base_url="http://x") as c:
            return await c.get(path, headers=headers)
    return asyncio.run(go())


def setup_module():
    harden(core.app, core.sio, PORT)


def test_foreign_host_header_is_rejected():
    assert request("/_nicegui/auto/static/favicon.ico", "attacker.example").status_code == 400
    assert request("/_nicegui/auto/static/favicon.ico", f"attacker.example:{PORT}").status_code == 400


def test_loopback_hosts_are_accepted():
    for host in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
        assert request(HANDSHAKE, host, f"http://{host}").status_code == 200


def test_socketio_rejects_foreign_origin_even_with_valid_host():
    r = request(HANDSHAKE, f"127.0.0.1:{PORT}", "http://attacker.example")
    assert r.status_code == 400
    assert "attacker.example" not in r.headers.get("access-control-allow-origin", "")


def test_allowed_origins_and_random_port():
    assert allowed_origins(8123) == ["http://127.0.0.1:8123", "http://localhost:8123"]
    ports = {pick_port() for _ in range(5)}
    assert all(20000 <= p <= 60999 for p in ports) and len(ports) > 1
