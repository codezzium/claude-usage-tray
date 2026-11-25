import winreg

SETTINGS_KEY = r"Software\ClaudeUsageTray"
COMPACT_VALUE = "Compact"


def is_compact() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as key:
            value, _ = winreg.QueryValueEx(key, COMPACT_VALUE)
    except FileNotFoundError:
        return False
    return bool(value)


def set_compact(compact: bool) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as key:
        winreg.SetValueEx(key, COMPACT_VALUE, 0, winreg.REG_DWORD, int(compact))
