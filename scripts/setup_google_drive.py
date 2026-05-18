"""One-time Google Drive OAuth2 setup."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CREDENTIALS_FILE = ROOT / "data" / "google_credentials.json"
TOKEN_FILE       = ROOT / "data" / "google_token.json"
SCOPES           = ["https://www.googleapis.com/auth/drive"]


def main() -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("XATO: pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)

    if not CREDENTIALS_FILE.exists():
        print(f"XATO: {CREDENTIALS_FILE} topilmadi.")
        sys.exit(1)

    print("Brauzer ochilmoqda — Google akkauntingizga ruxsat bering...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(creds.to_json())
    print(f"OK! Token saqlandi: {TOKEN_FILE}")
    print("Endi Novaga 'Drive dagi fayllarni korsat' deb yuboring.")


if __name__ == "__main__":
    main()
