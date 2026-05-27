"""
DownloadManager — владеет очередью загрузок.
Публикует события в EventBus вместо прямых колбэков.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from events import (
    EventBus,
    DownloadProgressEvent,
    DownloadPostprocessingEvent,
    DownloadCompletedEvent,
    DownloadCancelledEvent,
)
from managers.downloader import Downloader

MAX_PARALLEL = 5
_POST_PROCESSING_TAGS = ["[Merger]", "[Metadata]", "[Thumbnails]", "[ExtractAudio]", "[Modify]"]


# ── Снимок параметров на момент нажатия «Скачать» ────────────────────────────

@dataclass(frozen=True)
class DownloadSnapshot:
    """Неизменяемая копия параметров загрузки. Изменение настроек не затрагивает
    уже запущенные задачи."""
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
    task_id:    str
    snapshot:   DownloadSnapshot
    downloader: Downloader
    cancelled:  bool = False
    _handle:    Optional[asyncio.Task] = field(default=None, repr=False)


# ── Менеджер ──────────────────────────────────────────────────────────────────

class DownloadManager:

    def __init__(self, base_dir: str, tools_dir: str,
                 log_path: str, bus: EventBus) -> None:
        self._base_dir  = base_dir
        self._tools_dir = tools_dir
        self._log_path  = log_path
        self._bus       = bus

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
        """Запустить загрузку. Возвращает task_id или None если yt-dlp не найден."""
        dl = Downloader(self._base_dir, self._tools_dir)
        if not dl.resolve_yt_dlp():
            return None

        task_id = str(uuid.uuid4())
        task = DownloadTask(task_id=task_id, snapshot=snapshot, downloader=dl)
        self._active[task_id] = task
        task._handle = page.run_task(self._run, task)
        return task_id

    def cancel(self, task_id: str) -> None:
        task = self._active.get(task_id)
        if task and not task.cancelled:
            task.cancelled = True
            task.downloader.cancel()

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

            snap       = task.snapshot
            yt_dlp_exe = task.downloader.resolve_yt_dlp()

            if snap.download_path:
                try:
                    os.makedirs(snap.download_path, exist_ok=True)
                except Exception:
                    pass

            cmd_args = task.downloader.build_command(
                yt_dlp_exe=yt_dlp_exe,
                url=snap.url,
                download_path=snap.download_path,
                proxy_enabled=snap.proxy_enabled,
                proxy_address=snap.proxy_address,
                cookies_enabled=snap.cookies_enabled,
                cookies_browser=snap.cookies_browser,
                playlist_enabled=snap.playlist_enabled,
                embed_metadata=snap.embed_metadata,
                audio_only=snap.audio_only,
                yt_dlp_args=snap.yt_dlp_args,
                clean_titles=snap.clean_titles,
                save_to_source=snap.save_to_source,
            )

            returncode_holder = [0]

            def on_line(line: str) -> None:
                if task.cancelled:
                    return
                pct = Downloader.parse_progress(line)
                if pct is None:
                    self._write_log(line)
                if pct is not None:
                    status = line.replace("[download]", "").strip()
                    self._bus.emit(DownloadProgressEvent(
                        task_id=task.task_id, pct=pct, status=status[:80]
                    ))
                elif any(tag in line for tag in _POST_PROCESSING_TAGS):
                    self._bus.emit(DownloadPostprocessingEvent(task_id=task.task_id))

            def on_finish(rc: int) -> None:
                returncode_holder[0] = rc

            try:
                await task.downloader.run(cmd_args, on_line, on_finish)
            except Exception as err:
                self._finish(task)
                self._bus.emit(DownloadCompletedEvent(
                    task_id=task.task_id, success=False, message=f"Ошибка ОС: {err}"
                ))
                return

            if task.cancelled:
                self._finish(task)
                self._bus.emit(DownloadCancelledEvent(task_id=task.task_id))
                return

            success = returncode_holder[0] == 0
            message = "Загрузка завершена!" if success else f"Ошибка (код {returncode_holder[0]})"
            self._finish(task)
            self._bus.emit(DownloadCompletedEvent(
                task_id=task.task_id, success=success, message=message
            ))

    def _finish(self, task: DownloadTask) -> None:
        self._active.pop(task.task_id, None)

    def _write_log(self, line: str) -> None:
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
