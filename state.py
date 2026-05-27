"""
AppState — единственный источник истины для всего состояния приложения.

Правило: виджеты отображают состояние, но не хранят его.
- Читать из state, записывать в state.
- save_config() сериализует state → JSON.
- load_config() десериализует JSON → state и синхронизирует виджеты.
"""

import os
from dataclasses import dataclass, field
from typing import Dict

from config import DEFAULT_CONFIG


@dataclass
class AppState:
    # ── Настройки загрузки ────────────────────────────────────────────────────
    download_path: str = ""
    proxy_enabled: bool = False
    proxy_address: str = ""
    audio_only: bool = False
    cookies_enabled: bool = False
    cookies_browser: str = "none"
    playlist_enabled: bool = False
    embed_metadata: bool = True
    yt_dlp_args: str = ""
    clean_titles: bool = False
    save_to_source_folder: bool = False

    # ── Сервисные URL ─────────────────────────────────────────────────────────
    url_yt_api: str = ""
    url_yt_download: str = ""
    url_ffmpeg_version: str = ""
    url_ffmpeg_download: str = ""

    # ── Мета-состояние ────────────────────────────────────────────────────────
    last_check_time: float = 0.0
    last_needs_update: bool = False
    # Результаты последней проверки: {"yt-dlp": (local, remote, status_key), ...}
    # status_key: "ok" | "outdated" | "missing" | "error"
    tool_versions: Dict[str, tuple] = field(default_factory=dict)

    # ── Тема ──────────────────────────────────────────────────────────────────
    theme: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CONFIG["theme"]))

    # ── Геометрия окна ────────────────────────────────────────────────────────
    window: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_CONFIG["window"]))

    # ── Вспомогательные свойства ──────────────────────────────────────────────

    def download_opts(self) -> dict:
        """Параметры для Downloader.build_command() — берутся только из state."""
        return {
            "download_path":   self.download_path,
            "proxy_enabled":   self.proxy_enabled,
            "proxy_address":   self.proxy_address,
            "cookies_enabled": self.cookies_enabled,
            "cookies_browser": self.cookies_browser,
            "playlist_enabled": self.playlist_enabled,
            "embed_metadata":  self.embed_metadata,
            "audio_only":      self.audio_only,
            "yt_dlp_args":     self.yt_dlp_args,
            "clean_titles":    self.clean_titles,
            "save_to_source":  self.save_to_source_folder,
        }

    @staticmethod
    def defaults() -> "AppState":
        """AppState с дефолтными значениями из DEFAULT_CONFIG."""
        cfg = DEFAULT_CONFIG["settings"]
        urls = cfg["urls"]
        return AppState(
            download_path       = os.path.join(os.path.expanduser("~"), "Downloads"),
            proxy_enabled       = bool(cfg["proxy_enabled"]),
            proxy_address       = str(cfg["proxy_address"]),
            audio_only          = bool(cfg["audio_only"]),
            cookies_enabled     = bool(cfg["cookies_enabled"]),
            cookies_browser     = str(cfg["cookies_browser"]),
            playlist_enabled    = bool(cfg["playlist_enabled"]),
            embed_metadata      = bool(cfg["embed_metadata"]),
            yt_dlp_args         = str(cfg["yt_dlp_args"]),
            clean_titles        = bool(cfg["clean_titles"]),
            save_to_source_folder = bool(cfg["save_to_source_folder"]),
            url_yt_api          = str(urls["yt_api"]),
            url_yt_download     = str(urls["yt_download"]),
            url_ffmpeg_version  = str(urls["ffmpeg_version"]),
            url_ffmpeg_download = str(urls["ffmpeg_download"]),
            last_check_time     = float(cfg["last_check_time"]),
            last_needs_update   = bool(cfg["last_needs_update"]),
            theme               = dict(DEFAULT_CONFIG["theme"]),
            window              = dict(DEFAULT_CONFIG["window"]),
        )
