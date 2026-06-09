import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict

# ── Константы приложения ──────────────────────────────────────────────────────

CHECK_INTERVAL_SECONDS = 6 * 3600

# ── Сетевые константы (chunk / timeout) ──────────────────────────────────────
YT_DLP_CHUNK_SIZE      = 8_192   # байт/итерацию при скачивании yt-dlp
FFMPEG_CHUNK_SIZE      = 16_384  # байт/итерацию при скачивании ffmpeg zip
THUMBNAIL_TIMEOUT      = 15.0    # секунд — общий async-таймаут скачивания thumbnail
THUMBNAIL_SOCK_TIMEOUT = 10      # секунд — connect-таймаут httpx для thumbnail

DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "Downloads")
DEFAULT_PROXY_ADDRESS = "socks5://127.0.0.1:1080"
DEFAULT_YT_DLP_ARGS   = "-f bestvideo+bestaudio/best --merge-output-format mp4"

DEFAULT_YT_API_URL          = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
DEFAULT_YT_DOWNLOAD_URL     = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    if os.name == "nt" else
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
)
DEFAULT_FFMPEG_VERSION_URL  = "https://www.gyan.dev/ffmpeg/builds/release-version"
DEFAULT_FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip"


# ── Typed конфиги (вместо Dict) ───────────────────────────────────────────────

@dataclass
class ThemeConfig:
    accent_color:   str = "00B4D8"
    switch_color:   str = "4CAF50"
    header_color:   str = "00B4D8"
    text_color:     str = "E0E0E0"
    progress_color: str = "4CAF50"
    button_color:   str = "4CAF50"
    appbar_color:   str = "1c1c1c"
    card_color:     str = "161616"

    def to_dict(self) -> Dict[str, str]:
        return {
            "accent_color":   self.accent_color,
            "switch_color":   self.switch_color,
            "header_color":   self.header_color,
            "text_color":     self.text_color,
            "progress_color": self.progress_color,
            "button_color":   self.button_color,
            "appbar_color":   self.appbar_color,
            "card_color":     self.card_color,
        }

    @staticmethod
    def from_dict(d: Dict[str, str]) -> "ThemeConfig":
        defaults = ThemeConfig()
        return ThemeConfig(
            accent_color   = safe_str(d.get("accent_color"))   or defaults.accent_color,
            switch_color   = safe_str(d.get("switch_color"))   or defaults.switch_color,
            header_color   = safe_str(d.get("header_color"))   or defaults.header_color,
            text_color     = safe_str(d.get("text_color"))     or defaults.text_color,
            progress_color = safe_str(d.get("progress_color")) or defaults.progress_color,
            button_color   = safe_str(d.get("button_color"))   or defaults.button_color,
            appbar_color   = safe_str(d.get("appbar_color"))   or defaults.appbar_color,
            card_color     = safe_str(d.get("card_color"))     or defaults.card_color,
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
        return ParamExtraArgs(
            value = (safe_str(d["value"]) if "value" in d else r.value),
        )


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
    cookies:        ParamCookies       = field(default_factory=ParamCookies)
    playlist:       ParamPlaylist      = field(default_factory=ParamPlaylist)
    embed_metadata: ParamEmbedMetadata = field(default_factory=ParamEmbedMetadata)
    extra_args:     ParamExtraArgs     = field(default_factory=ParamExtraArgs)
    clean_titles:   ParamCleanTitles   = field(default_factory=ParamCleanTitles)
    save_to_source: ParamSaveToSource  = field(default_factory=ParamSaveToSource)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audio_only":     self.audio_only.to_dict(),
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


# ── UI-метаданные темы (порядок полей для Settings) ──────────────────────────

# THEME_FIELDS: список (field_key, i18n_key)
# THEME_GROUPS: список (group_i18n_key, [field_key, ...])
THEME_FIELDS = [
    ("accent_color",   "color_accent"),
    ("header_color",   "color_header"),
    ("switch_color",   "color_switch"),
    ("text_color",     "color_text"),
    ("progress_color", "color_progress"),
    ("button_color",   "color_button"),
    ("appbar_color",   "color_appbar"),
    ("card_color",     "color_card"),
]

THEME_GROUPS = [
    ("theme_group_controls", ["accent_color", "header_color", "switch_color",
                               "text_color", "progress_color", "button_color"]),
    ("theme_group_surfaces", ["appbar_color", "card_color"]),
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

def hex_to_flet(hex_str: str) -> str:
    h = hex_str.strip().lstrip("#").upper()
    if len(h) == 6 and all(c in "0123456789ABCDEF" for c in h):
        return f"#{h}"
    return "#FFFFFF"


def is_valid_hex(value: str) -> bool:
    h = value.strip().lstrip("#").upper()
    return len(h) == 6 and all(c in "0123456789ABCDEF" for c in h)


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
