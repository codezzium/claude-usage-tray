import ctypes
import ctypes.wintypes as wt
import json
import logging
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

APP_DIR = Path(__file__).resolve().parent
LOG_FILE = APP_DIR / "usage_tray.log"
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
POLL_SECONDS = 60
LAYOUT_SECONDS = 2
MAX_BACKOFF_SECONDS = 600
STALE_AFTER_FAILURES = 3
ERROR_ALREADY_EXISTS = 183
LANG_TURKISH = 0x1F
FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"
ICON_SIZE = 64

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel32.GetUserDefaultUILanguage.restype = wt.WORD
shell32 = ctypes.WinDLL("shell32")
log = logging.getLogger("usage_tray")

TEXTS = {
    "en": {
        "session": "5-hour session",
        "weekly_all": "Weekly (all models)",
        "weekly_model": "Weekly ({model})",
        "resets": "Resets",
        "refresh": "Refresh now",
        "quit": "Quit",
        "app": "Claude usage",
        "unavailable": "unavailable",
        "loading": "loading",
        "no_limits": "no limits returned",
        "token_expired": "open Claude Code to refresh the login",
        "token_invalid": "token rejected (401)",
    },
    "tr": {
        "session": "5 saatlik oturum",
        "weekly_all": "Haftalık (tümü)",
        "weekly_model": "Haftalık ({model})",
        "resets": "Sıfırlanma",
        "refresh": "Şimdi yenile",
        "quit": "Çıkış",
        "app": "Claude kullanımı",
        "unavailable": "okunamadı",
        "loading": "yükleniyor",
        "no_limits": "limit gelmedi",
        "token_expired": "Claude Code oturumu yenilenmeli",
        "token_invalid": "token geçersiz (401)",
    },
}
KIND_ORDER = {
    "session": 0,
    "weekly_all": 1,
    "weekly_scoped": 2,
}


def detect_language() -> str:
    if kernel32.GetUserDefaultUILanguage() & 0x3FF == LANG_TURKISH:
        return "tr"
    return "en"


T = TEXTS[detect_language()]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("guidItem", ctypes.c_byte * 16),
    ]


shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long
shell32.Shell_NotifyIconGetRect.argtypes = [ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(wt.RECT)]


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


def limit_key(limit: dict) -> str:
    scope = limit.get("scope") or {}
    model = (scope.get("model") or {}).get("display_name") or ""
    return f"{limit.get('kind')}:{model}"


def limit_label(limit: dict) -> str:
    kind = limit.get("kind") or "?"
    if kind in ("session", "weekly_all"):
        return T[kind]
    scope = limit.get("scope") or {}
    model = (scope.get("model") or {}).get("display_name")
    if model:
        return T["weekly_model"].format(model=model)
    return kind


def format_reset(value: str | None) -> str:
    if not value:
        return "-"
    moment = datetime.fromisoformat(value).astimezone() + timedelta(seconds=30)
    if moment.date() == datetime.now().astimezone().date():
        return moment.strftime("%H:%M")
    return moment.strftime("%d.%m %H:%M")


def color_for(percent: float | None) -> tuple[int, int, int]:
    if percent is None:
        return (110, 110, 110)
    if percent >= 80:
        return (200, 40, 40)
    if percent >= 50:
        return (215, 150, 0)
    return (30, 140, 60)


def draw_icon(text: str, percent: float | None) -> Image.Image:
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, ICON_SIZE - 1, ICON_SIZE - 1), radius=12, fill=color_for(percent))
    size = 46 if len(text) <= 2 else 32
    font = ImageFont.truetype(FONT_PATH, size)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    x = (ICON_SIZE - (right - left)) / 2 - left
    y = (ICON_SIZE - (bottom - top)) / 2 - top
    draw.text((x, y), text, font=font, fill=(255, 255, 255))
    return image


def icon_left(icon: pystray.Icon) -> int | None:
    hwnd = getattr(icon, "_hwnd", None)
    if not hwnd:
        return None
    for uid in (0, id(icon) & 0xFFFFFFFF):
        ident = NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        ident.hWnd = hwnd
        ident.uID = uid
        rect = wt.RECT()
        if shell32.Shell_NotifyIconGetRect(ctypes.byref(ident), ctypes.byref(rect)) == 0:
            return rect.left
    return None


class Slot:
    def __init__(self, index: int, icon: pystray.Icon) -> None:
        self.index = index
        self.icon = icon
        self.signature: tuple[str, str] | None = None
        self.hidden = False

    def paint(self, text: str, percent: float | None, title: str) -> None:
        signature = (text + str(color_for(percent)), title)
        if signature == self.signature:
            return
        self.signature = signature
        self.icon.icon = draw_icon(text, percent)
        self.icon.title = title[:127]


class App:
    def __init__(self) -> None:
        self.slots: list[Slot] = []
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.failures = 0
        self.limits: list[dict] = []
        self.stale_reason: str | None = T["loading"]

    def menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(T["refresh"], self.refresh_now, default=True),
            pystray.MenuItem(T["quit"], self.quit),
        )

    def refresh_now(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.wake_event.set()

    def quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.stop_event.set()
        self.wake_event.set()

    def ensure_slots(self, count: int) -> None:
        while len(self.slots) < count:
            index = len(self.slots)
            icon = pystray.Icon(f"claude-usage-{index}", draw_icon("?", None), T["app"], self.menu())
            self.slots.append(Slot(index, icon))
            icon.run_detached()
        for slot in self.slots[:count]:
            if slot.hidden:
                slot.icon.visible = True
                slot.hidden = False
                slot.signature = None
        for slot in self.slots[count:]:
            if not slot.hidden and slot.icon.visible:
                slot.icon.visible = False
                slot.hidden = True

    def ordered_slots(self, count: int) -> list[Slot]:
        active = self.slots[:count]
        lefts = {slot.index: icon_left(slot.icon) for slot in active}
        if any(value is None for value in lefts.values()) or len(set(lefts.values())) < len(active):
            return active
        return sorted(active, key=lambda slot: (lefts[slot.index], slot.index))

    def render(self) -> None:
        with self.lock:
            limits = self.limits
            count = max(len(limits), 1)
            self.ensure_slots(count)
            slots = self.ordered_slots(count)
            if not limits:
                slots[0].paint("?", None, f"{T['app']}: {self.stale_reason or T['no_limits']}")
                return
            for slot, limit in zip(slots, limits):
                if self.stale_reason:
                    slot.paint("?", None, f"{limit_label(limit)}: {T['unavailable']} ({self.stale_reason})")
                    continue
                percent = limit.get("percent")
                text = "?" if percent is None else str(round(percent))
                title = f"{limit_label(limit)}: %{text}\n{T['resets']}: {format_reset(limit.get('resets_at'))}"
                slot.paint(text, percent, title)

    def poll_once(self) -> int:
        try:
            limits = fetch_limits()
        except TokenUnavailable as error:
            log.warning("token unavailable: %s", error)
            self.stale_reason = T["token_expired"]
            return POLL_SECONDS
        except urllib.error.HTTPError as error:
            self.failures += 1
            log.warning("http error %s", error.code)
            if error.code == 401:
                self.stale_reason = T["token_invalid"]
                return POLL_SECONDS
            if self.failures >= STALE_AFTER_FAILURES:
                self.stale_reason = f"HTTP {error.code}"
            if error.code == 429:
                return min(POLL_SECONDS * 2 ** self.failures, MAX_BACKOFF_SECONDS)
            return POLL_SECONDS
        except Exception as error:
            self.failures += 1
            log.warning("poll failed: %r", error)
            if self.failures >= STALE_AFTER_FAILURES:
                self.stale_reason = type(error).__name__
            return POLL_SECONDS
        self.failures = 0
        self.stale_reason = None
        self.limits = limits
        log.info("ok %s", [(limit_key(item), item.get("percent")) for item in limits])
        return POLL_SECONDS

    def run(self) -> None:
        next_poll = 0.0
        while not self.stop_event.is_set():
            try:
                if self.wake_event.is_set() or time.monotonic() >= next_poll:
                    self.wake_event.clear()
                    next_poll = time.monotonic() + self.poll_once()
                self.render()
            except Exception:
                log.exception("unexpected error in main loop")
                next_poll = time.monotonic() + POLL_SECONDS
            self.wake_event.wait(LAYOUT_SECONDS)
        for slot in self.slots:
            slot.icon.stop()


def main() -> None:
    handler = RotatingFileHandler(LOG_FILE, maxBytes=256_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    kernel32.CreateMutexW(None, False, "Local\\claude-usage-tray")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        sys.exit(0)
    try:
        App().run()
    except Exception:
        log.exception("fatal error")
        raise


if __name__ == "__main__":
    main()
