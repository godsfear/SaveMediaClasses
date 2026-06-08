"""
AppState — единственный источник истины для всего состояния приложения.

Правило: виджеты отображают состояние, но не хранят его.
- Читать из state, записывать в state.
- ConfigManager.save() сериализует state → JSON.
- ConfigManager.load() десериализует JSON → state.
"""

from dataclasses import dataclass, field
from typing import Dict

from config import (
    ThemeConfig, WindowConfig, ToolConfig,
    DEFAULT_DOWNLOAD_PATH, DEFAULT_PROXY_ADDRESS, DEFAULT_YT_DLP_ARGS,
    default_tools_config,
)
from i18l import Locale


@dataclass
class AppState:
    # ── Настройки загрузки ────────────────────────────────────────────────────
    download_path:       str  = field(default_factory=lambda: DEFAULT_DOWNLOAD_PATH)
    proxy_enabled:       bool = False
    proxy_address:       str  = field(default_factory=lambda: DEFAULT_PROXY_ADDRESS)
    audio_only:          bool = False
    cookies_enabled:     bool = False
    cookies_browser:     str  = "none"
    playlist_enabled:    bool = False
    embed_metadata:      bool = True
    yt_dlp_args:         str  = field(default_factory=lambda: DEFAULT_YT_DLP_ARGS)
    clean_titles:        bool = False
    save_to_source_folder: bool = False

    # ── Мета-состояние ────────────────────────────────────────────────────────
    last_check_time:   float = 0.0
    last_needs_update: bool  = False

    # ── Инструменты: конфиг + версионное состояние ────────────────────────────
    tools: Dict[str, ToolConfig] = field(default_factory=default_tools_config)

    # ── Тема и геометрия — типизированные dataclass вместо Dict ──────────────
    theme:    ThemeConfig  = field(default_factory=ThemeConfig)
    window:   WindowConfig = field(default_factory=WindowConfig)
    language: str          = field(default_factory=Locale.default_language)
