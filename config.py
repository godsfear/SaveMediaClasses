import os
from dataclasses import dataclass
from typing import Any, Dict

# ── Константы приложения ──────────────────────────────────────────────────────

CHECK_INTERVAL_HOURS = 6

DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "Downloads")
DEFAULT_PROXY_ADDRESS = "socks5://127.0.0.1:1080"
DEFAULT_YT_DLP_ARGS   = "-f bestvideo+bestaudio/best --merge-output-format mp4"

DEFAULT_YT_API_URL          = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
DEFAULT_YT_DOWNLOAD_URL     = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    if os.name == "nt" else
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
)
DEFAULT_FFMPEG_VERSION_URL  = "https://www.gyan.dev/ffmpeg/builds/release-version"
DEFAULT_FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip"


# ── Typed конфиги (вместо Dict) ───────────────────────────────────────────────

@dataclass
class ThemeConfig:
    accent_color:   str = "00B4D8"
    switch_color:   str = "4CAF50"
    header_color:   str = "00B4D8"
    text_color:     str = "E0E0E0"
    progress_color: str = "4CAF50"
    button_color:   str = "4CAF50"
    appbar_color:   str = "1c1c1c"
    card_color:     str = "161616"

    def to_dict(self) -> Dict[str, str]:
        return {
            "accent_color":   self.accent_color,
            "switch_color":   self.switch_color,
            "header_color":   self.header_color,
            "text_color":     self.text_color,
            "progress_color": self.progress_color,
            "button_color":   self.button_color,
            "appbar_color":   self.appbar_color,
            "card_color":     self.card_color,
        }

    @staticmethod
    def from_dict(d: Dict[str, str]) -> "ThemeConfig":
        defaults = ThemeConfig()
        return ThemeConfig(
            accent_color   = safe_str(d.get("accent_color"))   or defaults.accent_color,
            switch_color   = safe_str(d.get("switch_color"))   or defaults.switch_color,
            header_color   = safe_str(d.get("header_color"))   or defaults.header_color,
            text_color     = safe_str(d.get("text_color"))     or defaults.text_color,
            progress_color = safe_str(d.get("progress_color")) or defaults.progress_color,
            button_color   = safe_str(d.get("button_color"))   or defaults.button_color,
            appbar_color   = safe_str(d.get("appbar_color"))   or defaults.appbar_color,
            card_color     = safe_str(d.get("card_color"))     or defaults.card_color,
        )


@dataclass
class WindowConfig:
    width:  int = 600
    height: int = 650
    left:   int = 100
    top:    int = 100

    def to_dict(self) -> Dict[str, int]:
        return {"width": self.width, "height": self.height,
                "left": self.left,  "top":    self.top}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "WindowConfig":
        defaults = WindowConfig()
        return WindowConfig(
            width  = safe_int(d.get("width"),  defaults.width),
            height = safe_int(d.get("height"), defaults.height),
            left   = safe_int(d.get("left"),   defaults.left),
            top    = safe_int(d.get("top"),     defaults.top),
        )


# ── UI-метаданные темы (порядок полей для Settings) ──────────────────────────

# THEME_FIELDS: список (field_key, i18n_key)
# THEME_GROUPS: список (group_i18n_key, [field_key, ...])
THEME_FIELDS = [
    ("accent_color",   "color_accent"),
    ("header_color",   "color_header"),
    ("switch_color",   "color_switch"),
    ("text_color",     "color_text"),
    ("progress_color", "color_progress"),
    ("button_color",   "color_button"),
    ("appbar_color",   "color_appbar"),
    ("card_color",     "color_card"),
]

THEME_GROUPS = [
    ("theme_group_controls", ["accent_color", "header_color", "switch_color",
                               "text_color", "progress_color", "button_color"]),
    ("theme_group_surfaces", ["appbar_color", "card_color"]),
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


# ── Утилиты ───────────────────────────────────────────────────────────────────

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
