"""
DownloadManager — владеет очередью загрузок.

Не знает про yt-dlp, aria2c или любой другой конкретный инструмент.
Работает только через протокол DownloadProvider.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field, fields
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from app_logging import get_logger
from events import (
    EventBus,
    DownloadStartedEvent,
    DownloadProgressEvent,
    DownloadPostprocessingEvent,
    DownloadCompletedEvent,
    DownloadCancelledEvent,
    DownloadPausedEvent,
    DownloadResumedEvent,
)

if TYPE_CHECKING:
    from managers.providers import DownloadProvider
    from state import AppState

MAX_PARALLEL = 5

# (async_fn, *args) — в Flet: page.run_task
TaskRunner = Callable[..., Any]


# ── Снимок параметров на момент нажатия «Скачать» ────────────────────────────

@dataclass(frozen=True)
class DownloadSnapshot:
    """Неизменяемая копия параметров загрузки.
    Изменение настроек во время загрузки не затрагивает уже запущенные задачи."""
    url:              str
    download_path:    str
    proxy_enabled:    bool
    proxy_address:    str
    cookies_enabled:  bool
    cookies_browser:  str
    playlist_enabled: bool
    embed_metadata:   bool
    audio_only:       bool
    yt_dlp_args:      str
    clean_titles:     bool
    save_to_source:   bool
    # Параметры инструмента из конфига (флаги CLI и шаблоны путей)
    aria2_args:            str = ""   # фиксированные CLI-флаги aria2c (из Aria2cConfig)
    aria2_part_dirname:    str = ".part"
    cookies_flag:          str = "--cookies-from-browser"
    playlist_flag_on:      str = "--yes-playlist"
    playlist_flag_off:     str = "--no-playlist"
    metadata_flags:        str = "--embed-metadata --embed-thumbnail"
    audio_flags:           str = "-x --audio-format mp3 --audio-quality 0"
    clean_title_template:  str = "%(title)s.%(ext)s"
    title_id_template:     str = "%(title)s [%(id)s].%(ext)s"
    playlist_dir_template: str = "%(playlist_title)s"
    playlist_idx_prefix:   str = "%(playlist_index)s - "
    source_dir_template:   str = "%(extractor_key)s"

    @classmethod
    def from_state(cls, state: "AppState", url: str) -> "DownloadSnapshot":
        """Собрать неизменяемый снимок из текущего AppState.

        Знание внутренних имён флагов/шаблонов yt-dlp-параметров локализовано
        здесь, а не в UI-экране: экрану достаточно вызвать from_state(state, url).
        Доступ к параметрам — через типизированный аксессор state.ytdlp,
        поэтому строковых имён инструментов тут тоже нет.
        """
        p = state.ytdlp.parameters
        a = state.aria2c
        return cls(
            url=url,
            download_path=state.download_path,
            aria2_args=a.extra_args,
            aria2_part_dirname=a.part_dirname,
            proxy_enabled=state.proxy_enabled,
            proxy_address=state.proxy_address,
            cookies_enabled=p.cookies.state,
            cookies_browser=p.cookies.browser,
            playlist_enabled=p.playlist.state,
            embed_metadata=p.embed_metadata.state,
            audio_only=p.audio_only.state,
            yt_dlp_args=p.extra_args.value,
            clean_titles=p.clean_titles.state,
            save_to_source=p.save_to_source.state,
            cookies_flag=p.cookies.flag,
            playlist_flag_on=p.playlist.flag_on,
            playlist_flag_off=p.playlist.flag_off,
            metadata_flags=p.embed_metadata.args,
            audio_flags=p.audio_only.args,
            clean_title_template=p.clean_titles.template_on,
            title_id_template=p.clean_titles.template_off,
            playlist_dir_template=p.playlist.dir_template,
            playlist_idx_prefix=p.playlist.idx_prefix,
            source_dir_template=p.save_to_source.dir_template,
        )

    @classmethod
    def from_params(cls, url: str, params: dict) -> "DownloadSnapshot":
        """Восстановить снимок из сохранённого в БД params (asdict без url) — для
        возобновления загрузки из истории. Лишние/недостающие ключи игнорируются:
        берём только известные поля, остальное — дефолты dataclass."""
        valid = {f.name for f in fields(cls)}
        kw = {k: v for k, v in (params or {}).items() if k in valid and k != "url"}
        return cls(url=url, **kw)


# ── Внутреннее состояние одной задачи ────────────────────────────────────────

@dataclass
class DownloadTask:
    task_id:   str
    snapshot:  DownloadSnapshot
    provider:  "DownloadProvider"
    cancelled: bool  = False
    paused:    bool  = False   # на паузе: процесс убит, partial цел, задача ждёт resume
    started:   bool  = False   # DownloadStartedEvent уже отправлен (не дублируем на resume)
    _last_pct: float = -1.0   # последний эмитированный прогресс; -1 = ещё не было
    _handle:   Optional[asyncio.Task] = field(default=None, repr=False)


# ── Менеджер ──────────────────────────────────────────────────────────────────

class DownloadManager:

    def __init__(self,
                 provider_factories: Dict[str, Callable[[], "DownloadProvider"]],
                 default_provider: str,
                 log_path: str,
                 bus: EventBus,
                 task_runner: TaskRunner,
                 db=None) -> None:
        """
        provider_factories — реестр {ключ: callable без аргументов → новый DownloadProvider}.
            Пример: {"yt-dlp": lambda: YtDlpProvider(paths), "aria2c": lambda: Aria2cProvider(paths)}
        default_provider — ключ провайдера по умолчанию (когда add() вызван без выбора).
        task_runner — планировщик async-задач (в app.py: page.run_task).
        db — DownloadRepository для сохранения thumbnail после загрузки (опционально).
        """
        self._provider_factories = provider_factories
        self._default_provider   = default_provider
        self._task_runner        = task_runner
        self._bus                = bus
        self._db                 = db
        self._log                = get_logger("app")

        self._semaphore = asyncio.Semaphore(MAX_PARALLEL)
        self._active: Dict[str, DownloadTask] = {}

    def _make_provider(self, provider_key: Optional[str]) -> "DownloadProvider":
        """Создать провайдер по ключу; неизвестный/пустой ключ → провайдер по умолчанию."""
        factory = self._provider_factories.get(provider_key or self._default_provider) \
            or self._provider_factories[self._default_provider]
        return factory()

    # ── Публичный API ─────────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        # Паузные задачи не качаются и не занимают слот — в счёт ёмкости не идут.
        return sum(1 for t in self._active.values() if not t.paused)

    @property
    def at_capacity(self) -> bool:
        return self.active_count >= MAX_PARALLEL

    def is_active_url(self, url: str) -> bool:
        """Уже идёт загрузка с этим URL? Нельзя качать тот же URL дважды
        одновременно: совпадут временные .part-папки (детерминированы по URL) и
        процессы подерутся за файлы."""
        return any(t.snapshot.url == url for t in self._active.values())

    def active_temp_dirs(self) -> set[str]:
        """Временные папки активных загрузок (чтобы ручная очистка их не трогала)."""
        return {
            pd for t in self._active.values()
            if (pd := getattr(t.provider, "_part_dir", ""))
        }

    def add(self, snapshot: DownloadSnapshot, provider_key: Optional[str] = None) -> Optional[str]:
        """Запустить загрузку выбранным провайдером. Возвращает task_id или None если exe не найден."""
        provider = self._make_provider(provider_key)
        if not provider.resolve_exe():
            return None

        task_id  = str(uuid.uuid4())
        task     = DownloadTask(task_id=task_id, snapshot=snapshot, provider=provider)
        self._active[task_id] = task
        task._handle = self._task_runner(self._run, task)
        return task_id

    def cancel(self, task_id: str) -> None:
        task = self._active.get(task_id)
        if not task or task.cancelled:
            return
        task.cancelled = True
        if task.paused:
            # У паузной задачи нет живого процесса/короутины — финализируем сами.
            task.paused = False
            self._finish(task)
            self._bus.emit(DownloadCancelledEvent(
                task_id=task_id, source=self._provider_source(task.provider)))
        else:
            task.provider.cancel()

    def cancel_all(self) -> None:
        for task_id in list(self._active):
            self.cancel(task_id)

    def pause(self, task_id: str) -> None:
        """Поставить на паузу: убить процесс (partial и .aria2 остаются для докачки).
        Задача остаётся в _active в состоянии paused до resume(). БД → 'incomplete'."""
        task = self._active.get(task_id)
        if task and not task.cancelled and not task.paused:
            task.paused = True
            task.provider.cancel()
            self._bus.emit(DownloadPausedEvent(
                task_id=task_id, source=self._provider_source(task.provider)))

    def resume(self, task_id: str) -> None:
        """Снять с паузы: перезапустить загрузку (та же .part/<id> + --continue).
        БД → 'running'."""
        task = self._active.get(task_id)
        if task and task.paused and not task.cancelled:
            task.paused = False
            self._bus.emit(DownloadResumedEvent(
                task_id=task_id, source=self._provider_source(task.provider)))
            task._handle = self._task_runner(self._run, task)

    def can_pause(self, task_id: str) -> bool:
        task = self._active.get(task_id)
        return bool(task and getattr(task.provider, "SUPPORTS_PAUSE", False))

    def drop(self, task_id: str) -> None:
        """Выгрузить ПАУЗНУЮ задачу из активных — она «припаркована» в истории
        (статус incomplete) и будет возобновлена реконструкцией. Процесс уже убит,
        partial в .part цел. Активные/качающиеся задачи не трогаем."""
        task = self._active.get(task_id)
        if task and task.paused:
            self._finish(task)   # снимает из _active

    # ── Внутренняя логика ─────────────────────────────────────────────────────

    async def _run(self, task: DownloadTask) -> None:
        async with self._semaphore:
            if task.cancelled:
                self._finish(task)
                self._bus.emit(DownloadCancelledEvent(task_id=task.task_id))
                return

            provider = task.provider
            snap     = task.snapshot
            exe      = provider.resolve_exe()
            source   = self._provider_source(provider)

            # Сообщаем репозиторию о старте — он запишет snapshot в БД.
            # Только один раз: resume перезапускает _run, повторно слать не нужно.
            if not task.started:
                task.started = True
                self._bus.emit(DownloadStartedEvent(
                    task_id=task.task_id,
                    snapshot=snap,
                    source=source,
                ))

            if snap.download_path:
                try:
                    os.makedirs(snap.download_path, exist_ok=True)
                except Exception:
                    self._log.exception("Failed to create download directory: %s", snap.download_path)

            cmd_args = provider.build_command(exe, snap)
            returncode = 0

            def on_line(line: str) -> None:
                if task.cancelled:
                    return
                pct = provider.parse_progress(line)
                if pct is None:
                    self._write_log(line, source)
                # abs(): прогресс может и убывать (новый файл/поток у yt-dlp,
                # смена фазы у торрента) — иначе бар застревает на прежнем максимуме.
                if pct is not None and abs(pct - task._last_pct) >= 0.01:
                    task._last_pct = pct
                    status = provider.format_status(line)
                    self._bus.emit(DownloadProgressEvent(
                        task_id=task.task_id, pct=pct, status=status[:80],
                        source=source,
                    ))
                elif any(tag in line for tag in provider.post_processing_tags()):
                    self._bus.emit(DownloadPostprocessingEvent(
                        task_id=task.task_id,
                        source=source,
                    ))

            def on_finish(rc: int) -> None:
                nonlocal returncode
                returncode = rc

            try:
                await provider.run(cmd_args, on_line, on_finish)
            except Exception as err:
                self._log.exception("Download process failed: %s", snap.url)
                self._finish(task)
                self._bus.emit(DownloadCompletedEvent(
                    task_id=task.task_id, success=False,
                    message=f"OS error: {err}",   # для БД — английский технический текст
                    error_detail=str(err),
                    source=source,
                ))
                return

            # Пауза: процесс убит, но задачу НЕ финализируем — она ждёт resume().
            # Выход из `async with` освобождает слот семафора; partial цел в .part.
            if task.paused:
                return

            if task.cancelled:
                self._finish(task)
                self._bus.emit(DownloadCancelledEvent(
                    task_id=task.task_id,
                    source=source,
                ))
                return

            success = returncode == 0
            # Технический текст для БД; перевод для UI строится в main_screen
            message = "" if success else f"Exit code {returncode}"
            if not success:
                get_logger(source).error("Process finished with return code %s", returncode)
            self._finish(task)
            self._bus.emit(DownloadCompletedEvent(
                task_id=task.task_id, success=success, message=message,
                error_code=returncode if not success else None,
                source=source,
            ))



    def _finish(self, task: DownloadTask) -> None:
        self._active.pop(task.task_id, None)

    @staticmethod
    def _provider_source(provider: "DownloadProvider") -> str:
        return getattr(provider, "SOURCE_NAME", type(provider).__name__)

    @staticmethod
    def _write_log(line: str, source: str) -> None:
        get_logger(source).info(line)
