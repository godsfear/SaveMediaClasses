import os
from typing import Any, Dict

# Интервал автопроверки версий в часах (пункт 6)
CHECK_INTERVAL_HOURS = 6

DEFAULT_CONFIG: Dict[str, Any] = {
    "settings": {
        "download_path": "",
        "proxy_address": "socks5://127.0.0.1:1080",
        "proxy_enabled": False,
        "yt_dlp_args": "-f bestvideo+bestaudio/best --merge-output-format mp4",
        "audio_only": False,
        "cookies_browser": "none",
        "cookies_enabled": False,
        "embed_metadata": True,
        "playlist_enabled": False,
        "clean_titles": False,
        "save_to_source_folder": False,
        "minimize_to_tray": False,
        "last_check_time": 0.0,
        "last_needs_update": False,
        "urls": {
            "yt_api": "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
            "yt_download": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" if os.name == "nt" else "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
            "ffmpeg_version": "https://www.gyan.dev/ffmpeg/builds/release-version",
            "ffmpeg_download": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip"
        }
    },
    "window": {
        "width": 600,
        "height": 650,
        "left": 100,
        "top": 100
    },
    "theme": {
        "accent_color": "00B4D8",
        "switch_color": "4CAF50",
        "header_color": "00B4D8",
        "text_color": "E0E0E0",
        "progress_color": "4CAF50",
        "button_color": "4CAF50",
        "appbar_color": "1c1c1c",
        "card_color": "161616"
    }
}

THEME_FIELDS = [
    ("accent_color",   "Акцент (обводка полей, фокус)"),
    ("header_color",   "Заголовки секций"),
    ("switch_color",   "Цвет переключателей"),
    ("text_color",     "Основной текст / путь к папке"),
    ("progress_color", "Прогресс-бар и статус"),
    ("button_color",   "Кнопка «Скачать»"),
    ("appbar_color",   "Фон шапки AppBar"),
    ("card_color",     "Фон карточек"),
]

PALETTE = [
    "F44336","E91E63","9C27B0","673AB7","3F51B5","2196F3",
    "03A9F4","00BCD4","009688","4CAF50","8BC34A","CDDC39",
    "FFEB3B","FFC107","FF9800","FF5722","795548","9E9E9E",
    "607D8B","000000","212121","37474F","455A64","546E7A",
    "EF9A9A","F48FB1","CE93D8","B39DDB","90CAF9","80DEEA",
    "A5D6A7","FFE082","FFCC80","FF8A65","BCAAA4","EEEEEE",
    "00B4D8","00FF87","FF6B6B","FFD166","06D6A0","118AB2",
    "1c1c1c","161616","0d0d0d","1A237E","B71C1C","1B5E20",
]


def hex_to_flet(hex_str: str) -> str:
    h = hex_str.strip().lstrip("#").upper()
    if len(h) == 6 and all(c in "0123456789ABCDEF" for c in h):
        return f"#{h}"
    return "#FFFFFF"


def is_valid_hex(value: str) -> bool:
    h = value.strip().lstrip("#").upper()
    return len(h) == 6 and all(c in "0123456789ABCDEF" for c in h)


def safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def safe_int(value: Any, default: int = 0) -> int:
    if value is None or value == "": return default
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return default


def get_fallback_bool(source_dict: Dict[str, Any], key: str, default_bool: bool) -> bool:
    val = source_dict.get(key)
    return default_bool if val is None or val == "" else bool(val)
