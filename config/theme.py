"""
config/theme.py — оформление: семантические токены (ThemeConfig), именованные
наборы, UI-метаданные редактора темы (порядок и группировка полей, палитра)
и карты «семантический ключ → токен» с функциями перевода в цвет.
"""

from dataclasses import dataclass, field, fields
from typing import Any, Dict

from config.utils import hex_to_flet, safe_str


@dataclass
class ThemeConfig:
    """Семантические токены оформления. Дефолты поля = тёмная палитра, поэтому
    ThemeConfig() == dark_default() (важно для фолбэков from_dict).

    Светлая палитра — отдельная фабрика light_default(). Режим (dark/light) живёт
    в AppState.theme_mode и выбирает активную из двух палитр; цвета каждой палитры
    редактируются независимо.
    """
    # ── Управляющие элементы ──────────────────────────────────────────────────
    accent_color:      str = "00B4D8"
    switch_color:      str = "4CAF50"
    header_color:      str = "00B4D8"
    progress_color:    str = "4CAF50"
    button_color:      str = "4CAF50"
    button_text_color: str = "FFFFFF"

    # ── Текст ─────────────────────────────────────────────────────────────────
    text_color:           str = "E0E0E0"
    text_secondary_color: str = "BDBDBD"
    text_muted_color:     str = "9E9E9E"

    # ── Фоны и поверхности ────────────────────────────────────────────────────
    bg_color:         str = "121212"
    appbar_color:     str = "1c1c1c"
    bottom_bar_color: str = "141414"
    card_color:       str = "161616"
    surface_color:    str = "1A1A1A"
    border_color:     str = "2A2A2A"

    # ── Статусы загрузок ──────────────────────────────────────────────────────
    status_ok_color:      str = "66BB6A"
    status_error_color:   str = "EF5350"
    status_warning_color: str = "FFA726"
    status_running_color: str = "42A5F5"

    def to_dict(self) -> Dict[str, str]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @staticmethod
    def from_dict(d: Dict[str, str]) -> "ThemeConfig":
        """Мягкая миграция: отсутствующие/пустые ключи берутся из тёмных дефолтов."""
        defaults = ThemeConfig()
        d = d if isinstance(d, dict) else {}
        return ThemeConfig(**{
            f.name: (safe_str(d.get(f.name)) or getattr(defaults, f.name))
            for f in fields(ThemeConfig)
        })

    @classmethod
    def dark_default(cls) -> "ThemeConfig":
        return cls()

    @classmethod
    def light_default(cls) -> "ThemeConfig":
        return cls(
            accent_color="0288D1", switch_color="43A047", header_color="0277BD",
            progress_color="43A047", button_color="43A047", button_text_color="FFFFFF",
            text_color="212121", text_secondary_color="616161", text_muted_color="9E9E9E",
            bg_color="FAFAFA", appbar_color="ECEFF1", bottom_bar_color="ECEFF1",
            card_color="FFFFFF", surface_color="F5F5F5", border_color="E0E0E0",
            status_ok_color="2E7D32", status_error_color="C62828",
            status_warning_color="EF6C00", status_running_color="1565C0",
        )


@dataclass
class NamedTheme:
    """Снимок палитры под именем + режим, для которого она задумана."""
    mode:   str = "dark"
    config: ThemeConfig = field(default_factory=ThemeConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {"mode": self.mode, "colors": self.config.to_dict()}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "NamedTheme":
        d = d if isinstance(d, dict) else {}
        mode = safe_str(d.get("mode")) or "dark"
        return NamedTheme(
            mode   = "light" if mode == "light" else "dark",
            config = ThemeConfig.from_dict(d.get("colors", {})),
        )


# ── UI-метаданные темы (порядок полей для Settings) ──────────────────────────

# THEME_FIELDS: список (field_key, i18n_key)
# THEME_GROUPS: список (group_i18n_key, [field_key, ...])
THEME_FIELDS = [
    ("accent_color",         "color_accent"),
    ("header_color",         "color_header"),
    ("switch_color",         "color_switch"),
    ("progress_color",       "color_progress"),
    ("button_color",         "color_button"),
    ("button_text_color",    "color_button_text"),
    ("text_color",           "color_text"),
    ("text_secondary_color", "color_text_secondary"),
    ("text_muted_color",     "color_text_muted"),
    ("bg_color",             "color_bg"),
    ("appbar_color",         "color_appbar"),
    ("bottom_bar_color",     "color_bottom_bar"),
    ("card_color",           "color_card"),
    ("surface_color",        "color_surface"),
    ("border_color",         "color_border"),
    ("status_ok_color",      "color_status_ok"),
    ("status_error_color",   "color_status_error"),
    ("status_warning_color", "color_status_warning"),
    ("status_running_color", "color_status_running"),
]

THEME_GROUPS = [
    ("theme_group_controls", ["accent_color", "header_color", "switch_color",
                               "progress_color", "button_color", "button_text_color"]),
    ("theme_group_text",     ["text_color", "text_secondary_color", "text_muted_color"]),
    ("theme_group_surfaces", ["bg_color", "appbar_color", "bottom_bar_color",
                               "card_color", "surface_color", "border_color"]),
    ("theme_group_status",   ["status_ok_color", "status_error_color",
                               "status_warning_color", "status_running_color"]),
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


# ── Карты «семантический ключ → токен ThemeConfig» ────────────────────────────
# События и записи БД несут только семантику; в конкретный цвет её переводит
# UI-слой по активной теме через token_color()/severity_color().

# Severity статусных событий шины ("ok"|"warning"|"error"|"info").
SEVERITY_TOKENS = {
    "ok":      "status_ok_color",
    "warning": "status_warning_color",
    "error":   "status_error_color",
    "info":    "text_secondary_color",
}

# Статусы загрузок (история/БД).
DOWNLOAD_STATUS_TOKENS = {
    "completed":  "status_ok_color",
    "failed":     "status_error_color",
    "cancelled":  "status_warning_color",
    "running":    "status_running_color",
    "incomplete": "status_warning_color",
    "seeding":    "status_running_color",
}

# Статусы проверки версий инструментов (tool_specs.classify_version).
TOOL_STATUS_TOKENS = {
    "ok":       "status_ok_color",
    "outdated": "status_warning_color",
    "missing":  "status_error_color",
    "error":    "status_warning_color",
}


def token_color(t: ThemeConfig, token_map: Dict[str, str], key: str,
                fallback: str = "text_muted_color") -> str:
    """Flet-цвет по карте «ключ → токен» из активной палитры."""
    return hex_to_flet(getattr(t, token_map.get(key, fallback)))


def severity_color(t: ThemeConfig, severity: str) -> str:
    """Flet-цвет для severity события из токенов активной темы."""
    return token_color(t, SEVERITY_TOKENS, severity, "text_secondary_color")
