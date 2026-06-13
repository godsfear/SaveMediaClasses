"""
ThemeController — применение темы ко всем экранам приложения.

Ответственность:
  - Хранить ссылки на все экраны, реализующие apply_theme().
  - Читать ThemeConfig из AppState и раздавать его экранам.
  - Выставлять page.theme_mode и seed Material-палитры (от accent_color).
  - Обновлять цвета AppBar/BottomAppBar, если они уже созданы.

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
        """Применить текущую тему из state ко всем экранам, странице и барам."""
        t = self._svc.state.theme
        self._page.theme_mode = (
            ft.ThemeMode.LIGHT if self._svc.state.theme_mode == "light"
            else ft.ThemeMode.DARK
        )
        # Seed Material-палитры Flet: от него зависят элементы вне токенов темы
        # (меню дропдаунов, шевроны ExpansionTile, TextButton в диалогах).
        self._page.theme = ft.Theme(color_scheme_seed=hex_to_flet(t.accent_color))
        self._page.bgcolor = hex_to_flet(t.bg_color)
        for screen in self._screens:
            screen.apply_theme(t)
        self._update_bars(t)

    # ── Приватное ─────────────────────────────────────────────────────────────

    def _update_bars(self, t: "ThemeConfig") -> None:
        if self._page.appbar:
            self._page.appbar.bgcolor = hex_to_flet(t.appbar_color)
        if self._page.bottom_appbar:
            self._page.bottom_appbar.bgcolor = hex_to_flet(t.bottom_bar_color)
