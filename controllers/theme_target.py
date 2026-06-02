"""
controllers/theme_target.py — миксин для применения темы без ручного перечисления виджетов.

Проблема (OCP):
  Каждый экран дублировал apply_theme() с явным перечислением виджетов по полю темы.
  Добавление нового цвета в ThemeConfig требовало правки в трёх местах.

Решение:
  Экран наследует ThemeTarget и при построении виджетов вызывает register_*():
      self.register_headers(self.header_main, self.header_queue)
      self.register_switches(self.audio_switch)
      self.register_accents(self.url_input)
      self.register_buttons(self.download_btn)
      self.register_cards(self.main_card)
      self.register_text_labels(self.folder_label)    # text_color
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

    Наследуй в классе экрана и вызывай register_*() в _build_widgets().
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

    # ── Регистрация виджетов ──────────────────────────────────────────────────

    def register_headers(self, *widgets: ft.Text) -> None:
        """ft.Text, которым ставится .color = header_color."""
        self._theme_headers.extend(widgets)

    def register_switches(self, *widgets: ft.Switch) -> None:
        """ft.Switch, которым ставится .active_color = switch_color."""
        self._theme_switches.extend(widgets)

    def register_accents(self, *widgets) -> None:
        """TextField / Dropdown, которым ставится .focused_border_color = accent_color."""
        self._theme_accents.extend(widgets)

    def register_buttons(self, *widgets: ft.Button) -> None:
        """ft.Button, которым ставится .bgcolor = button_color."""
        self._theme_buttons.extend(widgets)

    def register_cards(self, *widgets: ft.Container) -> None:
        """ft.Container, которым ставится .bgcolor = card_color."""
        self._theme_cards.extend(widgets)

    def register_progress(self, *widgets) -> None:
        """ft.ProgressBar / ft.Text, которым ставится .color = progress_color."""
        self._theme_progress.extend(widgets)

    def register_text_labels(self, *widgets: ft.Text) -> None:
        """ft.Text, которым ставится .color = text_color."""
        self._theme_text_labels.extend(widgets)

    # ── Универсальный apply_theme ─────────────────────────────────────────────

    def apply_theme(self, t: ThemeConfig) -> None:
        """
        Применить ThemeConfig ко всем зарегистрированным виджетам.
        Экранам не нужно переопределять этот метод — только вызывать register_*().
        Если экрану нужна дополнительная логика, он переопределяет метод и вызывает super().
        """
        header_c   = hex_to_flet(t.header_color)
        switch_c   = hex_to_flet(t.switch_color)
        accent     = hex_to_flet(t.accent_color)
        button_c   = hex_to_flet(t.button_color)
        card_c     = hex_to_flet(t.card_color)
        progress_c = hex_to_flet(t.progress_color)
        text_c     = hex_to_flet(t.text_color)

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
