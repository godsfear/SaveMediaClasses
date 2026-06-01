"""
ThemeController — применение темы ко всем экранам приложения.

Ответственность:
  - Хранить ссылки на все экраны, реализующие apply_theme().
  - Читать ThemeConfig из AppState и раздавать его экранам.
  - Обновлять цвет AppBar, если он уже создан.

Не знает про навигацию, сохранение или язык.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import flet as ft

from config import hex_to_flet

if TYPE_CHECKING:
    from config import ThemeConfig
    from services import Services


class Themeable(Protocol):
    """Контракт экрана, который умеет применять тему."""
    def apply_theme(self, t: "ThemeConfig") -> None: ...


class ThemeController:

    def __init__(
        self,
        page: ft.Page,
        svc: "Services",
        screens: list[Themeable],
    ) -> None:
        """
        screens — список экранов в порядке применения темы.
                  Новый экран = просто добавить в список при вызове.
        """
        self._page    = page
        self._svc     = svc
        self._screens = screens

    # ── Публичный API ─────────────────────────────────────────────────────────

    def apply(self) -> None:
        """Применить текущую тему из state ко всем экранам и AppBar."""
        t = self._svc.state.theme
        for screen in self._screens:
            screen.apply_theme(t)
        self._update_appbar(t)

    # ── Приватное ─────────────────────────────────────────────────────────────

    def _update_appbar(self, t: "ThemeConfig") -> None:
        if self._page.appbar:
            self._page.appbar.bgcolor = hex_to_flet(t.appbar_color)
