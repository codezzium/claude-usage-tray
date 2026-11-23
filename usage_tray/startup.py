import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Claude Usage Tray"
MAIN_SCRIPT = Path(__file__).resolve().parent.parent / "main.pyw"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def command() -> str:
    if is_frozen():
        return f'"{Path(sys.executable).resolve()}"'
    pythonw = Path(sys.executable).resolve().with_name("pythonw.exe")
    return f'"{pythonw}" "{MAIN_SCRIPT}"'


def registered() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None
    return value if isinstance(value, str) else None


def is_enabled() -> bool:
    return registered() is not None


def enable() -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass


def refresh() -> None:
    current = registered()
    if is_frozen() and current is not None and current != command():
        enable()
