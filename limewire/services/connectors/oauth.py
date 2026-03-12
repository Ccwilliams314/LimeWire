"""OAuth helpers — local callback server, token exchange, and refresh."""

from __future__ import annotations

import http.server
import threading
import time
import webbrowser
from urllib.parse import urlparse, parse_qs

import requests

REDIRECT_PORT = 18734
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"


class _OAuthResult:
    """Mutable container shared between server thread and caller."""
    def __init__(self):
        self.params: dict | None = None
        self.event = threading.Event()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Captures the OAuth callback redirect parameters."""

    result: _OAuthResult  # set on the class before serving

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            qs = parse_qs(parsed.query)
            self.result.params = {k: v[0] for k, v in qs.items()}
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization successful!</h2>"
                b"<p>You can close this tab and return to LimeWire.</p>"
                b"</body></html>"
            )
            self.result.event.set()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # silence request logging


def start_oauth_flow(auth_url: str, timeout: int = 120) -> dict | None:
    """Open browser to auth_url, start local server, wait for callback.

    Returns dict with 'code' and 'state' on success, None on timeout.
    """
    result = _OAuthResult()
    _CallbackHandler.result = result

    server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    server.timeout = 1

    def serve():
        deadline = time.time() + timeout
        while not result.event.is_set() and time.time() < deadline:
            server.handle_request()
        server.server_close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()

    webbrowser.open(auth_url)
    result.event.wait(timeout=timeout)
    return result.params


def exchange_code_for_token(
    token_url: str,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str = REDIRECT_URI,
) -> dict:
    """Exchange authorization code for access/refresh tokens.

    Returns dict: {access_token, refresh_token, expires_in, token_type, ...}
    or {error: str} on failure.
    """
    try:
        resp = requests.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)[:200]}


def refresh_access_token(
    token_url: str,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict:
    """Refresh an expired access token.

    Returns dict: {access_token, expires_in, ...} or {error: str}.
    """
    try:
        resp = requests.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)[:200]}
