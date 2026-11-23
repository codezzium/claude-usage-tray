import ctypes
import ctypes.wintypes as wt
import logging
import os
import sys
import threading
import time
import urllib.error
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

from usage_tray import startup
from usage_tray.i18n import T
from usage_tray.usage_api import TokenUnavailable, fetch_limits, retry_after

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ClaudeUsageTray"
LOG_FILE = (DATA_DIR if startup.is_frozen() else APP_DIR) / "usage_tray.log"
POLL_SECONDS = 300
MAX_POLL_SECONDS = 1800
STALE_SECONDS = 2 * MAX_POLL_SECONDS + 60
MIN_MANUAL_GAP_SECONDS = 60
LAYOUT_SECONDS = 2
ERROR_ALREADY_EXISTS = 183
INFINITE = 0xFFFFFFFF
MUTEX_NAME = "Local\\claude-usage-tray"
QUIT_EVENT_NAME = "Local\\claude-usage-tray-quit"
FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"
ICON_SIZE = 64

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel32.CreateEventW.restype = wt.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
kernel32.ResetEvent.restype = wt.BOOL
kernel32.ResetEvent.argtypes = [wt.HANDLE]
kernel32.WaitForSingleObject.restype = wt.DWORD
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
shell32 = ctypes.WinDLL("shell32")
log = logging.getLogger("usage_tray")


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("guidItem", ctypes.c_byte * 16),
    ]


shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long
shell32.Shell_NotifyIconGetRect.argtypes = [ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(wt.RECT)]


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
        self.interval = POLL_SECONDS
        self.limits: list[dict] = []
        self.updated_at: datetime | None = None
        self.updated_mono: float | None = None
        self.error: str | None = None
        self.last_request = float("-inf")
        self.cooldown_until = 0.0
        self.last_was_ok = False
        self.consecutive_429 = 0

    def menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(T["refresh"], self.refresh_now, default=True),
            pystray.MenuItem(T["startup"], self.toggle_startup, checked=lambda item: startup.is_enabled()),
            pystray.MenuItem(T["quit"], self.quit),
        )

    def toggle_startup(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            if startup.is_enabled():
                startup.disable()
                log.info("startup disabled")
            else:
                startup.enable()
                log.info("startup enabled: %s", startup.command())
        except OSError:
            log.exception("startup toggle failed")
        for slot in list(self.slots):
            slot.icon.update_menu()

    def refresh_now(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        now = time.monotonic()
        if now - self.last_request < MIN_MANUAL_GAP_SECONDS or now < self.cooldown_until:
            log.info("manual refresh ignored")
            return
        self.wake_event.set()

    def quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.stop()

    def stop(self) -> None:
        self.stop_event.set()
        self.wake_event.set()

    def watch_quit_event(self, handle: int) -> None:
        kernel32.WaitForSingleObject(handle, INFINITE)
        log.info("quit requested by another process")
        self.stop()

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
            fresh = self.updated_mono is not None and time.monotonic() - self.updated_mono <= STALE_SECONDS
            if not limits or not fresh or self.updated_at is None:
                reason = self.error or (T["no_limits"] if self.updated_at else T["loading"])
                for slot in slots:
                    slot.paint("?", None, f"{T['app']}: {T['unavailable']} ({reason})")
                return
            updated = f"{T['updated']}: {self.updated_at.strftime('%H:%M')}"
            if self.error:
                updated += f" ({self.error})"
            for slot, limit in zip(slots, limits):
                percent = limit.get("percent")
                text = "?" if percent is None else str(round(percent))
                reset = format_reset(limit.get("resets_at"))
                title = f"{limit_label(limit)}: %{text}\n{T['resets']}: {reset}\n{updated}"
                slot.paint(text, percent, title)

    def poll_once(self) -> float:
        self.last_request = time.monotonic()
        previous_ok = self.last_was_ok
        self.last_was_ok = False
        try:
            limits = fetch_limits()
        except TokenUnavailable as error:
            log.warning("token unavailable: %s", error)
            self.error = T["token_expired"]
            return self.interval
        except urllib.error.HTTPError as error:
            if error.code == 429:
                if previous_ok:
                    self.interval = min(self.interval * 2, MAX_POLL_SECONDS)
                self.consecutive_429 += 1
                delay = min(self.interval * 2 ** (self.consecutive_429 - 1), MAX_POLL_SECONDS)
                delay = max(delay, retry_after(error))
                self.cooldown_until = time.monotonic() + delay
                self.error = T["rate_limited"]
                log.warning("http 429, next request in %s s, interval now %s s", delay, self.interval)
                return delay
            log.warning("http error %s", error.code)
            self.error = T["token_invalid"] if error.code == 401 else f"HTTP {error.code}"
            return self.interval
        except Exception as error:
            log.warning("poll failed: %r", error)
            self.error = type(error).__name__
            return self.interval
        self.error = None
        self.last_was_ok = True
        self.consecutive_429 = 0
        self.limits = limits
        self.updated_at = datetime.now()
        self.updated_mono = time.monotonic()
        log.info("ok %s", [(limit_key(item), item.get("percent")) for item in limits])
        return self.interval

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
                next_poll = time.monotonic() + self.interval
            self.wake_event.wait(LAYOUT_SECONDS)
        for slot in self.slots:
            slot.icon.stop()


def main() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=256_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        sys.exit(0)
    try:
        startup.refresh()
    except OSError:
        log.exception("startup refresh failed")
    app = App()
    quit_event = kernel32.CreateEventW(None, True, False, QUIT_EVENT_NAME)
    if quit_event:
        kernel32.ResetEvent(quit_event)
        threading.Thread(target=app.watch_quit_event, args=(quit_event,), daemon=True).start()
    try:
        app.run()
    except Exception:
        log.exception("fatal error")
        raise


if __name__ == "__main__":
    main()
