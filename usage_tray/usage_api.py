import json
import time
import urllib.error
import urllib.request
from pathlib import Path

CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
KIND_ORDER = {
    "session": 0,
    "weekly_all": 1,
    "weekly_scoped": 2,
}


class TokenUnavailable(Exception):
    pass


def read_token() -> str:
    data = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
    oauth = data["claudeAiOauth"]
    if oauth.get("expiresAt", 0) / 1000 <= time.time():
        raise TokenUnavailable("access token expired")
    return oauth["accessToken"]


def fetch_limits() -> list[dict]:
    request = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {read_token()}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-usage-tray/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    limits = payload.get("limits") or []
    return sorted(limits, key=lambda item: KIND_ORDER.get(item.get("kind"), len(KIND_ORDER)))


def retry_after(error: urllib.error.HTTPError) -> int:
    try:
        return max(int(error.headers.get("Retry-After") or 0), 0)
    except ValueError:
        return 0
