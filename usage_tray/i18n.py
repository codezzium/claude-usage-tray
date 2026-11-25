import ctypes
import ctypes.wintypes as wt

LANG_TURKISH = 0x1F

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetUserDefaultUILanguage.restype = wt.WORD

TEXTS = {
    "en": {
        "session": "5-hour session",
        "weekly_all": "Weekly (all models)",
        "weekly_model": "Weekly ({model})",
        "resets": "Resets",
        "refresh": "Refresh now",
        "startup": "Start with Windows",
        "show_all": "Show every limit",
        "quit": "Quit",
        "app": "Claude usage",
        "unavailable": "unavailable",
        "loading": "loading",
        "no_limits": "no limits returned",
        "token_expired": "open Claude Code to refresh the login",
        "token_invalid": "token rejected (401)",
        "updated": "Updated",
        "rate_limited": "rate limited, waiting",
    },
    "tr": {
        "session": "5 saatlik oturum",
        "weekly_all": "Haftalık (tümü)",
        "weekly_model": "Haftalık ({model})",
        "resets": "Sıfırlanma",
        "refresh": "Şimdi yenile",
        "startup": "Windows ile başlat",
        "show_all": "Tüm limitleri göster",
        "quit": "Çıkış",
        "app": "Claude kullanımı",
        "unavailable": "okunamadı",
        "loading": "yükleniyor",
        "no_limits": "limit gelmedi",
        "token_expired": "Claude Code oturumu yenilenmeli",
        "token_invalid": "token geçersiz (401)",
        "updated": "Güncellendi",
        "rate_limited": "çok sık istek, bekleniyor",
    },
}


def detect_language() -> str:
    if kernel32.GetUserDefaultUILanguage() & 0x3FF == LANG_TURKISH:
        return "tr"
    return "en"


T = TEXTS[detect_language()]
