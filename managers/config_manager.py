import json
import os
from typing import Any, Dict

from app_logging import get_logger
from config import (
    ThemeConfig, NamedTheme, WindowConfig, TimeoutsConfig, ToolConfig, VersionState,
    MAX_PARALLEL_CEILING,
    safe_str, safe_int, get_fallback_bool,
)
from i18n import Locale
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
                # Полиморфно: подкласс выбирается по типу дефолта (YtDlpConfig / базовый ToolConfig).
                tools[tool_name] = type(tool_default).from_dict(raw_tool, tool_default)
            else:
                tools[tool_name] = tool_default

        tool_versions = self._load_tool_versions(raw, tools_raw)
        theme_mode, theme_dark, theme_light, saved_themes = self._load_themes(raw)

        return AppState(
            download_path     = dp,
            proxy_enabled     = fb_bool(cfg, "proxy_enabled", defaults.proxy_enabled),
            proxy_address     = fb_str(cfg,  "proxy_address",  defaults.proxy_address),
            download_tool     = fb_str(cfg,  "download_tool",  defaults.download_tool),
            max_parallel      = max(1, min(MAX_PARALLEL_CEILING,
                                           safe_int(cfg.get("max_parallel"), defaults.max_parallel))),
            clipboard_watch   = fb_bool(cfg, "clipboard_watch", defaults.clipboard_watch),
            last_check_time   = float(cfg.get("last_check_time",  defaults.last_check_time)),
            last_needs_update = bool(cfg.get("last_needs_update",  defaults.last_needs_update)),
            tools         = tools,
            tool_versions = tool_versions,
            theme_mode   = theme_mode,
            theme_dark   = theme_dark,
            theme_light  = theme_light,
            saved_themes = saved_themes,
            window   = WindowConfig.from_dict(raw.get("window", {})),
            language = Locale.resolve_language(raw.get("language") or defaults.language),
            timeouts = TimeoutsConfig.from_dict(raw.get("timeouts", {})),
        )

    @staticmethod
    def _load_themes(raw: Dict[str, Any]):
        """Загрузить режим + две палитры + именованные наборы из блока "theme".

        Поддерживаются три формата (мягкая миграция):
          • новый      — "theme": {mode, dark, light, saved};
          • переходный — ключи theme_mode/theme_dark/theme_light/saved_themes в корне;
          • старейший  — "theme" = одна палитра (становится тёмной)."""
        block = raw.get("theme")
        block = block if isinstance(block, dict) else {}
        is_container = any(k in block for k in ("mode", "dark", "light", "saved"))

        if is_container:
            src_mode, src_dark = block.get("mode"), block.get("dark")
            src_light, src_saved = block.get("light"), block.get("saved")
            legacy_single: Dict[str, Any] = {}
        else:
            src_mode, src_dark = raw.get("theme_mode"), raw.get("theme_dark")
            src_light, src_saved = raw.get("theme_light"), raw.get("saved_themes")
            legacy_single = block   # старый одиночный "theme" → тёмная палитра

        mode = safe_str(src_mode) or "dark"
        mode = "light" if mode == "light" else "dark"

        dark_raw = src_dark if isinstance(src_dark, dict) else legacy_single
        theme_dark = ThemeConfig.from_dict(dark_raw)

        theme_light = (ThemeConfig.from_dict(src_light)
                       if isinstance(src_light, dict) else ThemeConfig.light_default())

        saved: Dict[str, NamedTheme] = {}
        if isinstance(src_saved, dict):
            for name, entry in src_saved.items():
                if isinstance(entry, dict):
                    saved[name] = NamedTheme.from_dict(entry)
        return mode, theme_dark, theme_light, saved

    @staticmethod
    def _load_tool_versions(raw: Dict[str, Any], tools_raw: Any) -> Dict[str, VersionState]:
        """Загрузить runtime-версии из секции "tool_versions".

        Мягкая миграция: если секции нет (старый формат), собрать версии из
        legacy-полей tools.*.current/latest/status и tools.*.binaries.*.* —
        чтобы при первом запуске не терять отображение и не форсить пере-проверку.
        """
        tv_raw = raw.get("tool_versions")
        if isinstance(tv_raw, dict):
            return {
                name: VersionState.from_dict(d)
                for name, d in tv_raw.items() if isinstance(d, dict)
            }

        versions: Dict[str, VersionState] = {}
        if isinstance(tools_raw, dict):
            for tool_name, raw_tool in tools_raw.items():
                if not isinstance(raw_tool, dict):
                    continue
                if any(k in raw_tool for k in ("current", "latest", "status")):
                    versions[tool_name] = VersionState.from_dict(raw_tool)
                legacy_bins = raw_tool.get("binaries", {})
                if isinstance(legacy_bins, dict):
                    for bin_name, bin_data in legacy_bins.items():
                        if isinstance(bin_data, dict) and any(
                            k in bin_data for k in ("current", "latest", "status")
                        ):
                            versions[bin_name] = VersionState.from_dict(bin_data)
        return versions

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
                "download_tool":     state.download_tool,
                "max_parallel":      state.max_parallel,
                "clipboard_watch":   state.clipboard_watch,
                "last_check_time":   state.last_check_time,
                "last_needs_update": state.last_needs_update,
            },
            "tools":         {k: v.to_dict() for k, v in state.tools.items()},
            "tool_versions": {k: v.to_dict() for k, v in state.tool_versions.items()},
            "window":   state.window.to_dict(),
            "timeouts": state.timeouts.to_dict(),
            "theme": {
                "mode":  state.theme_mode,
                "dark":  state.theme_dark.to_dict(),
                "light": state.theme_light.to_dict(),
                "saved": {k: v.to_dict() for k, v in state.saved_themes.items()},
            },
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
