"""Local web server hardening.

Pista's UI is a local web page served by NiceGUI. These settings make sure only this machine's app window
can talk to it: no other device on the network, and no other website open in a browser (DNS rebinding /
cross-site socket.io).
"""
import random

from fastapi import FastAPI
from socketio import AsyncServer
from starlette.middleware.trustedhost import TrustedHostMiddleware

from nicegui import native

HOST = "127.0.0.1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


def allowed_origins(port: int) -> list[str]:
    return [f"http://{host}:{port}" for host in ALLOWED_HOSTS]


def pick_port() -> int:
    """A free loopback port in a random range, so other software can't rely on a fixed one."""
    start = random.randrange(20000, 60000)
    return native.find_open_port(start, start + 999)


def harden(app: FastAPI, sio: AsyncServer, port: int) -> None:
    # Reject requests whose Host header isn't loopback (stops DNS-rebinding sites from reaching the API).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    # NiceGUI creates its socket.io server with cors_allowed_origins='*' and has no public option to change it;
    # `cors_allowed_origins` is a public attribute of the python-engineio server, read on every request.
    sio.eio.cors_allowed_origins = allowed_origins(port)
