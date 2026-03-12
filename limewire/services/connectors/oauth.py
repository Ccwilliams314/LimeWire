"""OAuth helpers — local callback server, token exchange, and refresh."""

from __future__ import annotations

import base64
import hashlib
import http.server
import re
import secrets
import threading
import time
import webbrowser
from urllib.parse import urlparse, parse_qs

import requests

REDIRECT_PORT = 18734
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"


def _sanitize_error(e: Exception) -> str:
    """Strip sensitive data (tokens, secrets, query params) from error messages."""
    msg = str(e)
    # Remove query parameters from URLs in error messages
    msg = re.sub(r"(https?://[^\s?]+)\?[^\s'\"]+", r"\1?<redacted>", msg)
    return msg[:200]


def generate_state() -> str:
    """Generate a cryptographically random state parameter for CSRF protection."""
    return secrets.token_urlsafe(32)


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256).

    Returns (code_verifier, code_challenge).
    """
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class _OAuthResult:
    """Mutable container shared between server thread and caller."""
    def __init__(self):
        self.params: dict | None = None
        self.event = threading.Event()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Captures the OAuth callback redirect parameters."""

    result: _OAuthResult  # set on the class before serving
    expected_state: str = ""  # set before serving for CSRF validation

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            qs = parse_qs(parsed.query)
            params = {k: v[0] for k, v in qs.items()}

            # Validate state parameter for CSRF protection
            received_state = params.get("state", "")
            if self.expected_state and received_state != self.expected_state:
                self.send_response(403)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Authorization failed</h2>"
                    b"<p>Invalid state parameter - possible CSRF attack.</p>"
                    b"</body></html>"
                )
                return

            self.result.params = params
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


def start_oauth_flow(auth_url: str, timeout: int = 120,
                     expected_state: str = "") -> dict | None:
    """Open browser to auth_url, start local server, wait for callback.

    Args:
        auth_url: Full authorization URL (must already include state param).
        timeout: Seconds to wait for callback.
        expected_state: If set, validates the returned state matches (CSRF protection).

    Returns dict with 'code' and 'state' on success, None on timeout.
    """
    result = _OAuthResult()
    _CallbackHandler.result = result
    _CallbackHandler.expected_state = expected_state

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
    code_verifier: str = "",
) -> dict:
    """Exchange authorization code for access/refresh tokens.

    Returns dict: {access_token, refresh_token, expires_in, token_type, ...}
    or {error: str} on failure.
    """
    try:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        resp = requests.post(token_url, data=data, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": _sanitize_error(e)}


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
        return {"error": _sanitize_error(e)}
