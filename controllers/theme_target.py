"""
controllers/theme_target.py — миксин для применения темы без ручного перечисления виджетов.

Проблема (OCP):
  Каждый экран дублировал apply_theme() с явным перечислением виджетов по полю темы.
  Добавление нового цвета в ThemeConfig требовало правки в трёх местах.

Решение:
  Экран наследует ThemeTarget и регистрирует виджеты прямо при создании —
  register_*() возвращает переданный виджет, поэтому регистрация встраивается
  в строку создания без отдельной «фазы регистрации»:
      self.header_main = self.register_headers(ft.Text("..."))
      self.url_input   = self.register_accents(ft.TextField(...))
      self.download_btn = self.register_buttons(ft.Button(...))

  Можно по-прежнему регистрировать пачкой (вернётся кортеж, его обычно игнорируют):
      self.register_progress(self.progress_bar, self.progress_text)

  После этого apply_theme() из ThemeTarget применяется автоматически:
  достаточно вызвать super().apply_theme(t) или вообще не переопределять метод.

Расширение:
  Новое поле в ThemeConfig + новый register_*() в миксине.
  Экраны, которым это поле нужно, добавляют один вызов register_*().
  Экраны, которым не нужно — не меняются.
"""

from __future__ import annotations

import flet as ft

from config import ThemeConfig, hex_to_flet


class ThemeTarget:
    """
    Миксин, заменяющий ручной apply_theme() декларативной регистрацией виджетов.

    Наследуй в классе экрана и оборачивай виджеты в register_*() при создании.
    apply_theme() переопределять не нужно — достаточно вызвать super().apply_theme(t).
    """

    def __init__(self) -> None:
        self._theme_headers:   list = []
        self._theme_switches:  list = []
        self._theme_accents:   list = []
        self._theme_buttons:   list = []
        self._theme_cards:     list = []
        self._theme_progress:  list = []
        self._theme_text_labels: list = []
        self._theme_secondary_text: list = []
        self._theme_muted_text:     list = []
        self._theme_surfaces:       list = []
        self._theme_borders:        list = []
        self._theme_dividers:       list = []
        self._theme_button_texts:   list = []

    # ── Регистрация виджетов ──────────────────────────────────────────────────
    #
    # Каждый register_*() возвращает переданный виджет, чтобы регистрацию можно
    # было встроить в строку создания:
    #     self.header_main = self.register_headers(ft.Text("..."))
    # При нескольких аргументах возвращается кортеж (как правило игнорируется):
    #     self.register_progress(self.progress_bar, self.progress_text)

    @staticmethod
    def _ret(widgets: tuple):
        """Вернуть единственный виджет либо кортеж — для встраивания в присваивание."""
        return widgets[0] if len(widgets) == 1 else widgets

    def register_headers(self, *widgets: ft.Text):
        """ft.Text, которым ставится .color = header_color."""
        self._theme_headers.extend(widgets)
        return self._ret(widgets)

    def register_switches(self, *widgets: ft.Switch):
        """ft.Switch, которым ставится .active_color = switch_color."""
        self._theme_switches.extend(widgets)
        return self._ret(widgets)

    def register_accents(self, *widgets):
        """TextField / Dropdown, которым ставится .focused_border_color = accent_color."""
        self._theme_accents.extend(widgets)
        return self._ret(widgets)

    def register_buttons(self, *widgets: ft.Button):
        """ft.Button, которым ставится .bgcolor = button_color."""
        self._theme_buttons.extend(widgets)
        return self._ret(widgets)

    def register_cards(self, *widgets: ft.Container):
        """ft.Container, которым ставится .bgcolor = card_color."""
        self._theme_cards.extend(widgets)
        return self._ret(widgets)

    def register_progress(self, *widgets):
        """ft.ProgressBar / ft.Text, которым ставится .color = progress_color."""
        self._theme_progress.extend(widgets)
        return self._ret(widgets)

    def register_text_labels(self, *widgets: ft.Text):
        """ft.Text, которым ставится .color = text_color."""
        self._theme_text_labels.extend(widgets)
        return self._ret(widgets)

    def register_secondary_text(self, *widgets: ft.Text):
        """ft.Text вторичного уровня — .color = text_secondary_color."""
        self._theme_secondary_text.extend(widgets)
        return self._ret(widgets)

    def register_muted_text(self, *widgets: ft.Text):
        """ft.Text приглушённый (хинты, таймстемпы, пустые состояния) — .color = text_muted_color."""
        self._theme_muted_text.extend(widgets)
        return self._ret(widgets)

    def register_surfaces(self, *widgets: ft.Container):
        """Вложенные контейнеры/чипы — .bgcolor = surface_color."""
        self._theme_surfaces.extend(widgets)
        return self._ret(widgets)

    def register_borders(self, *widgets: ft.Container):
        """ft.Container, которым ставится .border = Border.all(1, border_color)."""
        self._theme_borders.extend(widgets)
        return self._ret(widgets)

    def register_dividers(self, *widgets: ft.Divider):
        """ft.Divider, которым ставится .color = border_color."""
        self._theme_dividers.extend(widgets)
        return self._ret(widgets)

    def register_button_texts(self, *widgets: ft.Text):
        """ft.Text/ft.Icon на кнопках — .color = button_text_color."""
        self._theme_button_texts.extend(widgets)
        return self._ret(widgets)

    # ── Универсальный apply_theme ─────────────────────────────────────────────

    def apply_theme(self, t: ThemeConfig) -> None:
        """
        Применить ThemeConfig ко всем зарегистрированным виджетам.
        Экранам не нужно переопределять этот метод — только вызывать register_*().
        Если экрану нужна дополнительная логика, он переопределяет метод и вызывает super().
        """
        header_c    = hex_to_flet(t.header_color)
        switch_c    = hex_to_flet(t.switch_color)
        accent      = hex_to_flet(t.accent_color)
        button_c    = hex_to_flet(t.button_color)
        button_tc   = hex_to_flet(t.button_text_color)
        card_c      = hex_to_flet(t.card_color)
        progress_c  = hex_to_flet(t.progress_color)
        text_c      = hex_to_flet(t.text_color)
        secondary_c = hex_to_flet(t.text_secondary_color)
        muted_c     = hex_to_flet(t.text_muted_color)
        surface_c   = hex_to_flet(t.surface_color)
        border_c    = hex_to_flet(t.border_color)

        for w in self._theme_headers:
            w.color = header_c
        for w in self._theme_switches:
            w.active_color = switch_c
        for w in self._theme_accents:
            w.focused_border_color = accent
        for w in self._theme_buttons:
            w.bgcolor = button_c
        for w in self._theme_cards:
            w.bgcolor = card_c
        for w in self._theme_progress:
            w.color = progress_c
        for w in self._theme_text_labels:
            w.color = text_c
        for w in self._theme_secondary_text:
            w.color = secondary_c
        for w in self._theme_muted_text:
            w.color = muted_c
        for w in self._theme_button_texts:
            w.color = button_tc
        for w in self._theme_surfaces:
            w.bgcolor = surface_c
        for w in self._theme_borders:
            w.border = ft.Border.all(1, border_c)
        for w in self._theme_dividers:
            w.color = border_c
