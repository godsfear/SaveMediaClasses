import json
import os
from typing import Any, Dict

from app_logging import get_logger
from config import (
    ThemeConfig, WindowConfig,
    safe_str, safe_int, get_fallback_bool,
)
from i18l import Locale
from state import AppState, ToolVersionInfo


def _load_tool_versions(raw: dict) -> dict:
    result = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            result[k] = ToolVersionInfo(
                current=v.get("current", ""),
                latest=v.get("latest", ""),
                status=v.get("status", ""),
            )
        elif isinstance(v, (list, tuple)) and len(v) == 3:
            # backward-compat: старый формат ["current", "latest", "status"]
            result[k] = ToolVersionInfo(current=v[0], latest=v[1], status=v[2])
    return result


class ConfigManager:

    def __init__(self, config_file: str) -> None:
        self.config_file = config_file
        self._log = get_logger("app")

    # ── Загрузка ──────────────────────────────────────────────────────────────

    def load(self) -> AppState:
        """Читает config.json и возвращает заполненный AppState.
        При любой ошибке возвращает AppState с дефолтами."""
        defaults = AppState()
        raw = self._read_raw()
        if raw is None:
            return defaults

        cfg  = raw.get("settings", {}) if isinstance(raw.get("settings"), dict) else {}
        urls = cfg.get("urls", {})     if isinstance(cfg.get("urls"), dict)      else {}

        def fb_str(d: dict, k: str, default: str) -> str:
            v = d.get(k)
            return default if v is None or v == "" else str(v)

        def fb_bool(d: dict, k: str, default: bool) -> bool:
            return get_fallback_bool(d, k, default)

        dp = fb_str(cfg, "download_path", "")
        if not dp:
            dp = defaults.download_path

        return AppState(
            download_path         = dp,
            proxy_enabled         = fb_bool(cfg, "proxy_enabled",       defaults.proxy_enabled),
            proxy_address         = fb_str(cfg,  "proxy_address",        defaults.proxy_address),
            audio_only            = fb_bool(cfg, "audio_only",           defaults.audio_only),
            cookies_enabled       = fb_bool(cfg, "cookies_enabled",      defaults.cookies_enabled),
            cookies_browser       = fb_str(cfg,  "cookies_browser",      defaults.cookies_browser),
            playlist_enabled      = fb_bool(cfg, "playlist_enabled",     defaults.playlist_enabled),
            embed_metadata        = fb_bool(cfg, "embed_metadata",       defaults.embed_metadata),
            yt_dlp_args           = fb_str(cfg,  "yt_dlp_args",          defaults.yt_dlp_args),
            clean_titles          = fb_bool(cfg, "clean_titles",         defaults.clean_titles),
            save_to_source_folder = fb_bool(cfg, "save_to_source_folder", defaults.save_to_source_folder),
            url_yt_api            = fb_str(urls, "yt_api",          defaults.url_yt_api),
            url_yt_download       = fb_str(urls, "yt_download",     defaults.url_yt_download),
            url_ffmpeg_version    = fb_str(urls, "ffmpeg_version",  defaults.url_ffmpeg_version),
            url_ffmpeg_download   = fb_str(urls, "ffmpeg_download", defaults.url_ffmpeg_download),
            last_check_time       = float(cfg.get("last_check_time",  defaults.last_check_time)),
            last_needs_update     = bool(cfg.get("last_needs_update", defaults.last_needs_update)),
            tool_versions         = _load_tool_versions(cfg.get("tool_versions", {})),
            theme    = ThemeConfig.from_dict(raw.get("theme", {})),
            window   = WindowConfig.from_dict(raw.get("window", {})),
            language = Locale.resolve_language(raw.get("language") or defaults.language),
        )

    def load_window_geometry(self) -> WindowConfig:
        """Быстрое чтение только геометрии окна до полной загрузки."""
        raw = self._read_raw()
        if raw and isinstance(raw.get("window"), dict):
            return WindowConfig.from_dict(raw["window"])
        return WindowConfig()

    # ── Сохранение ────────────────────────────────────────────────────────────

    def save(self, state: AppState) -> None:
        """Сериализует AppState → config.json."""
        data = {
            "settings": {
                "download_path":         state.download_path,
                "proxy_address":         state.proxy_address,
                "proxy_enabled":         state.proxy_enabled,
                "yt_dlp_args":           state.yt_dlp_args,
                "audio_only":            state.audio_only,
                "cookies_browser":       state.cookies_browser,
                "cookies_enabled":       state.cookies_enabled,
                "embed_metadata":        state.embed_metadata,
                "playlist_enabled":      state.playlist_enabled,
                "clean_titles":          state.clean_titles,
                "save_to_source_folder": state.save_to_source_folder,
                "last_check_time":       state.last_check_time,
                "last_needs_update":     state.last_needs_update,
                "tool_versions":         {
                    k: {"current": v.current, "latest": v.latest, "status": v.status}
                    for k, v in state.tool_versions.items()
                },
                "urls": {
                    "yt_api":          state.url_yt_api,
                    "yt_download":     state.url_yt_download,
                    "ffmpeg_version":  state.url_ffmpeg_version,
                    "ffmpeg_download": state.url_ffmpeg_download,
                },
            },
            "window":   state.window.to_dict(),
            "theme":    state.theme.to_dict(),
            "language": state.language,
        }
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except OSError:
            self._log.exception("Failed to save config: %s", self.config_file)

    # ── Приватное ─────────────────────────────────────────────────────────────

    def _read_raw(self) -> Dict[str, Any] | None:
        if not os.path.exists(self.config_file):
            return None
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else None
        except Exception:
            self._log.exception("Failed to read config: %s", self.config_file)
            return None
