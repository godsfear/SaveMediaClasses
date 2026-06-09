"""
managers/tool_specs.py — единая абстракция внешнего инструмента (yt-dlp, ffmpeg, …).

Идея (симметрия с providers.DownloadProvider):
  ToolsManager — это generic-движок. Он НЕ знает ни про yt-dlp, ни про ffmpeg.
  Он итерирует список ToolSpec и для каждого единообразно выполняет:
      • проверку локальной версии каждого бинарника  (probe → ToolSpec.parse_version)
      • запрос удалённой версии                       (ToolSpec.fetch_remote_version)
      • установку/обновление                          (ToolSpec.install)

Добавить новый инструмент:
  1. Реализовать ToolSpec в managers/tool_registry.py.
  2. Добавить его в DEFAULT_TOOLS.
  Больше ничего менять не нужно — он автоматически попадает в проверку версий,
  в установку, в события и в список виджетов на экране настроек.

Сравнение версий («устарело ли») живёт в ОДНОМ месте — classify_version().
Сетевой стриминг с прогрессом — в ОДНОМ месте — stream_to_file().
"""

from __future__ import annotations

import abc
import os
import zipfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional, Protocol, runtime_checkable

from config import safe_int, ToolConfig

if TYPE_CHECKING:
    import httpx
    from state import AppState


# ── Sentinel-константы статусов версий (языконезависимы, не для отображения) ──
# Перевод в текст UI происходит в settings_screen._resolve_version().
TOOL_VERSION_MISSING       = ""          # бинарник не найден (falsy)
TOOL_VERSION_CALL_ERROR    = "\x00CALL"  # ошибка вызова --version
TOOL_VERSION_REMOTE_ERR    = "\x00NET"   # сетевая ошибка при запросе удалённой версии
TOOL_VERSION_UNKNOWN       = "\x00UNK"   # ответ API не содержит поля с версией
TOOL_VERSION_NEEDS_RUNTIME = "\x00RT"    # бинарник есть, но не хватает рантайма (Python для generic yt-dlp)

_REMOTE_BAD = (TOOL_VERSION_REMOTE_ERR, TOOL_VERSION_UNKNOWN)

# Статусы (единый словарь значений). needs_update выводится из статуса.
STATUS_OK       = "ok"
STATUS_OUTDATED = "outdated"
STATUS_MISSING  = "missing"
STATUS_ERROR    = "error"

# Статусы, при которых инструмент подлежит обновлению (если удалённая версия известна).
_INSTALLABLE_STATUSES = (STATUS_MISSING, STATUS_OUTDATED)


# ── Единственная функция сравнения версий ─────────────────────────────────────

def classify_version(local: str, remote: str) -> str:
    """Определить статус по локальной и удалённой версии. Единый источник истины."""
    if local == TOOL_VERSION_MISSING:
        return STATUS_MISSING
    if local in (TOOL_VERSION_CALL_ERROR, TOOL_VERSION_NEEDS_RUNTIME) or remote in _REMOTE_BAD:
        return STATUS_ERROR
    if local == remote or remote in local or local in remote:
        return STATUS_OK
    return STATUS_OUTDATED


def remote_is_known(remote: str) -> bool:
    """True если удалённую версию удалось получить (можно обновлять)."""
    return remote not in _REMOTE_BAD


def status_needs_update(status: str, remote: str) -> bool:
    """Подлежит ли бинарник обновлению. Обновляем только если есть валидная удалённая версия."""
    return remote_is_known(remote) and status in _INSTALLABLE_STATUSES


# ── Описание бинарника ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolBinary:
    """
    Один исполняемый файл, предоставляемый инструментом.

    Один инструмент может давать несколько бинарников: ffmpeg-комплект
    предоставляет ffmpeg + ffplay + ffprobe. Расширение (.exe) добавляет
    движок по платформе — здесь хранится базовое имя.
    """
    name:         str                 # отображаемое имя (ключ виджета): "yt-dlp", "ffmpeg"
    filename:     str                 # базовое имя файла без расширения
    version_flag: str  = "--version"  # флаг для вывода версии
    is_primary:   bool = False        # бинарник, чья версия представляет весь инструмент


# ── Контекст установки ────────────────────────────────────────────────────────

@dataclass
class InstallContext:
    """Всё, что нужно ToolSpec.install() для скачивания/распаковки."""
    client:       "httpx.AsyncClient"
    tools_dir:    str
    ext:          str                          # ".exe" на Windows, "" иначе
    download_url: str
    on_progress:  Callable[[Optional[float]], None]  # pct 0..1, или None = индетерминированно
    state:        "AppState" = None            # type: ignore[assignment]
    chunk_size:   int = 8_192


class ManualInstallRequired(Exception):
    """
    Поднимается из ToolSpec.install(), если автоматическая установка невозможна
    (например, ffmpeg вне Windows). hint — подсказка пользователю с командой.
    """
    def __init__(self, hint: str) -> None:
        super().__init__(hint)
        self.hint = hint


# ── Протокол инструмента ──────────────────────────────────────────────────────

@runtime_checkable
class ToolSpec(Protocol):
    """Контракт одного инструмента. ToolsManager работает только с этим интерфейсом."""

    name: str

    def binaries(self, state: "AppState") -> list[ToolBinary]:
        """Список бинарников инструмента (первый/помеченный is_primary — главный)."""
        ...

    def missing_runtime(self) -> bool:
        """
        True, если для запуска инструмента не хватает внешнего рантайма
        (например, generic-сборка yt-dlp требует системный Python 3). По умолчанию
        False — большинство инструментов self-contained.
        """
        ...

    def parse_version(self, binary: ToolBinary, output: str) -> str:
        """Распарсить вывод `<exe> <version_flag>` в строку версии. '' если не удалось."""
        ...

    def version_url(self, state: "AppState") -> str:
        """URL для запроса удалённой версии (может читать пользовательские настройки из state)."""
        ...

    def download_url(self, state: "AppState") -> str:
        """URL для скачивания при установке/обновлении."""
        ...

    def chunk_size(self, state: "AppState") -> int:
        """Размер чанка при потоковой загрузке."""
        ...

    async def fetch_remote_version(self, client: "httpx.AsyncClient", url: str) -> str:
        """
        Получить удалённую версию. Вернуть строку версии либо TOOL_VERSION_UNKNOWN,
        если ответ корректен, но версии в нём нет. Сетевые ошибки — поднимать
        исключение (движок переведёт их в TOOL_VERSION_REMOTE_ERR).
        """
        ...

    async def install(self, ctx: InstallContext) -> None:
        """
        Скачать и установить инструмент. При невозможности авто-установки —
        поднять ManualInstallRequired(hint).
        """
        ...


# ── Базовый класс инструмента ─────────────────────────────────────────────────

class BaseTool(abc.ABC):
    """
    Общая база для всех инструментов (реализует ToolSpec).

    Главное, что она даёт, — СВЯЗЬ инструмента с его конфигом в одном месте
    (cfg). Раньше каждый метод каждого инструмента делал
    `state.tools.get(self.name, ToolConfig())`, местами с хардкодом строк-имён.
    Теперь lookup один — через self.cfg(state) — и типобезопасен через
    default_config(). Дефолтная конфигурация объявляется тут же: из неё
    автоматически собирается весь реестр (tool_registry.default_tools_config),
    так что добавление инструмента больше не требует правок в config.py.
    """
    name: str

    @abc.abstractmethod
    def default_config(self) -> ToolConfig:
        """Дефолтная статическая конфигурация инструмента (единый источник истины)."""
        ...

    def cfg(self, state: "AppState | None") -> ToolConfig:
        """Конфиг инструмента из state; дефолт, если state или ключа нет."""
        cfg = state.tools.get(self.name) if state is not None else None
        return cfg if cfg is not None else self.default_config()

    # ── Общие геттеры (раньше дублировались в каждом инструменте) ──────────────

    def version_url(self, state: "AppState") -> str:
        return self.cfg(state).version_url

    def download_url(self, state: "AppState") -> str:
        return self.cfg(state).download_url

    def chunk_size(self, state: "AppState") -> int:
        return self.cfg(state).chunk_size

    # ── Бинарники: единообразно для всех инструментов из cfg.binaries ──────────

    def binaries(self, state: "AppState") -> list[ToolBinary]:
        """
        Список бинарников инструмента — прямое отображение cfg.binaries.
        Реализация общая: и yt-dlp (один бинарник), и ffmpeg (три) описаны
        одинаково в конфиге, поэтому переопределять в подклассах не нужно.
        """
        return [
            ToolBinary(name=name,
                       filename=bd.filename or name,
                       version_flag=bd.version_flag or "--version",
                       is_primary=bd.is_primary)
            for name, bd in self.cfg(state).binaries.items()
        ]

    def primary_binary(self, state: "AppState") -> ToolBinary:
        """Главный бинарник инструмента (по is_primary; иначе — первый)."""
        bins = self.binaries(state)
        return next((b for b in bins if b.is_primary), bins[0])

    # ── Рантайм-предусловие (по умолчанию инструмент self-contained) ───────────

    def missing_runtime(self) -> bool:
        """Переопределяется инструментом, которому нужен внешний рантайм (см. ToolSpec)."""
        return False

    # ── Инструмент-специфика — реализуют подклассы ─────────────────────────────

    @abc.abstractmethod
    def parse_version(self, binary: ToolBinary, output: str) -> str:
        ...

    @abc.abstractmethod
    async def fetch_remote_version(self, client: "httpx.AsyncClient", url: str) -> str:
        ...

    @abc.abstractmethod
    async def install(self, ctx: InstallContext) -> None:
        ...


# ── Общие примитивы для реализаций ToolSpec ──────────────────────────────────

async def stream_to_file(
    client: "httpx.AsyncClient",
    url: str,
    dest_path: str,
    on_progress: Callable[[Optional[float]], None],
    chunk_size: int = 8_192,
) -> str:
    """
    Скачать url в dest_path потоково, отдавая прогресс 0..1 через on_progress.
    Пишет во временный .part, проверяет непустоту, атомарно заменяет.
    При ошибке удаляет временный файл и пробрасывает исключение.
    """
    temp_path = dest_path + ".part"
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)

        downloaded = 0
        async with client.stream("GET", url) as res:
            res.raise_for_status()
            total = safe_int(res.headers.get("content-length", "0"))
            with open(temp_path, "wb") as f:
                async for chunk in res.aiter_bytes(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        on_progress(min(downloaded / total, 1.0))

        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            raise RuntimeError(f"Downloaded empty file: {os.path.basename(dest_path)}")

        os.replace(temp_path, dest_path)
        return dest_path

    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        raise


def extract_zip_members(zip_path: str, tools_dir: str, members: set[str]) -> int:
    """
    Распаковать из zip все записи, чьё базовое имя (в нижнем регистре) есть в
    members, прямо в tools_dir (без вложенных каталогов архива). Возвращает число
    извлечённых файлов. Общий примитив для инструментов, поставляемых zip-архивом
    (ffmpeg-комплект, aria2c во вложенной папке сборки).
    """
    found = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            base = os.path.basename(member).lower()
            if base in members:
                target = os.path.join(tools_dir, base)
                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                found += 1
    return found
