"""One-time Canva OAuth2 setup with PKCE."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

TOKEN_FILE   = ROOT / "data" / "canva_token.json"
AUTH_URL     = "https://www.canva.com/api/oauth/authorize"
TOKEN_URL    = "https://api.canva.com/rest/v1/oauth/token"
REDIRECT_URI = "http://127.0.0.1:8766/callback"
SCOPES       = "design:meta:read design:content:read design:content:write asset:read asset:write"
PORT         = 8766

_code_holder: dict = {}


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    digest   = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            error = params.get("error", [""])[0]
            if error:
                desc = params.get("error_description", [error])[0]
                _code_holder["error"] = desc
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h2>XATO: {desc}</h2>".encode())
            else:
                _code_holder["code"] = params.get("code", [""])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h2>OK! Canva ulandi. Bu oynani yoping.</h2>")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *_):
        pass


def main() -> None:
    try:
        import httpx
    except ImportError:
        print("XATO: pip install httpx")
        sys.exit(1)

    from core.config import settings

    client_id     = settings.canva_client_id
    client_secret = settings.canva_client_secret

    if not client_id or not client_secret:
        print("XATO: .env da NOVA_CANVA_CLIENT_ID va NOVA_CANVA_CLIENT_SECRET yozilmagan.")
        sys.exit(1)

    code_verifier, code_challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_link = f"{AUTH_URL}?{urlencode(params)}"

    server = HTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print(f"Brauzer ochilmoqda...")
    webbrowser.open(auth_link)
    print("Brauzerda 'Allow' ni bosing, keyin avtomatik davom etadi...")

    deadline = time.time() + 180
    while "code" not in _code_holder and "error" not in _code_holder and time.time() < deadline:
        time.sleep(0.5)

    if "error" in _code_holder:
        print(f"XATO (Canva): {_code_holder['error']}")
        sys.exit(1)

    if "code" not in _code_holder:
        print("XATO: Vaqt tugadi (3 daqiqa). Qayta ishga tushiring.")
        sys.exit(1)

    code = _code_holder["code"]
    print(f"Kod olindi, token so'ralmoqda...")

    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": code_verifier,
        },
        auth=(client_id, client_secret),
        timeout=15,
    )

    if resp.status_code != 200:
        print(f"XATO: {resp.status_code} — {resp.text}")
        sys.exit(1)

    token_data = resp.json()
    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600) - 60
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    print(f"OK! Token saqlandi: {TOKEN_FILE}")
    print("Endi Novaga 'Canva dizaynlarni korsat' deb yuboring.")


if __name__ == "__main__":
    main()
