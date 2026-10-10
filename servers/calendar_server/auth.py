"""Google OAuth flow and token storage (only used by google_provider).

Run this ONCE in a normal terminal before starting the agent:
    python -m servers.calendar_server.auth
(The browser flow must not run inside a stdio server: stdout is reserved for the protocol.)
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = Path(os.getenv("GOOGLE_TOKEN_FILE", "token.json"))
    creds_path = Path(os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"))

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not creds_path.exists():
            raise FileNotFoundError(
                f"{creds_path} not found. Download OAuth client credentials from Google Cloud Console."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json())
    try:
        token_path.chmod(0o600)
    except OSError:
        pass
    return creds


if __name__ == "__main__":
    get_credentials()
    print("Google Calendar authorized. Token saved.")