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
    ThemeConfig, WindowConfig, ToolConfig, YtDlpConfig, FfmpegConfig, VersionState,
    DEFAULT_DOWNLOAD_PATH, DEFAULT_PROXY_ADDRESS,
)
from i18l import Locale


def _default_tools() -> Dict[str, ToolConfig]:
    """Дефолтные конфиги инструментов.

    Импорт ленивый: реестр живёт в пакете managers, чей __init__ тянет
    config_manager → state. Тянуть его на верхнем уровне state.py замкнуло бы
    цикл импорта; на момент создания AppState() все модули уже загружены.
    """
    from managers.tool_registry import default_tools_config
    return default_tools_config()


@dataclass
class AppState:
    # ── Настройки загрузки ────────────────────────────────────────────────────
    download_path: str  = field(default_factory=lambda: DEFAULT_DOWNLOAD_PATH)
    proxy_enabled: bool = False
    proxy_address: str  = field(default_factory=lambda: DEFAULT_PROXY_ADDRESS)

    # ── Мета-состояние ────────────────────────────────────────────────────────
    last_check_time:   float = 0.0
    last_needs_update: bool  = False

    # ── Инструменты: СТАТИЧЕСКИЙ конфиг (URL, имена, флаги) ───────────────────
    tools: Dict[str, ToolConfig] = field(default_factory=_default_tools)

    # ── Инструменты: RUNTIME-состояние версий, ключ — имя бинарника ───────────
    # (yt-dlp, ffmpeg, ffplay, ffprobe). Отделено от конфига; заполняется
    # проверкой версий, персистится в секции "tool_versions" config.json.
    tool_versions: Dict[str, VersionState] = field(default_factory=dict)

    # ── Тема и геометрия — типизированные dataclass вместо Dict ──────────────
    theme:    ThemeConfig  = field(default_factory=ThemeConfig)
    window:   WindowConfig = field(default_factory=WindowConfig)
    language: str          = field(default_factory=Locale.default_language)

    # ── Типобезопасный доступ к конфигам инструментов ─────────────────────────
    # Имена инструментов локализованы здесь, а не разбросаны строками по UI.
    # Возвращают конкретный подкласс (с .parameters / .binaries); при отсутствии
    # ключа — пустой дефолт того же типа, чтобы UI не падал на KeyError.

    @property
    def ytdlp(self) -> YtDlpConfig:
        cfg = self.tools.get("yt-dlp")
        return cfg if isinstance(cfg, YtDlpConfig) else YtDlpConfig()

    @property
    def ffmpeg(self) -> FfmpegConfig:
        cfg = self.tools.get("ffmpeg")
        return cfg if isinstance(cfg, FfmpegConfig) else FfmpegConfig()
