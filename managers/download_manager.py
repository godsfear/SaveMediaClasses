"""
DownloadManager — владеет очередью загрузок.

Не знает про yt-dlp, aria2c или любой другой конкретный инструмент.
Работает только через протокол DownloadProvider.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from app_logging import get_logger
from events import (
    EventBus,
    DownloadStartedEvent,
    DownloadProgressEvent,
    DownloadPostprocessingEvent,
    DownloadCompletedEvent,
    DownloadCancelledEvent,
)

if TYPE_CHECKING:
    from managers.providers import DownloadProvider

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


# ── Внутреннее состояние одной задачи ────────────────────────────────────────

@dataclass
class DownloadTask:
    task_id:   str
    snapshot:  DownloadSnapshot
    provider:  "DownloadProvider"
    cancelled: bool  = False
    _last_pct: float = -1.0   # последний эмитированный прогресс; -1 = ещё не было
    _handle:   Optional[asyncio.Task] = field(default=None, repr=False)


# ── Менеджер ──────────────────────────────────────────────────────────────────

class DownloadManager:

    def __init__(self,
                 provider_factory: Callable[[], "DownloadProvider"],
                 log_path: str,
                 bus: EventBus,
                 task_runner: TaskRunner,
                 db=None) -> None:
        """
        provider_factory — callable без аргументов, возвращает новый DownloadProvider.
        Пример: lambda: YtDlpProvider()
        task_runner — планировщик async-задач (в app.py: page.run_task).
        db — DownloadRepository для сохранения thumbnail после загрузки (опционально).
        """
        self._provider_factory = provider_factory
        self._task_runner      = task_runner
        self._bus              = bus
        self._db               = db
        self._log              = get_logger("app")

        self._semaphore = asyncio.Semaphore(MAX_PARALLEL)
        self._active: Dict[str, DownloadTask] = {}

    # ── Публичный API ─────────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def at_capacity(self) -> bool:
        return self.active_count >= MAX_PARALLEL

    def add(self, snapshot: DownloadSnapshot) -> Optional[str]:
        """Запустить загрузку. Возвращает task_id или None если exe не найден."""
        provider = self._provider_factory()
        if not provider.resolve_exe():
            return None

        task_id  = str(uuid.uuid4())
        task     = DownloadTask(task_id=task_id, snapshot=snapshot, provider=provider)
        self._active[task_id] = task
        task._handle = self._task_runner(self._run, task)
        return task_id

    def cancel(self, task_id: str) -> None:
        task = self._active.get(task_id)
        if task and not task.cancelled:
            task.cancelled = True
            task.provider.cancel()

    def cancel_all(self) -> None:
        for task_id in list(self._active):
            self.cancel(task_id)

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

            # Сообщаем репозиторию о старте — он запишет snapshot в БД
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
                if pct is not None and pct - task._last_pct >= 0.01:
                    task._last_pct = pct
                    status = line.replace("[download]", "").strip()
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
