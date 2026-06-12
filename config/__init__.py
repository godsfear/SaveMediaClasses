"""
config — пакет конфигурации приложения (бывший монолитный config.py).

Состав:
  constants.py — константы: интервалы, лимиты, сетевые параметры, URL, CLI-флаги
  utils.py     — примитивные хелперы: safe_*, hex-цвета, разбор URL
  theme.py     — оформление: ThemeConfig, UI-метаданные редактора, карты токенов
  runtime.py   — персистируемые настройки окружения: окно, таймауты
  tools.py     — статические конфиги инструментов + VersionState

Все публичные имена реэкспортируются отсюда: `from config import X`
работает как раньше — вызывающим переезд не виден.
"""

from config.constants import (
    CHECK_INTERVAL_SECONDS, DEFAULT_MAX_PARALLEL, MAX_PARALLEL_CEILING,
    CLIPBOARD_POLL_SECONDS, CLIPBOARD_MAX_CHARS, ERROR_TAIL_LINES,
    CARD_LINGER_SECONDS, SEED_LOG_INTERVAL_SECONDS, PERSIST_DEBOUNCE_SECONDS,
    YT_DLP_CHUNK_SIZE, FFMPEG_CHUNK_SIZE, ARIA2_CHUNK_SIZE,
    THUMBNAIL_TIMEOUT, THUMBNAIL_SOCK_TIMEOUT,
    DEFAULT_DOWNLOAD_PATH, DEFAULT_PROXY_ADDRESS,
    DEFAULT_YT_DLP_ARGS, _LEGACY_YT_DLP_ARGS,   # legacy-дефолт нужен тестам миграции
    DEFAULT_YT_API_URL, DEFAULT_YT_DOWNLOAD_URL,
    DEFAULT_FFMPEG_VERSION_URL, DEFAULT_FFMPEG_DOWNLOAD_URL,
    DEFAULT_ARIA2_VERSION_URL, DEFAULT_ARIA2_DOWNLOAD_URL,
    DEFAULT_ARIA2_ARGS, DEFAULT_ARIA2_PART_DIRNAME, DEFAULT_ARIA2_SEED_ARGS,
    COOKIE_BROWSERS,
)
from config.utils import (
    hex_to_flet, is_valid_hex, download_display_name, magnet_btih,
    parse_url_lines, safe_str, safe_int, get_fallback_bool,
)
from config.theme import (
    ThemeConfig, NamedTheme, THEME_FIELDS, THEME_GROUPS, PALETTE,
    SEVERITY_TOKENS, DOWNLOAD_STATUS_TOKENS, TOOL_STATUS_TOKENS,
    token_color, severity_color,
)
from config.runtime import WindowConfig, TimeoutsConfig
from config.tools import (
    DEFAULT_QUALITY_PRESETS, DEFAULT_SUBTITLE_PRESETS,
    VersionState, BinaryDef,
    ParamQuality, ParamSubtitles, ParamAudioOnly, ParamCookies, ParamPlaylist,
    ParamEmbedMetadata, ParamExtraArgs, ParamCleanTitles, ParamSaveToSource,
    YtDlpParameters, ToolConfig, YtDlpConfig, Aria2cParameters, Aria2cConfig,
)
