"""
config/tools.py — статическая конфигурация инструментов и runtime-состояние версий.

Разделение ответственности:
  • ToolConfig / YtDlpConfig / BinaryDef — СТАТИЧЕСКАЯ конфигурация: URL,
    имена файлов, флаги. Редактируется пользователем, персистится в "tools".
  • VersionState — RUNTIME-состояние версий (current/latest/status), которое
    контроллер обновляет при проверке. Персистится отдельно, в секции
    "tool_versions", ключ — имя бинарника. Конфиг им не «загрязняется».

Единообразие: КАЖДЫЙ инструмент описывает все свои бинарники одинаково — в
секции `binaries` (даже yt-dlp, у которого один бинарник). Ключ в `binaries`
== ключ в `tool_versions`; primary-бинарник помечен is_primary. Спец-полей
для «главного» бинарника на уровне инструмента больше нет.
"""

from dataclasses import dataclass, field, replace
from typing import Any, Dict

from config.constants import (
    DEFAULT_ARIA2_ARGS, DEFAULT_ARIA2_PART_DIRNAME, DEFAULT_ARIA2_SEED_ARGS,
    DEFAULT_YT_DLP_ARGS, _LEGACY_YT_DLP_ARGS,
)
from config.utils import get_fallback_bool, safe_int, safe_str


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
    download:     str = DEFAULT_ARIA2_ARGS        # флаги обычного скачивания
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
