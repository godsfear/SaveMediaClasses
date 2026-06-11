import os
from dataclasses import dataclass, field, fields, replace
from typing import Any, Dict

# ── Константы приложения ──────────────────────────────────────────────────────

CHECK_INTERVAL_SECONDS = 6 * 3600
DEFAULT_MAX_PARALLEL   = 5       # одновременных загрузок по умолчанию (settings.max_parallel)
MAX_PARALLEL_CEILING   = 50      # верхняя граница клампа (защита от опечатки в config.json)
CLIPBOARD_POLL_SECONDS = 1.0     # период опроса буфера обмена (слежение за ссылками)
CLIPBOARD_MAX_CHARS    = 4000    # длиннее — это документ, а не ссылки; игнорируем
ERROR_TAIL_LINES       = 20      # сколько последних строк вывода хранить для диагностики ошибки
CARD_LINGER_SECONDS    = 3       # сколько карточка висит после финала/паузы перед удалением
SEED_LOG_INTERVAL_SECONDS = 600  # как часто логировать строку раздачи aria2 (SEED спамит ~1/с)

# ── Сетевые константы (chunk / timeout) ──────────────────────────────────────
YT_DLP_CHUNK_SIZE      = 8_192   # байт/итерацию при скачивании yt-dlp
FFMPEG_CHUNK_SIZE      = 16_384  # байт/итерацию при скачивании ffmpeg zip
ARIA2_CHUNK_SIZE       = 16_384  # байт/итерацию при скачивании aria2 zip
THUMBNAIL_TIMEOUT      = 15.0    # секунд — общий async-таймаут скачивания thumbnail
THUMBNAIL_SOCK_TIMEOUT = 10      # секунд — connect-таймаут httpx для thumbnail

DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "Downloads")
DEFAULT_PROXY_ADDRESS = "socks5://127.0.0.1:1080"
# Дополнительные аргументы yt-dlp. Формата (-f) здесь больше НЕТ — выбором
# формата владеют пресеты качества (DEFAULT_QUALITY_PRESETS): при "best" yt-dlp
# использует свой встроенный дефолт bestvideo*+bestaudio/best (тот же результат),
# при явном пресете его -f добавляется после этих аргументов.
DEFAULT_YT_DLP_ARGS   = "--merge-output-format mp4"
# Старый дефолт (формат + контейнер) — для мягкой миграции сохранённых конфигов.
_LEGACY_YT_DLP_ARGS   = "-f bestvideo+bestaudio/best --merge-output-format mp4"

DEFAULT_YT_API_URL          = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
DEFAULT_YT_DOWNLOAD_URL     = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    if os.name == "nt" else
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
)
DEFAULT_FFMPEG_VERSION_URL  = "https://www.gyan.dev/ffmpeg/builds/release-version"
DEFAULT_FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip"

# aria2 публикует релизы на GitHub. Имя ассета содержит версию
# (aria2-X.Y.Z-win-64bit-buildN.zip), поэтому стабильного "latest"-URL на сам
# zip нет: и проверка версии, и установка идут через releases/latest API —
# Aria2cTool.install() сам находит нужный ассет в ответе. Отсюда оба URL равны.
DEFAULT_ARIA2_VERSION_URL   = "https://api.github.com/repos/aria2/aria2/releases/latest"
DEFAULT_ARIA2_DOWNLOAD_URL  = "https://api.github.com/repos/aria2/aria2/releases/latest"

# Фиксированные CLI-флаги aria2c для скачивания. ВАЖНО (от них зависит логика
# приложения): --summary-interval=0 (парсинг прогресса по \r-строке без спама),
# --auto-save-interval=1 (контрольный .aria2 актуален для pause/resume),
# --continue=true (докачка), --seed-time=0 (не сидировать торрент после докачки).
DEFAULT_ARIA2_ARGS          = ("--summary-interval=0 --console-log-level=warn "
                               "--continue=true --auto-file-renaming=false "
                               "--allow-overwrite=true --auto-save-interval=1 --seed-time=0")
DEFAULT_ARIA2_PART_DIRNAME  = ".part"   # подпапка временных загрузок в папке назначения
# Флаги РАЗДАЧИ (seed): проверить уже скачанные файлы и раздавать без лимита по
# ratio (0.0 = без лимита), пока пользователь не остановит. --check-integrity нужен,
# т.к. контрольный .aria2 удаляется после докачки (его перемещаем/чистим).
DEFAULT_ARIA2_SEED_ARGS     = ("--summary-interval=0 --console-log-level=warn "
                               "--check-integrity=true --seed-ratio=0.0 --bt-detach-seed-only=false")


# ── Typed конфиги (вместо Dict) ───────────────────────────────────────────────

@dataclass
class ThemeConfig:
    """Семантические токены оформления. Дефолты поля = тёмная палитра, поэтому
    ThemeConfig() == dark_default() (важно для фолбэков from_dict).

    Светлая палитра — отдельная фабрика light_default(). Режим (dark/light) живёт
    в AppState.theme_mode и выбирает активную из двух палитр; цвета каждой палитры
    редактируются независимо.
    """
    # ── Управляющие элементы ──────────────────────────────────────────────────
    accent_color:      str = "00B4D8"
    switch_color:      str = "4CAF50"
    header_color:      str = "00B4D8"
    progress_color:    str = "4CAF50"
    button_color:      str = "4CAF50"
    button_text_color: str = "FFFFFF"

    # ── Текст ─────────────────────────────────────────────────────────────────
    text_color:           str = "E0E0E0"
    text_secondary_color: str = "BDBDBD"
    text_muted_color:     str = "9E9E9E"

    # ── Фоны и поверхности ────────────────────────────────────────────────────
    bg_color:         str = "121212"
    appbar_color:     str = "1c1c1c"
    bottom_bar_color: str = "141414"
    card_color:       str = "161616"
    surface_color:    str = "1A1A1A"
    border_color:     str = "2A2A2A"

    # ── Статусы загрузок ──────────────────────────────────────────────────────
    status_ok_color:      str = "66BB6A"
    status_error_color:   str = "EF5350"
    status_warning_color: str = "FFA726"
    status_running_color: str = "42A5F5"

    def to_dict(self) -> Dict[str, str]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @staticmethod
    def from_dict(d: Dict[str, str]) -> "ThemeConfig":
        """Мягкая миграция: отсутствующие/пустые ключи берутся из тёмных дефолтов."""
        defaults = ThemeConfig()
        d = d if isinstance(d, dict) else {}
        return ThemeConfig(**{
            f.name: (safe_str(d.get(f.name)) or getattr(defaults, f.name))
            for f in fields(ThemeConfig)
        })

    @classmethod
    def dark_default(cls) -> "ThemeConfig":
        return cls()

    @classmethod
    def light_default(cls) -> "ThemeConfig":
        return cls(
            accent_color="0288D1", switch_color="43A047", header_color="0277BD",
            progress_color="43A047", button_color="43A047", button_text_color="FFFFFF",
            text_color="212121", text_secondary_color="616161", text_muted_color="9E9E9E",
            bg_color="FAFAFA", appbar_color="ECEFF1", bottom_bar_color="ECEFF1",
            card_color="FFFFFF", surface_color="F5F5F5", border_color="E0E0E0",
            status_ok_color="2E7D32", status_error_color="C62828",
            status_warning_color="EF6C00", status_running_color="1565C0",
        )


@dataclass
class NamedTheme:
    """Снимок палитры под именем + режим, для которого она задумана."""
    mode:   str = "dark"
    config: ThemeConfig = field(default_factory=ThemeConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {"mode": self.mode, "colors": self.config.to_dict()}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "NamedTheme":
        d = d if isinstance(d, dict) else {}
        mode = safe_str(d.get("mode")) or "dark"
        return NamedTheme(
            mode   = "light" if mode == "light" else "dark",
            config = ThemeConfig.from_dict(d.get("colors", {})),
        )


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
    read:              float = 8.0    # read при проверке версий
    tool_download:     float = 30.0   # общий таймаут скачивания инструментов
    thumbnail_connect: float = THUMBNAIL_SOCK_TIMEOUT   # connect при загрузке превью
    thumbnail_read:    float = THUMBNAIL_TIMEOUT        # read при загрузке превью
    thumbnail_meta:    float = 20.0   # таймаут yt-dlp --dump-single-json (метаданные превью)
    card_fade:         float = CARD_LINGER_SECONDS      # задержка карточки до удаления (0 = сразу)

    def to_dict(self) -> Dict[str, float]:
        return {
            "connect":           self.connect,
            "read":              self.read,
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
            tool_download     = _f("tool_download",     r.tool_download),
            thumbnail_connect = _f("thumbnail_connect", r.thumbnail_connect),
            thumbnail_read    = _f("thumbnail_read",    r.thumbnail_read),
            thumbnail_meta    = _f("thumbnail_meta",    r.thumbnail_meta),
            card_fade         = _f("card_fade",         r.card_fade, allow_zero=True),
        )

# ── Конфигурация инструментов ────────────────────────────────────────────────
#
# Разделение ответственности:
#   • ToolConfig / YtDlpConfig / BinaryDef — СТАТИЧЕСКАЯ конфигурация: URL,
#     имена файлов, флаги. Редактируется пользователем, персистится в "tools".
#   • VersionState — RUNTIME-состояние версий (current/latest/status), которое
#     контроллер обновляет при проверке. Персистится отдельно, в секции
#     "tool_versions", ключ — имя бинарника. Конфиг им не «загрязняется».
#
# Единообразие: КАЖДЫЙ инструмент описывает все свои бинарники одинаково — в
# секции `binaries` (даже yt-dlp, у которого один бинарник). Ключ в `binaries`
# == ключ в `tool_versions`; primary-бинарник помечен is_primary. Спец-полей
# для «главного» бинарника на уровне инструмента больше нет.


@dataclass
class VersionState:
    """Runtime-состояние версий одного бинарника. НЕ часть статической конфигурации."""
    current: str = ""
    latest:  str = ""
    status:  str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"current": self.current, "latest": self.latest, "status": self.status}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "VersionState":
        return VersionState(
            current = safe_str(d.get("current")),
            latest  = safe_str(d.get("latest")),
            status  = safe_str(d.get("status")),
        )


@dataclass
class BinaryDef:
    """Статическое описание одного бинарника инструмента: имя файла + флаг версии.

    is_primary помечает бинарник, версия которого представляет инструмент целиком
    (его имя совпадает с именем инструмента). У каждого инструмента ровно один primary.
    """
    filename:     str  = ""
    version_flag: str  = "--version"
    is_primary:   bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename":     self.filename,
            "version_flag": self.version_flag,
            "is_primary":   self.is_primary,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any], defaults: "BinaryDef | None" = None) -> "BinaryDef":
        def_ = defaults or BinaryDef()
        raw_primary = d.get("is_primary")
        return BinaryDef(
            filename     = safe_str(d.get("filename"))     or def_.filename,
            version_flag = safe_str(d.get("version_flag")) or def_.version_flag,
            is_primary   = def_.is_primary if raw_primary is None else bool(raw_primary),
        )


# ── Параметры yt-dlp (переключатель UI + CLI-аргументы) ──────────────────────

# Пресеты качества видео: ключ (пункт дропдауна) → CLI-аргументы yt-dlp.
# У "best" аргументы пустые: формат задаёт extra_args (-f bestvideo+bestaudio/best).
# У остальных свой -f добавляется ПОСЛЕ extra_args — последний -f выигрывает,
# а прочие флаги extra_args (--merge-output-format и т.п.) сохраняются.
DEFAULT_QUALITY_PRESETS: Dict[str, str] = {
    "best":  "",
    "2160p": "-f bestvideo[height<=2160]+bestaudio/best[height<=2160]",
    "1440p": "-f bestvideo[height<=1440]+bestaudio/best[height<=1440]",
    "1080p": "-f bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p":  "-f bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":  "-f bestvideo[height<=480]+bestaudio/best[height<=480]",
}


@dataclass
class ParamQuality:
    """Качество видео: выбранный пресет + карта пресет → CLI-аргументы.

    Карта редактируется в config.json (tools.yt-dlp.parameters.quality.presets):
    можно поправить аргументы пресета или добавить свой — он появится в дропдауне.
    Порядок пунктов = порядок ключей карты."""
    value:   str = "best"
    presets: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_QUALITY_PRESETS))

    def selected_args(self) -> str:
        """CLI-аргументы выбранного пресета ('' для best или неизвестного ключа)."""
        return self.presets.get(self.value, "")

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "presets": dict(self.presets)}

    @staticmethod
    def from_dict(d: Dict[str, Any], def_: "ParamQuality | None" = None) -> "ParamQuality":
        r = def_ or ParamQuality()
        d = d if isinstance(d, dict) else {}
        # Пресеты: дефолты + пользовательские правки/дополнения поверх.
        presets = dict(r.presets)
        raw = d.get("presets")
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(k, str) and isinstance(v, str):
                    presets[k] = v
        value = safe_str(d.get("value")) or r.value
        if value not in presets:
            value = "best" if "best" in presets else next(iter(presets), "best")
        return ParamQuality(value=value, presets=presets)


# Режимы субтитров: ключ → шаблон CLI-аргументов yt-dlp.
# Плейсхолдер {lang} заменяется кодом языка: для пункта-языка (ru/en/...) — его
# кодом, для "auto" — языком интерфейса. Ключ "lang" — общий шаблон для ЛЮБОГО
# кода языка из локализации (отдельных записей на каждый язык не нужно).
# yt-dlp сам пересекает запрошенные языки с доступными: отсутствующие
# пропускаются без ошибки, загрузка не срывается.
DEFAULT_SUBTITLE_PRESETS: Dict[str, str] = {
    "off":  "",
    "lang": "--embed-subs --sub-langs {lang}.*",
    "auto": "--embed-subs --write-auto-subs --sub-langs {lang}.*",
    "all":  "--embed-subs --sub-langs all",
}


@dataclass
class ParamSubtitles:
    """Субтитры: выбранный режим + карта режим → шаблон CLI-аргументов.

    value: "off" | код языка локализации ("ru", "en", ...) | "auto" | "all".
    Карта редактируется в config.json (tools.yt-dlp.parameters.subtitles.presets)."""
    value:   str = "off"
    presets: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SUBTITLE_PRESETS))

    def selected_args(self, ui_language: str = "en") -> str:
        """CLI-аргументы выбранного режима ('' для off/неизвестного шаблона).

        Код языка для {lang}: пункт-язык подставляет себя, остальные режимы —
        язык интерфейса (актуально для "auto")."""
        explicit = self.value in self.presets
        template = self.presets[self.value] if explicit else self.presets.get("lang", "")
        lang = (ui_language if explicit else self.value) or "en"
        lang = lang.split("_")[0].split("-")[0]
        return template.replace("{lang}", lang)

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "presets": dict(self.presets)}

    @staticmethod
    def from_dict(d: Dict[str, Any], def_: "ParamSubtitles | None" = None) -> "ParamSubtitles":
        r = def_ or ParamSubtitles()
        d = d if isinstance(d, dict) else {}
        presets = dict(r.presets)
        raw = d.get("presets")
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(k, str) and isinstance(v, str):
                    presets[k] = v
        presets.setdefault("off", "")          # "выключено" должно существовать всегда
        value = safe_str(d.get("value")) or r.value
        return ParamSubtitles(value=value, presets=presets)


@dataclass
class ParamAudioOnly:
    state: bool = False
    args:  str  = "-x --audio-format mp3 --audio-quality 0"

    def to_dict(self) -> Dict[str, Any]:
        return {"state": self.state, "args": self.args}

    @staticmethod
    def from_dict(d: Dict[str, Any], def_: "ParamAudioOnly | None" = None) -> "ParamAudioOnly":
        r = def_ or ParamAudioOnly()
        return ParamAudioOnly(
            state = get_fallback_bool(d, "state", r.state),
            args  = safe_str(d.get("args")) or r.args,
        )


@dataclass
class ParamCookies:
    state:   bool = False
    browser: str  = "none"
    flag:    str  = "--cookies-from-browser"

    def to_dict(self) -> Dict[str, Any]:
        return {"state": self.state, "browser": self.browser, "flag": self.flag}

    @staticmethod
    def from_dict(d: Dict[str, Any], def_: "ParamCookies | None" = None) -> "ParamCookies":
        r = def_ or ParamCookies()
        return ParamCookies(
            state   = get_fallback_bool(d, "state",   r.state),
            browser = safe_str(d.get("browser")) or r.browser,
            flag    = safe_str(d.get("flag"))    or r.flag,
        )


@dataclass
class ParamPlaylist:
    state:        bool = False
    flag_on:      str  = "--yes-playlist"
    flag_off:     str  = "--no-playlist"
    dir_template: str  = "%(playlist_title)s"
    idx_prefix:   str  = "%(playlist_index)s - "

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state":        self.state,
            "flag_on":      self.flag_on,
            "flag_off":     self.flag_off,
            "dir_template": self.dir_template,
            "idx_prefix":   self.idx_prefix,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any], def_: "ParamPlaylist | None" = None) -> "ParamPlaylist":
        r = def_ or ParamPlaylist()
        return ParamPlaylist(
            state        = get_fallback_bool(d, "state",    r.state),
            flag_on      = safe_str(d.get("flag_on"))      or r.flag_on,
            flag_off     = safe_str(d.get("flag_off"))     or r.flag_off,
            dir_template = safe_str(d.get("dir_template")) or r.dir_template,
            idx_prefix   = (safe_str(d["idx_prefix"]) if "idx_prefix" in d else r.idx_prefix),
        )


@dataclass
class ParamEmbedMetadata:
    state: bool = True
    args:  str  = "--embed-metadata --embed-thumbnail"

    def to_dict(self) -> Dict[str, Any]:
        return {"state": self.state, "args": self.args}

    @staticmethod
    def from_dict(d: Dict[str, Any], def_: "ParamEmbedMetadata | None" = None) -> "ParamEmbedMetadata":
        r = def_ or ParamEmbedMetadata()
        return ParamEmbedMetadata(
            state = get_fallback_bool(d, "state", r.state),
            args  = safe_str(d.get("args")) or r.args,
        )


@dataclass
class ParamExtraArgs:
    value: str = DEFAULT_YT_DLP_ARGS

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value}

    @staticmethod
    def from_dict(d: Dict[str, Any], def_: "ParamExtraArgs | None" = None) -> "ParamExtraArgs":
        r = def_ or ParamExtraArgs()
        value = safe_str(d["value"]) if "value" in d else r.value
        # Мягкая миграция: нетронутый старый дефолт (с -f) → новый без формата.
        # Пользовательские правки не трогаем — их -f продолжает работать
        # (пресет качества "best" ничего не добавляет и не перебивает его).
        if value.strip() == _LEGACY_YT_DLP_ARGS:
            value = DEFAULT_YT_DLP_ARGS
        return ParamExtraArgs(value=value)


@dataclass
class ParamCleanTitles:
    state:        bool = False
    template_on:  str  = "%(title)s.%(ext)s"
    template_off: str  = "%(title)s [%(id)s].%(ext)s"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state":        self.state,
            "template_on":  self.template_on,
            "template_off": self.template_off,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any], def_: "ParamCleanTitles | None" = None) -> "ParamCleanTitles":
        r = def_ or ParamCleanTitles()
        return ParamCleanTitles(
            state        = get_fallback_bool(d, "state",        r.state),
            template_on  = safe_str(d.get("template_on"))  or r.template_on,
            template_off = safe_str(d.get("template_off")) or r.template_off,
        )


@dataclass
class ParamSaveToSource:
    state:        bool = False
    dir_template: str  = "%(extractor_key)s"

    def to_dict(self) -> Dict[str, Any]:
        return {"state": self.state, "dir_template": self.dir_template}

    @staticmethod
    def from_dict(d: Dict[str, Any], def_: "ParamSaveToSource | None" = None) -> "ParamSaveToSource":
        r = def_ or ParamSaveToSource()
        return ParamSaveToSource(
            state        = get_fallback_bool(d, "state",        r.state),
            dir_template = safe_str(d.get("dir_template")) or r.dir_template,
        )


@dataclass
class YtDlpParameters:
    """Параметры yt-dlp: каждый группирует состояние переключателя и CLI-аргументы."""
    audio_only:     ParamAudioOnly     = field(default_factory=ParamAudioOnly)
    quality:        ParamQuality       = field(default_factory=ParamQuality)
    subtitles:      ParamSubtitles     = field(default_factory=ParamSubtitles)
    cookies:        ParamCookies       = field(default_factory=ParamCookies)
    playlist:       ParamPlaylist      = field(default_factory=ParamPlaylist)
    embed_metadata: ParamEmbedMetadata = field(default_factory=ParamEmbedMetadata)
    extra_args:     ParamExtraArgs     = field(default_factory=ParamExtraArgs)
    clean_titles:   ParamCleanTitles   = field(default_factory=ParamCleanTitles)
    save_to_source: ParamSaveToSource  = field(default_factory=ParamSaveToSource)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audio_only":     self.audio_only.to_dict(),
            "quality":        self.quality.to_dict(),
            "subtitles":      self.subtitles.to_dict(),
            "cookies":        self.cookies.to_dict(),
            "playlist":       self.playlist.to_dict(),
            "embed_metadata": self.embed_metadata.to_dict(),
            "extra_args":     self.extra_args.to_dict(),
            "clean_titles":   self.clean_titles.to_dict(),
            "save_to_source": self.save_to_source.to_dict(),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any], defaults: "YtDlpParameters | None" = None) -> "YtDlpParameters":
        def_ = defaults or YtDlpParameters()
        def _s(key, cls, sub_def):
            raw = d.get(key, {})
            return cls.from_dict(raw if isinstance(raw, dict) else {}, sub_def)
        return YtDlpParameters(
            audio_only     = _s("audio_only",     ParamAudioOnly,     def_.audio_only),
            quality        = _s("quality",        ParamQuality,       def_.quality),
            subtitles      = _s("subtitles",      ParamSubtitles,     def_.subtitles),
            cookies        = _s("cookies",        ParamCookies,       def_.cookies),
            playlist       = _s("playlist",       ParamPlaylist,      def_.playlist),
            embed_metadata = _s("embed_metadata", ParamEmbedMetadata, def_.embed_metadata),
            extra_args     = _s("extra_args",     ParamExtraArgs,     def_.extra_args),
            clean_titles   = _s("clean_titles",   ParamCleanTitles,   def_.clean_titles),
            save_to_source = _s("save_to_source", ParamSaveToSource,  def_.save_to_source),
        )


@dataclass
class ToolConfig:
    """
    Базовая СТАТИЧЕСКАЯ конфигурация одного инструмента — общая для всех.

    Все бинарники инструмента (включая primary) единообразно описаны в `binaries`.
    Единственное инструмент-специфичное расширение — YtDlpConfig.parameters.
    Runtime-версии (current/latest/status) тут НЕ хранятся — они в
    state.tool_versions (VersionState), ключ совпадает с ключом в `binaries`.

    Полиморфизм сериализации: подкласс расширяет to_dict()/from_dict().
    Загрузчик диспетчеризует по типу дефолта: type(default).from_dict(raw, default).
    """
    version_url:  str = ""
    download_url: str = ""
    chunk_size:   int = 8_192
    binaries:     Dict[str, BinaryDef] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_url":  self.version_url,
            "download_url": self.download_url,
            "chunk_size":   self.chunk_size,
            "binaries":     {k: v.to_dict() for k, v in self.binaries.items()},
        }

    @staticmethod
    def _merge_binaries(d: Dict[str, Any], def_: "ToolConfig") -> Dict[str, BinaryDef]:
        """Бинарники = копия дефолтов, поверх — пользовательские правки из raw.

        Дефолты гарантируют присутствие всех бинарников (в т.ч. primary), даже
        если в сохранённом конфиге их нет — это и есть мягкая миграция формата.
        """
        binaries: Dict[str, BinaryDef] = {k: replace(v) for k, v in def_.binaries.items()}
        raw_bins = d.get("binaries", {})
        if isinstance(raw_bins, dict):
            for name, bd in raw_bins.items():
                if isinstance(bd, dict):
                    binaries[name] = BinaryDef.from_dict(bd, def_.binaries.get(name))
        return binaries

    @staticmethod
    def _base_kwargs(d: Dict[str, Any], def_: "ToolConfig") -> Dict[str, Any]:
        """Общие поля базового ToolConfig — переиспользуется from_dict подклассов."""
        return dict(
            version_url  = safe_str(d.get("version_url"))  or def_.version_url,
            download_url = safe_str(d.get("download_url")) or def_.download_url,
            chunk_size   = safe_int(d.get("chunk_size"), def_.chunk_size),
            binaries     = ToolConfig._merge_binaries(d, def_),
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any], defaults: "ToolConfig | None" = None) -> "ToolConfig":
        def_ = defaults or cls()
        return cls(**cls._base_kwargs(d, def_))


@dataclass
class YtDlpConfig(ToolConfig):
    """Конфигурация yt-dlp: добавляет параметры скачивания (переключатели UI + CLI)."""
    parameters: YtDlpParameters = field(default_factory=YtDlpParameters)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["parameters"] = self.parameters.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any], defaults: "ToolConfig | None" = None) -> "YtDlpConfig":
        def_ = defaults if isinstance(defaults, YtDlpConfig) else cls()
        raw = d.get("parameters", {})
        params = YtDlpParameters.from_dict(
            raw if isinstance(raw, dict) else {}, def_.parameters
        )
        return cls(**cls._base_kwargs(d, def_), parameters=params)


@dataclass
class Aria2cParameters:
    """Параметры aria2c (по аналогии с YtDlpParameters): CLI-флаги скачивания и
    раздачи + имя temp-подпапки. Персистятся в секции parameters конфига."""
    download:     str = DEFAULT_ARIA2_ARGS       # флаги обычного скачивания
    seed:         str = DEFAULT_ARIA2_SEED_ARGS   # флаги режима раздачи
    part_dirname: str = DEFAULT_ARIA2_PART_DIRNAME

    def to_dict(self) -> Dict[str, Any]:
        return {"download": self.download, "seed": self.seed,
                "part_dirname": self.part_dirname}

    @staticmethod
    def from_dict(d: Dict[str, Any], defaults: "Aria2cParameters | None" = None) -> "Aria2cParameters":
        r = defaults or Aria2cParameters()
        d = d if isinstance(d, dict) else {}
        return Aria2cParameters(
            download     = safe_str(d.get("download"))     or r.download,
            seed         = safe_str(d.get("seed"))         or r.seed,
            part_dirname = safe_str(d.get("part_dirname")) or r.part_dirname,
        )


@dataclass
class Aria2cConfig(ToolConfig):
    """Конфигурация aria2c: добавляет parameters (флаги скачивания/раздачи)."""
    parameters: Aria2cParameters = field(default_factory=Aria2cParameters)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["parameters"] = self.parameters.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any], defaults: "ToolConfig | None" = None) -> "Aria2cConfig":
        def_ = defaults if isinstance(defaults, Aria2cConfig) else cls()
        raw = d.get("parameters", {})
        params = Aria2cParameters.from_dict(
            raw if isinstance(raw, dict) else {}, def_.parameters
        )
        return cls(**cls._base_kwargs(d, def_), parameters=params)


# ── UI-метаданные темы (порядок полей для Settings) ──────────────────────────

# THEME_FIELDS: список (field_key, i18n_key)
# THEME_GROUPS: список (group_i18n_key, [field_key, ...])
THEME_FIELDS = [
    ("accent_color",         "color_accent"),
    ("header_color",         "color_header"),
    ("switch_color",         "color_switch"),
    ("progress_color",       "color_progress"),
    ("button_color",         "color_button"),
    ("button_text_color",    "color_button_text"),
    ("text_color",           "color_text"),
    ("text_secondary_color", "color_text_secondary"),
    ("text_muted_color",     "color_text_muted"),
    ("bg_color",             "color_bg"),
    ("appbar_color",         "color_appbar"),
    ("bottom_bar_color",     "color_bottom_bar"),
    ("card_color",           "color_card"),
    ("surface_color",        "color_surface"),
    ("border_color",         "color_border"),
    ("status_ok_color",      "color_status_ok"),
    ("status_error_color",   "color_status_error"),
    ("status_warning_color", "color_status_warning"),
    ("status_running_color", "color_status_running"),
]

THEME_GROUPS = [
    ("theme_group_controls", ["accent_color", "header_color", "switch_color",
                               "progress_color", "button_color", "button_text_color"]),
    ("theme_group_text",     ["text_color", "text_secondary_color", "text_muted_color"]),
    ("theme_group_surfaces", ["bg_color", "appbar_color", "bottom_bar_color",
                               "card_color", "surface_color", "border_color"]),
    ("theme_group_status",   ["status_ok_color", "status_error_color",
                               "status_warning_color", "status_running_color"]),
]

PALETTE = [
    "F44336","E91E63","9C27B0","673AB7","3F51B5","2196F3",
    "03A9F4","00BCD4","009688","4CAF50","8BC34A","CDDC39",
    "FFEB3B","FFC107","FF9800","FF5722","795548","9E9E9E",
    "607D8B","000000","212121","37474F","455A64","546E7A",
    "EF9A9A","F48FB1","CE93D8","B39DDB","90CAF9","80DEEA",
    "A5D6A7","FFE082","FFCC80","FF8A65","BCAAA4","EEEEEE",
    "00B4D8","00FF87","FF6B6B","FFD166","06D6A0","118AB2",
    "1c1c1c","161616","0d0d0d","1A237E","B71C1C","1B5E20",
]


# ── Утилиты ───────────────────────────────────────────────────────────────────

# Семантика статусных событий (severity) → токен ThemeConfig.
# События шины несут только семантику ("ok"|"warning"|"error"|"info");
# в конкретный цвет её переводит UI-слой по активной теме.
SEVERITY_TOKENS = {
    "ok":      "status_ok_color",
    "warning": "status_warning_color",
    "error":   "status_error_color",
    "info":    "text_secondary_color",
}


def severity_color(t: ThemeConfig, severity: str) -> str:
    """Flet-цвет для severity события из токенов активной темы."""
    return hex_to_flet(getattr(t, SEVERITY_TOKENS.get(severity, "text_secondary_color")))


def hex_to_flet(hex_str: str) -> str:
    h = hex_str.strip().lstrip("#").upper()
    if len(h) == 6 and all(c in "0123456789ABCDEF" for c in h):
        return f"#{h}"
    return "#FFFFFF"


def is_valid_hex(value: str) -> bool:
    h = value.strip().lstrip("#").upper()
    return len(h) == 6 and all(c in "0123456789ABCDEF" for c in h)


def download_display_name(url: str) -> str:
    """Человекочитаемое имя загрузки из URL.

    magnet — параметр dn (display name), он же реальное имя торрента;
    остальные ссылки возвращаются как есть (для yt-dlp имя берётся из метаданных
    отдельно, у прямых http-ссылок имя файла и так видно в самом URL)."""
    from urllib.parse import urlparse, parse_qs, unquote
    u = safe_str(url).strip()
    if u.lower().startswith("magnet:"):
        try:
            dn = parse_qs(urlparse(u).query).get("dn", [""])[0]
            if dn:
                return unquote(dn)
        except Exception:
            pass
    # Локальный .torrent/.metalink — показываем имя файла, а не весь путь.
    if u.lower().endswith((".torrent", ".metalink")):
        return os.path.basename(u.replace("\\", "/")) or u
    return u


def magnet_btih(url: str) -> str:
    """BitTorrent info-hash (btih) из magnet-ссылки в нижнем регистре; '' если нет.

    Лежит прямо в URL: magnet:?xt=urn:btih:<HASH>&... — отдельно хранить не нужно.
    Идентифицирует содержимое торрента независимо от трекеров (tr) и имени (dn),
    поэтому годится как ключ дедупликации повторных загрузок."""
    import re
    m = re.search(r"xt=urn:btih:([0-9a-zA-Z]+)", safe_str(url), re.IGNORECASE)
    return m.group(1).lower() if m else ""


def parse_url_lines(raw: str) -> list:
    """Разобрать многострочный текст в список ссылок: по строке на ссылку, без
    пустых и дубликатов (порядок сохраняется). Разделитель — только перевод
    строки: URL и пути к .torrent-файлам могут содержать пробелы.
    Используется полем URL главного экрана и слежением за буфером обмена."""
    seen = set()
    urls = []
    for line in (raw or "").splitlines():
        u = line.strip()
        if u and u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def safe_int(value: Any, default: int = 0) -> int:
    if value is None or value == "": return default
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return default


def get_fallback_bool(source_dict: Dict[str, Any], key: str, default_bool: bool) -> bool:
    val = source_dict.get(key)
    return default_bool if val is None or val == "" else bool(val)
