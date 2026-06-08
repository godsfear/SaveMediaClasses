import json
import os
from typing import Any, Dict

from app_logging import get_logger
from config import (
    ThemeConfig, WindowConfig, ToolConfig,
    safe_str, safe_int, get_fallback_bool,
)
from i18l import Locale
from state import AppState


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

        cfg = raw.get("settings", {}) if isinstance(raw.get("settings"), dict) else {}

        def fb_str(d: dict, k: str, default: str) -> str:
            v = d.get(k)
            return default if v is None or v == "" else str(v)

        def fb_bool(d: dict, k: str, default: bool) -> bool:
            return get_fallback_bool(d, k, default)

        dp = fb_str(cfg, "download_path", "")
        if not dp:
            dp = defaults.download_path

        tools_raw = raw.get("tools", {})
        tools = {}
        for tool_name, tool_default in defaults.tools.items():
            raw_tool = tools_raw.get(tool_name, {}) if isinstance(tools_raw, dict) else {}
            if isinstance(raw_tool, dict):
                tools[tool_name] = ToolConfig.from_dict(raw_tool, tool_default)
            else:
                tools[tool_name] = tool_default

        return AppState(
            download_path     = dp,
            proxy_enabled     = fb_bool(cfg, "proxy_enabled", defaults.proxy_enabled),
            proxy_address     = fb_str(cfg,  "proxy_address",  defaults.proxy_address),
            last_check_time   = float(cfg.get("last_check_time",  defaults.last_check_time)),
            last_needs_update = bool(cfg.get("last_needs_update",  defaults.last_needs_update)),
            tools    = tools,
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
                "download_path":     state.download_path,
                "proxy_address":     state.proxy_address,
                "proxy_enabled":     state.proxy_enabled,
                "last_check_time":   state.last_check_time,
                "last_needs_update": state.last_needs_update,
            },
            "tools":    {k: v.to_dict() for k, v in state.tools.items()},
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
