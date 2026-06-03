"""
events.py — типизированные события приложения + EventBus.

Правила:
  - Каждое событие — frozen dataclass (неизменяемо, безопасно передавать между слоями).
  - EventBus.emit() синхронный: все обработчики вызываются в том же asyncio-тике,
    откуда пришёл emit(). Это безопасно для Flet — page.update() можно вызывать
    прямо в обработчике.
  - Подписка через bus.on(EventType, handler) — возвращает функцию отписки.
  - Один EventBus на всё приложение, создаётся в app.py и передаётся вниз.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Type, TypeVar

from app_logging import get_logger

E = TypeVar("E")


# ── Загрузки ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DownloadProgressEvent:
    task_id: str
    pct:     float
    status:  str
    source:  str = "yt-dlp"   # будущий aria2c просто ставит source="aria2c"

@dataclass(frozen=True)
class DownloadPostprocessingEvent:
    task_id: str
    source:  str = "yt-dlp"

@dataclass(frozen=True)
class DownloadCompletedEvent:
    task_id:      str
    success:      bool
    message:      str        # технический текст для БД (на английском)
    source:       str = "yt-dlp"
    error_code:   int | None = None  # код возврата процесса (только при success=False)
    error_detail: str = ""           # текст ошибки ОС (только при сбое запуска)

@dataclass(frozen=True)
class DownloadStartedEvent:
    """Эмитируется в момент старта загрузки — содержит полный снимок параметров.
    DownloadRepository использует его для записи в БД."""
    task_id:  str
    snapshot: object   # DownloadSnapshot — избегаем циклического импорта
    source:   str = "yt-dlp"

@dataclass(frozen=True)
class DownloadCancelledEvent:
    task_id: str
    source:  str = "yt-dlp"


# ── Инструменты (yt-dlp / ffmpeg) ─────────────────────────────────────────────

@dataclass(frozen=True)
class ToolsCheckedEvent:
    """Эмитируется после завершения проверки версий."""
    needs_update: bool

@dataclass(frozen=True)
class ToolsStatusMessageEvent:
    """Промежуточное сообщение во время проверки/обновления — для статус-бара."""
    message: str
    color:   str   # hex или ft.Colors.*


@dataclass(frozen=True)
class ToolsRestoredEvent:
    """Эмитируется при старте если проверка была недавно.
    Восстанавливает виджеты из сохранённого state без обращения к сети."""
    needs_update:     bool
    tool_versions:    dict   # {"yt-dlp": (local, remote, status_key), ...}
    mins_until_check: int


# ── Шина ──────────────────────────────────────────────────────────────────────

class EventBus:
    """
    Минималистичная синхронная шина событий.

    Использование:
        bus = EventBus()

        # Подписка
        unsub = bus.on(DownloadProgressEvent, handler)

        # Отписка
        unsub()

        # Публикация
        bus.emit(DownloadProgressEvent(task_id=..., pct=0.5, status="..."))
    """

    def __init__(self) -> None:
        self._handlers: Dict[type, List[Callable]] = {}
        self._log = get_logger("app")

    def on(self, event_type: Type[E], handler: Callable[[E], None]) -> Callable:
        """Подписаться на событие. Возвращает функцию отписки."""
        self._handlers.setdefault(event_type, []).append(handler)
        def unsubscribe():
            try:
                self._handlers[event_type].remove(handler)
            except (KeyError, ValueError):
                self._log.exception("Unsubscribe failed")
        return unsubscribe

    def emit(self, event: object) -> None:
        """Синхронно вызвать всех подписчиков данного типа события."""
        for handler in list(self._handlers.get(type(event), [])):
            try:
                handler(event)
            except Exception:
                # Один упавший обработчик не должен ломать остальных
                self._log.exception("Event handler failed for %s", type(event).__name__)
