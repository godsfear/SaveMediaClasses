"""
NavigationController — навигация между экранами и управление тулбаром.

Ответственность:
  - Переключение видимости экранов (show_main / show_settings / show_history).
  - Построение и обновление AppBar / BottomAppBar при каждом переходе.
  - Кнопки тулбара: тема, настройки, история, прокси, буфер обмена, папка, выход.
  - Статус-бар главного экрана (подписан на StatusMessageEvent).
  - Реакция на смену языка: статичные tooltip — через I18nTarget,
    состояние-зависимые тексты и заголовок AppBar — вручную.
  - Открытие диалога выбора папки загрузки, диалог «О программе».

Не знает про сохранение конфига (публикует SettingsChangedEvent в шину)
и про применение темы (делегирует ThemeController).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import flet as ft

from app_logging import get_logger
from config import hex_to_flet, severity_color
from controllers.i18n_target import I18nTarget
from events import (
    DownloadPathChangedEvent, SettingsChangedEvent, StatusMessageEvent, ThemeChangedEvent,
)
from i18n import Locale

if TYPE_CHECKING:
    from controllers.theme_controller import ThemeController
    from controllers.window_controller import WindowController
    from screens.history_screen import HistoryScreen
    from screens.main_screen import MainScreen
    from screens.settings_screen import SettingsScreen
    from services import Services


class NavigationController(I18nTarget):

    def __init__(
        self,
        page: ft.Page,
        svc: "Services",
        main_screen: "MainScreen",
        settings_screen: "SettingsScreen",
        history_screen: "HistoryScreen",
        theme_ctrl: "ThemeController",
        window_ctrl: "WindowController",
    ) -> None:
        super().__init__()
        self._page            = page
        self._svc             = svc
        self._main            = main_screen
        self._settings        = settings_screen
        self._history         = history_screen
        self._theme_ctrl      = theme_ctrl
        self._window_ctrl     = window_ctrl
        self._log             = get_logger("app")

        # Логотип тулбара/About: в flet build ft.Image по абсолютному пути с диска
        # не отображается (flet отдаёт картинки только из assets/URL/base64).
        # Встраиваем PNG как data-URI в src — работает и в pack, и в build.
        self._icon_src = self._load_icon_src()

        self._folder_picker = ft.FilePicker()

        s = Locale.load(svc.state.language)
        self._folder_picker_title: str = s.folder_select_text

        # ── Виджеты тулбара (созданы здесь, назначены снаружи через toolbar_buttons) ──
        fg = self._appbar_fg()
        self.theme_btn    = ft.IconButton(icon=self._theme_icon(),                    icon_color=fg, tooltip=s.theme_mode_tooltip)
        self.history_btn  = ft.IconButton(icon=ft.Icons.HISTORY_ROUNDED,              icon_color=fg, tooltip=s.nav_history)
        self.folder_btn   = ft.IconButton(icon=ft.Icons.FOLDER_OPEN_ROUNDED,          icon_color=fg, tooltip=s.btn_folder)
        self.proxy_btn    = ft.IconButton(icon=ft.Icons.SHIELD_OUTLINED,              icon_color=fg, tooltip=s.proxy_tooltip)
        self.clipboard_btn = ft.IconButton(icon=ft.Icons.CONTENT_PASTE_OFF_ROUNDED,   icon_color=fg, tooltip=s.clipboard_off)
        self.settings_btn = ft.IconButton(icon=ft.Icons.SETTINGS_ROUNDED,             icon_color=fg, tooltip=s.appbar_settings)
        self.exit_btn     = ft.IconButton(icon=ft.Icons.POWER_SETTINGS_NEW_ROUNDED,   icon_color=hex_to_flet(self._svc.state.theme.status_error_color), tooltip=s.btn_exit)

        # Статичные tooltip — по регистрации; proxy/clipboard зависят от
        # состояния и переводятся в update_proxy_ui/update_clipboard_ui.
        self.register_i18n(self.theme_btn,    tooltip="theme_mode_tooltip")
        self.register_i18n(self.history_btn,  tooltip="nav_history")
        self.register_i18n(self.folder_btn,   tooltip="btn_folder")
        self.register_i18n(self.settings_btn, tooltip="appbar_settings")
        self.register_i18n(self.exit_btn,     tooltip="btn_exit")

        self._bind_toolbar()

        # ── BottomAppBar контейнеры ───────────────────────────────────────────
        status_bar_text = ft.Text("", size=12,
                                  color=severity_color(svc.state.theme, "ok"))
        self._status_bar_text = status_bar_text
        # severity последнего сообщения — чтобы при смене темы перекрасить
        # текст из новой палитры, не теряя его семантику.
        self._status_severity = "ok"

        self.main_status_container = ft.Container(
            content=status_bar_text, padding=ft.Padding(left=10, right=10)
        )
        self.settings_status_container = ft.Container(
            content=ft.Column(
                [settings_screen.progress_text, settings_screen.progress_bar],
                spacing=4, tight=True,
            ),
            padding=ft.Padding(left=10, right=10),
        )

        # Нав владеет статус-баром, поэтому сам слушает сообщения для него.
        self._svc.bus.on(StatusMessageEvent, self._on_status_message)

    def _on_status_message(self, e: StatusMessageEvent) -> None:
        self._status_severity       = e.severity
        self._status_bar_text.value = e.message
        self._status_bar_text.color = severity_color(self._svc.state.theme, e.severity)
        self._svc.safe_update()

    # ── Публичный API ─────────────────────────────────────────────────────────

    @property
    def status_bar_text(self) -> ft.Text:
        return self._status_bar_text

    # ── Тема AppBar ───────────────────────────────────────────────────────────

    def _appbar_fg(self) -> str:
        """Цвет иконок/заголовка поверх шапки — основной текст активной палитры
        (палитра выбирается режимом, поэтому контраст к шапке сохраняется)."""
        return hex_to_flet(self._svc.state.theme.text_color)

    def _theme_icon(self) -> str:
        """Иконка переключателя: показываем целевой режим."""
        return (ft.Icons.LIGHT_MODE_ROUNDED
                if self._svc.state.theme_mode == "dark"
                else ft.Icons.DARK_MODE_ROUNDED)

    def apply_appbar_theme(self) -> None:
        """Привести иконки/заголовок текущей шапки в соответствие с режимом."""
        fg = self._appbar_fg()
        self.theme_btn.icon = self._theme_icon()
        for btn in (self.theme_btn, self.settings_btn, self.history_btn, self.folder_btn):
            btn.icon_color = fg
        # Кнопка выхода — статусный цвет «ошибка» из активной палитры.
        self.exit_btn.icon_color = hex_to_flet(self._svc.state.theme.status_error_color)
        # Статус-бар: последнее сообщение в цвет его severity из новой палитры.
        self._status_bar_text.color = severity_color(
            self._svc.state.theme, self._status_severity)
        self.update_proxy_ui()
        self.update_clipboard_ui()
        ab = self._page.appbar
        if ab is not None:
            if getattr(ab, "title", None) is not None:
                ab.title.color = fg
            if isinstance(getattr(ab, "leading", None), ft.IconButton):
                ab.leading.icon_color = fg

    def _toggle_theme_mode(self, _=None) -> None:
        st = self._svc.state
        st.theme_mode = "light" if st.theme_mode == "dark" else "dark"
        self._svc.bus.emit(ThemeChangedEvent())
        self.apply_appbar_theme()
        self._svc.bus.emit(SettingsChangedEvent())
        self._svc.safe_update()

    def update_proxy_ui(self) -> None:
        """Обновить иконку и tooltip кнопки прокси по текущему state."""
        s = Locale.load(self._svc.state.language)
        if self._svc.state.proxy_enabled:
            self.proxy_btn.icon       = ft.Icons.SHIELD_ROUNDED
            self.proxy_btn.icon_color = severity_color(self._svc.state.theme, "ok")
            self.proxy_btn.tooltip    = s.proxy_on
        else:
            self.proxy_btn.icon       = ft.Icons.SHIELD_OUTLINED
            self.proxy_btn.icon_color = self._appbar_fg()
            self.proxy_btn.tooltip    = s.proxy_off

    def update_clipboard_ui(self) -> None:
        """Обновить иконку и tooltip кнопки слежения за буфером по state."""
        s = Locale.load(self._svc.state.language)
        if self._svc.state.clipboard_watch:
            self.clipboard_btn.icon       = ft.Icons.CONTENT_PASTE_ROUNDED
            self.clipboard_btn.icon_color = severity_color(self._svc.state.theme, "ok")
            self.clipboard_btn.tooltip    = s.clipboard_on
        else:
            self.clipboard_btn.icon       = ft.Icons.CONTENT_PASTE_OFF_ROUNDED
            self.clipboard_btn.icon_color = self._appbar_fg()
            self.clipboard_btn.tooltip    = s.clipboard_off

    def _toggle_clipboard(self, _) -> None:
        """Тумблер слежения за буфером: state + персист; сам опрос ведёт
        ClipboardController, перечитывающий флаг на каждом цикле."""
        self._svc.state.clipboard_watch = not self._svc.state.clipboard_watch
        self.update_clipboard_ui()
        self._svc.bus.emit(SettingsChangedEvent())
        self._svc.safe_update()

    def on_language_changed(self) -> None:
        """Перестроить тексты тулбара и AppBar после смены языка: статичные
        tooltip — по регистрации, состояние-зависимые — свои методы."""
        s = Locale.load(self._svc.state.language)
        self.apply_language(s)
        self._folder_picker_title = s.folder_select_text
        self.update_proxy_ui()
        self.update_clipboard_ui()
        self._refresh_appbar_title(s)

    # ── Сборка AppBar (единая фабрика) ────────────────────────────────────────

    def _make_appbar(self, title: str, *, root: bool) -> ft.AppBar:
        """Единая сборка AppBar — устраняет дублирование между экранами.

        root=True  — корневой экран: лого + полный тулбар.
        root=False — вложенный экран: кнопка «назад» + переключатель темы.
        Цвета иконок/заголовка приводит к режиму последующий apply_appbar_theme().
        """
        if root:
            leading       = self._logo()
            leading_width = 44
            actions       = [
                self.theme_btn, self.settings_btn, self.history_btn,
                self.proxy_btn, self.clipboard_btn, self.folder_btn, self.exit_btn,
            ]
        else:
            leading = ft.IconButton(
                icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED, icon_color=self._appbar_fg(),
                icon_size=16, on_click=self.show_main,
            )
            leading_width = None
            actions       = [self.theme_btn]

        return ft.AppBar(
            title=ft.Text(title, size=18, weight=ft.FontWeight.W_600),
            bgcolor=hex_to_flet(self._svc.state.theme.appbar_color),
            leading=leading,
            leading_width=leading_width,
            actions=actions,
        )

    def build_initial_appbar(self) -> ft.AppBar:
        """Стартовая панель (корневой экран) с брендовым заголовком — для app.py."""
        return self._make_appbar("SaveMedia [GUI]", root=True)

    # ── Навигация ─────────────────────────────────────────────────────────────

    def show_main(self, _=None) -> None:
        self._svc.bus.emit(SettingsChangedEvent())
        self._main.layout.visible     = True
        self._settings.layout.visible = False
        self._history.layout.visible  = False
        s = Locale.load(self._svc.state.language)
        self._page.appbar = self._make_appbar(s.appbar_main, root=True)
        self._page.bottom_appbar.content = self.main_status_container
        self.apply_appbar_theme()
        self._svc.safe_update()

    def show_settings(self, _=None) -> None:
        self._main.layout.visible     = False
        self._history.layout.visible  = False
        self._settings.layout.visible = True
        self._settings.reapply_restored()
        s = Locale.load(self._svc.state.language)
        self._page.appbar = self._make_appbar(s.appbar_settings, root=False)
        self._page.bottom_appbar.content = self.settings_status_container
        self.apply_appbar_theme()
        self._svc.safe_update()

    def show_history(self, _=None) -> None:
        self._main.layout.visible     = False
        self._settings.layout.visible = False
        self._history.layout.visible  = True
        self._history.refresh()
        s = Locale.load(self._svc.state.language)
        self._page.appbar = self._make_appbar(s.appbar_history, root=False)
        self._page.bottom_appbar.content = ft.Container(height=0)
        self.apply_appbar_theme()
        self._svc.safe_update()

    # ── Приватное ─────────────────────────────────────────────────────────────

    def _load_icon_src(self) -> "str | None":
        """Логотип как data-URI для ft.Image(src=...). Единый источник — paths.icon."""
        try:
            import base64
            b64 = base64.b64encode(self._svc.paths.icon.read_bytes()).decode("ascii")
            return "data:image/png;base64," + b64
        except Exception:
            self._log.debug("logo icon not found: %s", self._svc.paths.icon)
            return None

    def _logo(self) -> ft.Container:
        img = (
            ft.Image(src=self._icon_src, width=28, height=28, fit="contain")
            if self._icon_src else
            ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, size=28, color=self._appbar_fg())
        )
        return ft.Container(
            content=img,
            padding=ft.Padding(left=8, top=0, right=0, bottom=0),
            on_click=self._show_about,
            tooltip="About",
        )

    def _app_version(self) -> str:
        try:
            from importlib.metadata import version
            return version("savemediaclasses")
        except Exception:
            pass
        try:
            import tomllib
            with open(self._svc.paths.pyproject, "rb") as f:
                return tomllib.load(f)["project"]["version"]
        except Exception:
            return ""

    def _show_about(self, _) -> None:
        t         = self._svc.state.theme
        muted_c   = hex_to_flet(t.text_muted_color)
        secondary = hex_to_flet(t.text_secondary_color)
        features = [
            "Thousands of sites — YouTube, VK, Rutube, Telegram and more",
            "Video, audio, playlists, subtitles",
            "Auto-update for yt-dlp and ffmpeg",
            "Proxy, cookies, custom arguments",
            "Download history · Thumbnail previews",
            "Localization: RU / EN",
        ]
        dlg = ft.AlertDialog(
            modal=False,
            bgcolor=hex_to_flet(t.card_color),
            title=ft.Row(
                [
                    ft.Image(src=self._icon_src, width=32, height=32, fit="contain")
                    if self._icon_src else ft.Container(width=0),
                    ft.Text("SaveMedia", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        f"v{ver}" if (ver := self._app_version()) else "",
                        size=12, color=muted_c,
                    ),
                ],
                spacing=10,
            ),
            content=ft.Column(
                [
                    ft.Text(
                        "Graphical interface for yt-dlp + ffmpeg",
                        size=13, color=secondary,
                    ),
                    ft.Divider(height=10),
                    *[ft.Text(f"• {f}", size=12) for f in features],
                    ft.Divider(height=10),
                    ft.TextButton(
                        "github.com/godsfear/SaveMediaClasses",
                        url="https://github.com/godsfear/SaveMediaClasses",
                    ),
                ],
                tight=True,
                spacing=5,
                width=360,
            ),
            actions=[
                ft.TextButton("OK", on_click=lambda e: self._close_dlg(dlg)),
            ],
        )
        self._page.show_dialog(dlg)

    def _close_dlg(self, dlg: ft.AlertDialog) -> None:
        self._page.pop_dialog()

    def _bind_toolbar(self) -> None:
        self.theme_btn.on_click     = self._toggle_theme_mode
        self.folder_btn.on_click    = self._open_folder_picker
        self.proxy_btn.on_click     = self._toggle_proxy
        self.clipboard_btn.on_click = self._toggle_clipboard
        self.settings_btn.on_click = self.show_settings
        self.history_btn.on_click  = self.show_history
        self.exit_btn.on_click     = self._window_ctrl.force_exit

    async def _open_folder_picker(self, _) -> None:
        path = await self._folder_picker.get_directory_path(
            dialog_title=self._folder_picker_title
        )
        if path:
            # Контроллер пишет только в state и шину; метку перевыводит сам
            # MainScreen по DownloadPathChangedEvent.
            self._svc.state.download_path = str(path)
            try:
                os.makedirs(self._svc.state.download_path, exist_ok=True)
            except Exception:
                self._log.exception(
                    "Failed to create selected download directory: %s",
                    self._svc.state.download_path,
                )
            self._svc.bus.emit(DownloadPathChangedEvent())
            self._svc.bus.emit(SettingsChangedEvent())
            self._svc.safe_update()

    def _toggle_proxy(self, _) -> None:
        self._svc.state.proxy_enabled = not self._svc.state.proxy_enabled
        self.update_proxy_ui()
        self._svc.bus.emit(SettingsChangedEvent())
        self._svc.safe_update()

    def _refresh_appbar_title(self, s) -> None:
        if not self._page.appbar:
            return
        if self._history.layout.visible:
            self._page.appbar.title.value = s.appbar_history
        elif self._settings.layout.visible:
            self._page.appbar.title.value = s.appbar_settings
        else:
            self._page.appbar.title.value = s.appbar_main
