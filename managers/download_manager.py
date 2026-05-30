"""
DownloadManager — владеет очередью загрузок.

Не знает про yt-dlp, aria2c или любой другой конкретный инструмент.
Работает только через протокол DownloadProvider.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, TYPE_CHECKING

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
                 db=None) -> None:
        """
        provider_factory — callable без аргументов, возвращает новый DownloadProvider.
        Пример: lambda: YtDlpProvider(base_dir, tools_dir)
        db — DownloadRepository для сохранения thumbnail после загрузки (опционально).
        """
        self._provider_factory = provider_factory
        self._log_path         = log_path
        self._bus              = bus
        self._db               = db

        self._semaphore = asyncio.Semaphore(MAX_PARALLEL)
        self._active: Dict[str, DownloadTask] = {}

    # ── Публичный API ─────────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def at_capacity(self) -> bool:
        return self.active_count >= MAX_PARALLEL

    def add(self, page, snapshot: DownloadSnapshot) -> Optional[str]:
        """Запустить загрузку. Возвращает task_id или None если exe не найден."""
        provider = self._provider_factory()
        if not provider.resolve_exe():
            return None

        task_id  = str(uuid.uuid4())
        task     = DownloadTask(task_id=task_id, snapshot=snapshot, provider=provider)
        self._active[task_id] = task
        task._handle = page.run_task(self._run, task)
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

            # Сообщаем репозиторию о старте — он запишет snapshot в БД
            self._bus.emit(DownloadStartedEvent(
                task_id=task.task_id,
                snapshot=snap,
                source=type(provider).__name__,
            ))

            if snap.download_path:
                try:
                    os.makedirs(snap.download_path, exist_ok=True)
                except Exception:
                    pass

            cmd_args = provider.build_command(exe, snap)
            returncode_holder = [0]

            def on_line(line: str) -> None:
                if task.cancelled:
                    return
                pct = provider.parse_progress(line)
                if pct is None:
                    self._write_log(line)
                if pct is not None and pct - task._last_pct >= 0.01:
                    task._last_pct = pct
                    status = line.replace("[download]", "").strip()
                    self._bus.emit(DownloadProgressEvent(
                        task_id=task.task_id, pct=pct, status=status[:80],
                        source=type(provider).__name__,
                    ))
                elif any(tag in line for tag in provider.post_processing_tags()):
                    self._bus.emit(DownloadPostprocessingEvent(
                        task_id=task.task_id,
                        source=type(provider).__name__,
                    ))

            def on_finish(rc: int) -> None:
                returncode_holder[0] = rc

            try:
                await provider.run(cmd_args, on_line, on_finish)
            except Exception as err:
                self._finish(task)
                self._bus.emit(DownloadCompletedEvent(
                    task_id=task.task_id, success=False,
                    message=f"Ошибка ОС: {err}",
                    source=type(provider).__name__,
                ))
                return

            if task.cancelled:
                self._finish(task)
                self._bus.emit(DownloadCancelledEvent(
                    task_id=task.task_id,
                    source=type(provider).__name__,
                ))
                return

            success = returncode_holder[0] == 0
            message = "Загрузка завершена!" if success else f"Ошибка (код {returncode_holder[0]})"
            self._finish(task)
            self._bus.emit(DownloadCompletedEvent(
                task_id=task.task_id, success=success, message=message,
                source=type(provider).__name__,
            ))

            # Скачать thumbnail и сохранить BLOB в БД (только при успехе)
            if success and self._db is not None and hasattr(provider, "fetch_thumbnail"):
                try:
                    thumb_data = await provider.fetch_thumbnail(exe, snap.url)
                    if thumb_data:
                        self._db.save_thumbnail(task.task_id, thumb_data)
                except Exception:
                    pass

    def _finish(self, task: DownloadTask) -> None:
        self._active.pop(task.task_id, None)

    def _write_log(self, line: str) -> None:
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
