"""
ClipboardController — слежение за буфером обмена.

Ответственность:
  - Фоновый опрос буфера (page.clipboard), пока включён state.clipboard_watch.
  - Распознавание ссылок на загрузку (extract_download_urls) и публикация
    ClipboardUrlEvent — поле URL пополняет сам MainScreen по подписке.

Не знает про экраны и виджеты (только page для доступа к буферу и шина).
Кнопка-тумблер живёт в тулбаре NavigationController и лишь меняет state —
контроллер перечитывает флаг на каждом цикле, отдельных сигналов не нужно.

Важно: при ВКЛЮЧЕНИИ слежения текущее содержимое буфера принимается за
базовую точку и не трогается — событие вызывают только НОВЫЕ копирования.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import flet as ft

from app_logging import get_logger
from config import CLIPBOARD_POLL_SECONDS, CLIPBOARD_MAX_CHARS, safe_str
from events import AppClosingEvent, ClipboardUrlEvent
from managers.providers import extract_download_urls

if TYPE_CHECKING:
    from services import Services


class ClipboardController:

    def __init__(self, page: ft.Page, svc: "Services") -> None:
        self._page    = page
        self._svc     = svc
        self._log     = get_logger("app")
        self._stopped = False
        svc.bus.on(AppClosingEvent, lambda _e: self._stop())

    def _stop(self) -> None:
        self._stopped = True

    async def run(self) -> None:
        """Цикл опроса; запускается один раз (page.run_task в app.py) и живёт
        до закрытия приложения. Выключенное слежение = холостые тики."""
        last_seen:   str | None = None
        was_enabled: bool       = False

        while not self._stopped:
            try:
                enabled = self._svc.state.clipboard_watch
                if enabled:
                    text = safe_str(await self._page.clipboard.get())
                    if not was_enabled:
                        # Только что включили: запомнить как базу, не обрабатывать.
                        last_seen = text
                    elif text and text != last_seen:
                        last_seen = text
                        if len(text) <= CLIPBOARD_MAX_CHARS:
                            urls = extract_download_urls(text)
                            if urls:
                                self._svc.bus.emit(ClipboardUrlEvent(urls=tuple(urls)))
                was_enabled = enabled
            except Exception:
                # Буфер бывает занят другим процессом / содержит не-текст —
                # это не ошибка приложения, просто пропускаем тик.
                self._log.debug("Clipboard poll failed", exc_info=True)
            await asyncio.sleep(CLIPBOARD_POLL_SECONDS)
