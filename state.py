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
    ThemeConfig, NamedTheme, WindowConfig, ToolConfig, YtDlpConfig, VersionState,
    DEFAULT_DOWNLOAD_PATH, DEFAULT_PROXY_ADDRESS,
)
from i18l import Locale


# Импорты реестра ленивые: он живёт в пакете managers, чей __init__ тянет
# config_manager → state. Импорт на верхнем уровне state.py замкнул бы цикл;
# на момент вызова (создание AppState / доступ к property) всё уже загружено.

def _default_tools() -> Dict[str, ToolConfig]:
    """Дефолтные конфиги всех инструментов (фабрика поля tools)."""
    from managers.tool_registry import default_tools_config
    return default_tools_config()


def _tool_default(name: str) -> ToolConfig:
    """Дефолтный конфиг конкретного инструмента из реестра — fallback для аксессоров."""
    from managers.tool_registry import DEFAULT_TOOLS
    for tool in DEFAULT_TOOLS:
        if tool.name == name:
            return tool.default_config()
    return ToolConfig()


@dataclass
class AppState:
    # ── Настройки загрузки ────────────────────────────────────────────────────
    download_path: str  = field(default_factory=lambda: DEFAULT_DOWNLOAD_PATH)
    proxy_enabled: bool = False
    proxy_address: str  = field(default_factory=lambda: DEFAULT_PROXY_ADDRESS)
    # Выбранный загрузчик (ключ провайдера: "yt-dlp" | "aria2c"). Запоминается между сессиями.
    download_tool: str  = "yt-dlp"

    # ── Мета-состояние ────────────────────────────────────────────────────────
    last_check_time:   float = 0.0
    last_needs_update: bool  = False

    # ── Инструменты: СТАТИЧЕСКИЙ конфиг (URL, имена, флаги) ───────────────────
    tools: Dict[str, ToolConfig] = field(default_factory=_default_tools)

    # ── Инструменты: RUNTIME-состояние версий, ключ — имя бинарника ───────────
    # (yt-dlp, ffmpeg, ffplay, ffprobe). Отделено от конфига; заполняется
    # проверкой версий, персистится в секции "tool_versions" config.json.
    tool_versions: Dict[str, VersionState] = field(default_factory=dict)

    # ── Тема: режим (отдельная ось) + две всегда-живые палитры ───────────────
    # theme_mode выбирает активную палитру; редактируются независимо. Именованные
    # наборы (saved_themes) — отдельные снимки, каждый помнит свой mode.
    theme_mode:  str         = "dark"
    theme_dark:  ThemeConfig = field(default_factory=ThemeConfig.dark_default)
    theme_light: ThemeConfig = field(default_factory=ThemeConfig.light_default)
    saved_themes: Dict[str, NamedTheme] = field(default_factory=dict)

    # ── Геометрия и язык ──────────────────────────────────────────────────────
    window:   WindowConfig = field(default_factory=WindowConfig)
    language: str          = field(default_factory=Locale.default_language)

    # ── Активная палитра по режиму (совместимость со всеми чтениями .theme) ───
    @property
    def theme(self) -> ThemeConfig:
        return self.theme_light if self.theme_mode == "light" else self.theme_dark

    # ── Типобезопасный доступ к конфигам инструментов ─────────────────────────
    # Имена инструментов локализованы здесь, а не разбросаны строками по UI.
    # При отсутствии/неверном типе ключа — настоящий дефолт инструмента из
    # реестра (с реальными URL), а не пустышка.

    @property
    def ytdlp(self) -> YtDlpConfig:
        cfg = self.tools.get("yt-dlp")
        if isinstance(cfg, YtDlpConfig):
            return cfg
        return _tool_default("yt-dlp")  # type: ignore[return-value]

    @property
    def ffmpeg(self) -> ToolConfig:
        cfg = self.tools.get("ffmpeg")
        return cfg if isinstance(cfg, ToolConfig) else _tool_default("ffmpeg")

    @property
    def aria2c(self) -> ToolConfig:
        cfg = self.tools.get("aria2c")
        return cfg if isinstance(cfg, ToolConfig) else _tool_default("aria2c")
