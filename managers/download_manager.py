"""
DownloadManager — владеет очередью загрузок.

Не знает про yt-dlp, aria2c или любой другой конкретный инструмент.
Работает только через протокол DownloadProvider.
"""

import asyncio
import contextlib
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from app_logging import get_logger
from config import (
    SEED_LOG_INTERVAL_SECONDS, DEFAULT_MAX_PARALLEL, MAX_PARALLEL_CEILING,
    ERROR_TAIL_LINES,
)
from managers.snapshot import DownloadSnapshot
from events import (
    EventBus,
    SettingsChangedEvent,
    DownloadStartedEvent,
    DownloadProgressEvent,
    DownloadPostprocessingEvent,
    DownloadCompletedEvent,
    DownloadCancelledEvent,
    DownloadPausedEvent,
    DownloadResumedEvent,
    DownloadSeedingEvent,
)

if TYPE_CHECKING:
    from managers.providers import DownloadProvider

# (async_fn, *args) — в Flet: page.run_task
TaskRunner = Callable[..., Any]


# ── Внутреннее состояние одной задачи ────────────────────────────────────────

@dataclass
class DownloadTask:
    task_id:   str
    snapshot:  DownloadSnapshot
    provider:  "DownloadProvider"
    cancelled: bool  = False
    paused:    bool  = False   # на паузе: процесс убит, partial цел, задача ждёт resume
    seed:      bool  = False   # задача-раздача: завершение/стоп → запись снова 'completed'
    started:   bool  = False   # DownloadStartedEvent уже отправлен (не дублируем на resume)
    _last_pct: float = -1.0   # последний эмитированный прогресс; -1 = ещё не было
    _last_seed_log: float = -1e9   # monotonic последнего залогированного SEED (троттлинг)
    # Кольцевой буфер последних НЕ-прогрессных строк вывода — диагностика при сбое.
    _tail: deque = field(default_factory=lambda: deque(maxlen=ERROR_TAIL_LINES), repr=False)
    _handle:   Optional[asyncio.Task] = field(default=None, repr=False)


# ── Менеджер ──────────────────────────────────────────────────────────────────

class DownloadManager:

    def __init__(self,
                 provider_factories: Dict[str, Callable[[], "DownloadProvider"]],
                 default_provider: str,
                 bus: EventBus,
                 task_runner: TaskRunner,
                 max_parallel: Optional[Callable[[], int]] = None) -> None:
        """
        provider_factories — реестр {ключ: callable без аргументов → новый DownloadProvider}.
            Пример: {"yt-dlp": lambda: YtDlpProvider(paths), "aria2c": lambda: Aria2cProvider(paths)}
        default_provider — ключ провайдера по умолчанию (когда add() вызван без выбора).
        task_runner — планировщик async-задач (в app.py: page.run_task).
        max_parallel — поставщик текущего лимита одновременных загрузок
            (в Services: lambda: state.max_parallel). Читается динамически:
            смена настройки применяется без пересоздания менеджера.
        """
        self._provider_factories = provider_factories
        self._default_provider   = default_provider
        self._task_runner        = task_runner
        self._bus                = bus
        self._log                = get_logger("app")

        # Слоты параллельности. Семафор не подходит: его ёмкость фиксируется
        # при создании, а лимит меняется в настройках на лету. Вместо него —
        # счётчик + Event: ожидающие перепроверяют условие при каждом сигнале.
        self._max_parallel_fn = max_parallel or (lambda: DEFAULT_MAX_PARALLEL)
        self._running   = 0                  # задач внутри _run (между acquire/release)
        self._slot_free = asyncio.Event()
        # Лимит могли увеличить — разбудить ожидающих перепроверить условие.
        self._bus.on(SettingsChangedEvent, lambda _e: self._slot_free.set())

        self._active: Dict[str, DownloadTask] = {}

    def _make_provider(self, provider_key: Optional[str]) -> "DownloadProvider":
        """Создать провайдер по ключу; неизвестный/пустой ключ → провайдер по умолчанию."""
        factory = self._provider_factories.get(provider_key or self._default_provider) \
            or self._provider_factories[self._default_provider]
        return factory()

    # ── Слоты параллельности ──────────────────────────────────────────────────

    @property
    def max_parallel(self) -> int:
        """Текущий лимит одновременных загрузок (кламп на случай мусора в конфиге)."""
        try:
            n = int(self._max_parallel_fn())
        except (TypeError, ValueError):
            n = DEFAULT_MAX_PARALLEL
        return max(1, min(MAX_PARALLEL_CEILING, n))

    async def _acquire_slot(self) -> None:
        """Дождаться свободного слота. Лимит перечитывается на каждой проверке."""
        while self._running >= self.max_parallel:
            self._slot_free.clear()
            await self._slot_free.wait()
        self._running += 1

    def _release_slot(self) -> None:
        self._running -= 1
        self._slot_free.set()

    @contextlib.asynccontextmanager
    async def _slot(self):
        """Слот как контекст-менеджер (бывший asyncio.Semaphore в _run)."""
        await self._acquire_slot()
        try:
            yield
        finally:
            self._release_slot()

    # ── Публичный API ─────────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        # Паузные задачи не качаются и не занимают слот — в счёт ёмкости не идут.
        return sum(1 for t in self._active.values() if not t.paused)

    @property
    def at_capacity(self) -> bool:
        return self.active_count >= self.max_parallel

    def is_active_url(self, url: str) -> bool:
        """Уже идёт загрузка с этим URL? Нельзя качать тот же URL дважды
        одновременно: совпадут временные .part-папки (детерминированы по URL) и
        процессы подерутся за файлы."""
        return any(t.snapshot.url == url for t in self._active.values())

    def active_temp_dirs(self) -> set[str]:
        """Временные папки активных загрузок (чтобы ручная очистка их не трогала)."""
        return {
            pd for t in self._active.values()
            if (pd := t.provider.temp_dir())
        }

    def add(self, snapshot: DownloadSnapshot, provider_key: Optional[str] = None,
            task_id: Optional[str] = None) -> Optional[str]:
        """Запустить загрузку (или раздачу, если snapshot.seed) выбранным провайдером.
        task_id можно передать (возобновление/раздача переиспользуют запись истории).
        Возвращает task_id или None если exe не найден."""
        provider = self._make_provider(provider_key)
        if not provider.resolve_exe():
            return None

        task_id  = task_id or str(uuid.uuid4())
        task     = DownloadTask(task_id=task_id, snapshot=snapshot, provider=provider,
                                seed=snapshot.seed)
        self._active[task_id] = task
        if snapshot.seed:   # запись истории сразу помечается раздающейся
            self._bus.emit(DownloadSeedingEvent(
                task_id=task_id, source=self._provider_source(provider)))
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
        return bool(task and task.provider.SUPPORTS_PAUSE)

    def is_paused(self, task_id: str) -> bool:
        """Задача жива в этой сессии и стоит на паузе (ждёт resume).
        Единый источник истины о паузе — UI и оркестратор не ведут своих списков."""
        task = self._active.get(task_id)
        return bool(task and task.paused and not task.cancelled)

    def drop(self, task_id: str) -> None:
        """Выгрузить ПАУЗНУЮ задачу из активных — она «припаркована» в истории
        (статус incomplete) и будет возобновлена реконструкцией. Процесс уже убит,
        partial в .part цел. Активные/качающиеся задачи не трогаем."""
        task = self._active.get(task_id)
        if task and task.paused:
            self._finish(task)   # снимает из _active

    # ── Внутренняя логика ─────────────────────────────────────────────────────

    async def _run(self, task: DownloadTask) -> None:
        async with self._slot():
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
                provider.observe_line(line)   # провайдер собирает своё (финальный путь и т.п.)
                pct = provider.parse_progress(line)
                if pct is None:
                    # При раздаче aria2 сыплет строки-readout (~1/с): и SEED, и фаза
                    # метаданных magnet ([#gid 0B/0B …]). Любую такую строку ([#…)
                    # логируем редко; остальное (ошибки/notice) — как обычно.
                    if task.seed and "[#" in line:
                        now = time.monotonic()
                        if now - task._last_seed_log < SEED_LOG_INTERVAL_SECONDS:
                            return
                        task._last_seed_log = now
                    task._tail.append(line)   # хвост для диагностики при сбое
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
                # Сбой раздачи не ошибка контента — запись остаётся завершённой.
                self._bus.emit(DownloadCompletedEvent(
                    task_id=task.task_id, success=task.seed,
                    message="" if task.seed else f"OS error: {err}",
                    error_detail="" if task.seed else str(err),
                    output_tail="" if task.seed else "\n".join(task._tail),
                    source=source,
                ))
                return

            # Раздача завершилась/остановлена — контент цел, запись снова 'completed'.
            if task.seed:
                self._finish(task)
                self._bus.emit(DownloadCompletedEvent(
                    task_id=task.task_id, success=True, message="", source=source))
                return

            # Пауза: процесс убит, но задачу НЕ финализируем — она ждёт resume().
            # Выход из `async with` освобождает слот параллельности; partial цел в .part.
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
                output_tail="" if success else "\n".join(task._tail),
                file_path=provider.final_path() if success else "",
                source=source,
            ))



    def _finish(self, task: DownloadTask) -> None:
        self._active.pop(task.task_id, None)

    @staticmethod
    def _provider_source(provider: "DownloadProvider") -> str:
        return provider.SOURCE_NAME

    @staticmethod
    def _write_log(line: str, source: str) -> None:
        get_logger(source).info(line)
