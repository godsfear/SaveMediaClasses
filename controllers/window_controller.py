"""
WindowController — управление окном приложения.

Ответственность:
  - Применить сохранённую геометрию окна при старте.
  - Сохранить текущую геометрию + state в config.json.
  - Перехватить событие закрытия и корректно завершить приложение.
  - Реализовать принудительный выход (кнопка Exit).

Намеренно не знает про экраны и навигацию.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import flet as ft

from app_logging import get_logger
from events import SettingsChangedEvent, AppClosingEvent, WindowStateEvent

if TYPE_CHECKING:
    from services import Services


def window_event_visibility(ev: str) -> "bool | None":
    """Видимость окна по имени события: True — на виду, False — скрыто/без
    фокуса, None — событие не про видимость (resize/move/close...).
    Скрывающие маркеры проверяются первыми: "unmaximize" содержит "maximize"."""
    if any(m in ev for m in ("blur", "minimize", "hide")):
        return False
    if any(m in ev for m in ("focus", "restore", "show", "maximize")):
        return True
    return None


class WindowController:

    def __init__(
        self,
        page: ft.Page,
        svc: "Services",
    ) -> None:
        """
        page — Flet Page.
        svc  — DI-контейнер (через svc.bus публикуются SettingsChangedEvent/AppClosingEvent).
        """
        self._page = page
        self._svc  = svc
        self._log  = get_logger("app")

    # ── Публичный API ─────────────────────────────────────────────────────────

    def apply_geometry(self) -> None:
        """Применить сохранённую геометрию окна и показать его."""
        geo = self._svc.state.window
        page = self._page

        page.window.width  = geo.width
        page.window.height = geo.height
        page.window.left   = geo.left
        page.window.top    = geo.top

        if page.platform in [
            ft.PagePlatform.WINDOWS,
            ft.PagePlatform.MACOS,
            ft.PagePlatform.LINUX,
        ]:
            page.window.min_width     = 500
            page.window.min_height    = 550
            page.window.prevent_close = True
            # Окно НЕ прячем: в flet build (нативный flutter) повторный показ
            # из main() не закрепляется и окно остаётся скрытым. Показываем сразу.

    def reveal(self) -> None:
        """Показать окно после page.add() — вызывать после финальной инициализации."""
        if self._page.platform in [
            ft.PagePlatform.WINDOWS,
            ft.PagePlatform.MACOS,
            ft.PagePlatform.LINUX,
        ]:
            self._page.window.visible = True

    def register_close_handler(self) -> None:
        """Подписаться на событие закрытия окна."""
        self._page.window.on_event = self._handle_window_event

    def save(self) -> None:
        """Сохранить текущую геометрию окна и state."""
        page = self._page
        w, h = page.window.width, page.window.height
        l, t = page.window.left,  page.window.top
        state = self._svc.state
        if w and w > 10:    state.window.width  = int(w)
        if h and h > 10:    state.window.height = int(h)
        if l is not None:   state.window.left   = int(l)
        if t is not None:   state.window.top    = int(t)
        self._svc.bus.emit(SettingsChangedEvent())

    # ── Обработчики ───────────────────────────────────────────────────────────

    async def force_exit(self, _) -> None:
        """Обработчик кнопки Exit — сохранить и уничтожить окно."""
        try:
            self.save()
        except Exception:
            self._log.exception("Failed to save config before exit")
        self._close()
        await self._page.window.destroy()

    async def _handle_window_event(self, e) -> None:
        """Перехватчик событий окна: закрытие (крестик / Alt+F4) + трансляция
        видимости в шину (WindowStateEvent — для подавления уведомлений)."""
        ev = str(getattr(e, "type", None) or getattr(e, "data", None)).lower()
        visibility = window_event_visibility(ev)
        if visibility is not None:
            self._svc.bus.emit(WindowStateEvent(in_view=visibility))
        if "close" in ev:
            try:
                self.save()
            except Exception:
                self._log.exception("Failed to save config before window close")
            self._close()
            await self._page.window.destroy()

    def _close(self) -> None:
        """Снять блокировку закрытия и уведомить подписчиков (teardown через AppClosingEvent)."""
        self._page.window.prevent_close = False
        self._page.window.on_event      = None
        try:
            self._svc.bus.emit(AppClosingEvent())
        except Exception:
            self._log.exception("Teardown failed on window close")
        try:
            self._page.update()
        except Exception as exc:
            self._log.debug("page.update on close skipped: %s", exc)
