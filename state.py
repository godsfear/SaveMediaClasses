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
    ThemeConfig, WindowConfig,
    DEFAULT_DOWNLOAD_PATH, DEFAULT_PROXY_ADDRESS, DEFAULT_YT_DLP_ARGS,
    DEFAULT_YT_API_URL, DEFAULT_YT_DOWNLOAD_URL,
    DEFAULT_FFMPEG_VERSION_URL, DEFAULT_FFMPEG_DOWNLOAD_URL,
)


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

    # ── Сервисные URL ─────────────────────────────────────────────────────────
    url_yt_api:          str = field(default_factory=lambda: DEFAULT_YT_API_URL)
    url_yt_download:     str = field(default_factory=lambda: DEFAULT_YT_DOWNLOAD_URL)
    url_ffmpeg_version:  str = field(default_factory=lambda: DEFAULT_FFMPEG_VERSION_URL)
    url_ffmpeg_download: str = field(default_factory=lambda: DEFAULT_FFMPEG_DOWNLOAD_URL)

    # ── Мета-состояние ────────────────────────────────────────────────────────
    last_check_time:   float = 0.0
    last_needs_update: bool  = False
    # Результаты последней проверки: {"yt-dlp": (local, remote, status_key), ...}
    # status_key: "ok" | "outdated" | "missing" | "error"
    tool_versions: Dict[str, tuple] = field(default_factory=dict)

    # ── Тема и геометрия — типизированные dataclass вместо Dict ──────────────
    theme:    ThemeConfig  = field(default_factory=ThemeConfig)
    window:   WindowConfig = field(default_factory=WindowConfig)
    language: str          = "ru"
