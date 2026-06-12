"""
controllers/i18n_target.py — миксин для смены языка без ручного перечисления виджетов.

Симметричен ThemeTarget (см. theme_target.py), но для текстов: виджет
регистрируется рядом с созданием с парами «атрибут = i18n-ключ», а
apply_language() единым циклом переписывает все тексты из новой локали:

    self.url_input = self.register_accents(ft.TextField(label=s.url_label, ...))
    self.register_i18n(self.url_input, label="url_label", hint_text="url_hint")

Динамические тексты (s.fmt(...), пункты дропдаунов, состояние-зависимые
подписи) в миксин НЕ регистрируются — их перестраивает сам экран в своём
rebuild_for_language() после вызова apply_language().

Отдельные widget.update() при смене языка не нужны: оркестратор
(_on_language_changed в app.py) завершает обработку общим safe_update() —
страница дорисовывает все изменения разом.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from i18n import Strings


class I18nTarget:
    """Миксин: декларативная привязка текстовых атрибутов виджетов к ключам локали."""

    def __init__(self) -> None:
        super().__init__()   # кооперативный init — для связки с ThemeTarget в экранах
        self._i18n_bindings: list[tuple[object, str, str]] = []

    def register_i18n(self, widget, **attr_keys: str):
        """Привязать атрибуты виджета к ключам локали: register_i18n(w, tooltip="btn_exit").
        Возвращает widget — регистрацию можно встроить в выражение создания."""
        for attr, key in attr_keys.items():
            self._i18n_bindings.append((widget, attr, key))
        return widget

    def apply_language(self, s: "Strings") -> None:
        """Переписать все зарегистрированные тексты из новой локали."""
        for widget, attr, key in self._i18n_bindings:
            setattr(widget, attr, getattr(s, key, key))
