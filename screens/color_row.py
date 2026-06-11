"""
screens/color_row.py — одна строка редактора цвета темы.

Инкапсулирует метку, hex-поле, превью и выпадающую палитру для ОДНОГО поля
ThemeConfig. Держит явные ссылки на свои виджеты и собственные field_key/
label_key, поэтому обновление из состояния (refresh) и перевод (relabel) НЕ
требуют обхода дерева виджетов и обратного поиска ключа по тексту метки —
именно эта хрупкость была в прежнем make_color_row + refresh_theme_fields.

Компонент — часть композиции SettingsScreen и сознательно обращается к её
инфраструктуре (state/bus/safe_update + register_* из ThemeTarget). Чтобы не
создавать циклический импорт, тип владельца берётся только под TYPE_CHECKING.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from config import PALETTE, hex_to_flet, is_valid_hex, safe_str
from events import SettingsChangedEvent, ThemeChangedEvent

if TYPE_CHECKING:
    from screens.settings_screen import SettingsScreen


class ColorRow:
    """Строка редактора одного цвета темы: метка + hex-поле + превью + палитра."""

    def __init__(self, owner: "SettingsScreen", field_key: str, label_key: str) -> None:
        self._owner    = owner
        self.field_key = field_key
        self.label_key = label_key

        current = getattr(owner._state.theme, field_key, "FFFFFF")

        self.label = owner.register_muted_text(ft.Text(
            getattr(owner._s, label_key, label_key),
            size=12, expand=True, color=ft.Colors.GREY_300,
        ))
        self._field = owner.register_accents(ft.TextField(
            value=current.upper().lstrip("#"),
            width=100, border_radius=6, text_size=13,
            capitalization=ft.TextCapitalization.CHARACTERS,
            max_length=6,
            content_padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            hint_text="RRGGBB",
            on_change=self._on_field_change,
        ))
        self._preview = owner.register_borders(ft.Container(
            width=28, height=28, border_radius=6,
            bgcolor=hex_to_flet(current),
            border=ft.Border.all(1, hex_to_flet(owner._state.theme.border_color)),
            on_click=self._toggle_palette,
        ))

        palette_grid = ft.Row(wrap=True, spacing=4, run_spacing=4, width=280)
        for c in PALETTE:
            palette_grid.controls.append(ft.Container(
                width=24, height=24, border_radius=4,
                bgcolor=f"#{c}", border=ft.Border.all(1, "#00000044"),
                tooltip=f"#{c}", on_click=lambda e, h=c: self._apply(h),
            ))
        # surface + border на одном контейнере — регистрации вкладываются.
        self._palette = owner.register_surfaces(owner.register_borders(ft.Container(
            content=palette_grid, bgcolor="#1e1e1e", border_radius=8,
            padding=8, border=ft.Border.all(1, "#333333"), visible=False,
        )))

        self.control = ft.Column([
            ft.Row([self.label, self._field, self._preview],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            self._palette,
        ], spacing=4, tight=True)

    # ── Реакции на ввод ───────────────────────────────────────────────────────

    def _apply(self, hex_val: str) -> None:
        """Клик по образцу палитры — применить цвет и скрыть палитру."""
        setattr(self._owner._state.theme, self.field_key, hex_val)
        self._field.value        = hex_val.upper()
        self._field.border_color = None
        self._preview.bgcolor    = hex_to_flet(hex_val)
        self._palette.visible    = False
        self._owner._bus.emit(ThemeChangedEvent())
        self._owner._bus.emit(SettingsChangedEvent())

    def _on_field_change(self, _e) -> None:
        val = safe_str(self._field.value).strip().lstrip("#").upper()
        if is_valid_hex(val):
            setattr(self._owner._state.theme, self.field_key, val)
            self._preview.bgcolor    = hex_to_flet(val)
            self._field.border_color = None
            self._owner._bus.emit(ThemeChangedEvent())
            self._owner._bus.emit(SettingsChangedEvent())
        else:
            self._field.border_color = hex_to_flet(
                self._owner._state.theme.status_error_color)
            self._owner._safe_update()

    def _toggle_palette(self, _e) -> None:
        self._palette.visible = not self._palette.visible
        self._owner._safe_update()

    # ── Синхронизация (без обхода дерева) ──────────────────────────────────────

    def refresh(self) -> None:
        """Перечитать цвет из состояния — после reset / смены режима / применения набора."""
        val = getattr(self._owner._state.theme, self.field_key)
        self._field.value        = val.upper().lstrip("#")
        self._field.border_color = None
        self._preview.bgcolor    = hex_to_flet(val)

    def relabel(self, s) -> None:
        """Обновить текст метки после смены языка."""
        self.label.value = getattr(s, self.label_key, self.label_key)
        self.label.update()
