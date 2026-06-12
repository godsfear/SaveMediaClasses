"""
config/runtime.py — персистируемые настройки окружения: геометрия окна
и сетевые таймауты.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict

from config.constants import (
    CARD_LINGER_SECONDS, THUMBNAIL_SOCK_TIMEOUT, THUMBNAIL_TIMEOUT,
)
from config.utils import safe_int


@dataclass
class WindowConfig:
    width:  int = 600
    height: int = 650
    left:   int = 100
    top:    int = 100

    @staticmethod
    def _get_screen_metrics() -> tuple[int, int]:
        if os.name == "nt":
            import ctypes
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        return 1920, 1080

    def to_dict(self) -> Dict[str, int]:
        return {"width": self.width, "height": self.height,
                "left": self.left,  "top":    self.top}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "WindowConfig":
        defaults = WindowConfig()
        screen_width, screen_height = WindowConfig._get_screen_metrics()

        width = min(
            safe_int(d.get("width"), defaults.width),
            screen_width
        )

        height = min(
            safe_int(d.get("height"), defaults.height),
            screen_height
        )

        left = min(
            safe_int(d.get("left"), defaults.left),
            max(0, screen_width - width)
        )

        top = min(
            safe_int(d.get("top"), defaults.top),
            max(0, screen_height - height)
        )

        return WindowConfig(
            width  = width,
            height = height,
            left   = max(0, left),
            top    = max(0, top),
        )


@dataclass
class TimeoutsConfig:
    """Сетевые таймауты (секунды), персистятся в config.json — раньше были
    захардкожены в коде (tools_manager, providers)."""
    connect:           float = 5.0    # connect httpx при проверке версий инструментов
    read:              float = 8.0    # read при проверке версий (он же общий лимит запроса)
    version_probe:     float = 5.0    # локальный вызов `<exe> --version`
    tool_download:     float = 30.0   # общий таймаут скачивания инструментов
    thumbnail_connect: float = THUMBNAIL_SOCK_TIMEOUT   # connect при загрузке превью
    thumbnail_read:    float = THUMBNAIL_TIMEOUT        # read при загрузке превью
    thumbnail_meta:    float = 20.0   # таймаут yt-dlp --dump-single-json (метаданные превью)
    card_fade:         float = CARD_LINGER_SECONDS      # задержка карточки до удаления (0 = сразу)

    def to_dict(self) -> Dict[str, float]:
        return {
            "connect":           self.connect,
            "read":              self.read,
            "version_probe":     self.version_probe,
            "tool_download":     self.tool_download,
            "thumbnail_connect": self.thumbnail_connect,
            "thumbnail_read":    self.thumbnail_read,
            "thumbnail_meta":    self.thumbnail_meta,
            "card_fade":         self.card_fade,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TimeoutsConfig":
        r = TimeoutsConfig()
        d = d if isinstance(d, dict) else {}
        def _f(key: str, default: float, allow_zero: bool = False) -> float:
            try:
                v = float(d.get(key))
                return v if (v >= 0 if allow_zero else v > 0) else default
            except (TypeError, ValueError):
                return default
        return TimeoutsConfig(
            connect           = _f("connect",           r.connect),
            read              = _f("read",              r.read),
            version_probe     = _f("version_probe",     r.version_probe),
            tool_download     = _f("tool_download",     r.tool_download),
            thumbnail_connect = _f("thumbnail_connect", r.thumbnail_connect),
            thumbnail_read    = _f("thumbnail_read",    r.thumbnail_read),
            thumbnail_meta    = _f("thumbnail_meta",    r.thumbnail_meta),
            card_fade         = _f("card_fade",         r.card_fade, allow_zero=True),
        )
