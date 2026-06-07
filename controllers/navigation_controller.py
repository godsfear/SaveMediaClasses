"""
NavigationController — навигация между экранами и управление тулбаром.

Ответственность:
  - Переключение видимости экранов (show_main / show_settings / show_history).
  - Построение и обновление AppBar / BottomAppBar при каждом переходе.
  - Кнопки тулбара: прокси, папка, история, настройки, выход.
  - Реакция на смену языка: обновить тексты tooltip, заголовок AppBar.
  - Открытие диалога выбора папки загрузки.

Не знает про сохранение конфига (делегирует on_save)
и про применение темы (делегирует ThemeController).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Callable

import flet as ft

from app_logging import get_logger
from config import hex_to_flet
from i18l import Locale
from paths import AppPaths

if TYPE_CHECKING:
    from controllers.theme_controller import ThemeController
    from controllers.window_controller import WindowController
    from screens.history_screen import HistoryScreen
    from screens.main_screen import MainScreen
    from screens.settings_screen import SettingsScreen
    from services import Services


class NavigationController:

    def __init__(
        self,
        page: ft.Page,
        svc: "Services",
        main_screen: "MainScreen",
        settings_screen: "SettingsScreen",
        history_screen: "HistoryScreen",
        theme_ctrl: "ThemeController",
        window_ctrl: "WindowController",
        on_save: Callable[[], None],
    ) -> None:
        self._page            = page
        self._svc             = svc
        self._main            = main_screen
        self._settings        = settings_screen
        self._history         = history_screen
        self._theme_ctrl      = theme_ctrl
        self._window_ctrl     = window_ctrl
        self._on_save         = on_save
        self._log             = get_logger("app")

        self._pending_restored: list = []

        self._folder_picker = ft.FilePicker()

        s = Locale.load(svc.state.language)
        self._folder_picker_title: str = s.folder_select_text

        # ── Виджеты тулбара (созданы здесь, назначены снаружи через toolbar_buttons) ──
        self.history_btn  = ft.IconButton(icon=ft.Icons.HISTORY_ROUNDED,              icon_color=ft.Colors.WHITE, tooltip=s.nav_history)
        self.folder_btn   = ft.IconButton(icon=ft.Icons.FOLDER_OPEN_ROUNDED,          icon_color=ft.Colors.WHITE, tooltip=s.btn_folder)
        self.proxy_btn    = ft.IconButton(icon=ft.Icons.SHIELD_OUTLINED,              icon_color=ft.Colors.WHITE, tooltip=s.proxy_tooltip)
        self.settings_btn = ft.IconButton(icon=ft.Icons.SETTINGS_ROUNDED,             icon_color=ft.Colors.WHITE, tooltip=s.appbar_settings)
        self.exit_btn     = ft.IconButton(icon=ft.Icons.POWER_SETTINGS_NEW_ROUNDED,   icon_color=ft.Colors.RED_400, tooltip=s.btn_exit)

        self._bind_toolbar()

        # ── BottomAppBar контейнеры ───────────────────────────────────────────
        status_bar_text = ft.Text("", size=12, color=ft.Colors.GREEN_400)
        self._status_bar_text = status_bar_text

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

    # ── Публичный API ─────────────────────────────────────────────────────────

    @property
    def status_bar_text(self) -> ft.Text:
        return self._status_bar_text

    def update_proxy_ui(self) -> None:
        """Обновить иконку и tooltip кнопки прокси по текущему state."""
        s = Locale.load(self._svc.state.language)
        if self._svc.state.proxy_enabled:
            self.proxy_btn.icon       = ft.Icons.SHIELD_ROUNDED
            self.proxy_btn.icon_color = ft.Colors.GREEN_400
            self.proxy_btn.tooltip    = s.proxy_on
        else:
            self.proxy_btn.icon       = ft.Icons.SHIELD_OUTLINED
            self.proxy_btn.icon_color = ft.Colors.WHITE
            self.proxy_btn.tooltip    = s.proxy_off

    def update_cookies_ui(self) -> None:
        self._settings.update_cookies_ui(self._main.cookies_enabled_switch)

    def on_tools_restored_pending(self, e) -> None:
        """Сохранить последнее ToolsRestoredEvent — показать при входе в настройки."""
        self._pending_restored.clear()
        self._pending_restored.append(e)

    def on_language_changed(self) -> None:
        """Перестроить все тексты тулбара и AppBar после смены языка."""
        s = Locale.load(self._svc.state.language)
        self._folder_picker_title  = s.folder_select_text
        self.settings_btn.tooltip  = s.appbar_settings
        self.history_btn.tooltip   = s.nav_history
        self.folder_btn.tooltip    = s.btn_folder
        self.exit_btn.tooltip      = s.btn_exit
        self.update_proxy_ui()
        self._refresh_appbar_title(s)

    # ── Навигация ─────────────────────────────────────────────────────────────

    def show_main(self, _=None) -> None:
        self._on_save()
        self.update_cookies_ui()
        self._main.layout.visible     = True
        self._settings.layout.visible = False
        self._history.layout.visible  = False
        s = Locale.load(self._svc.state.language)
        self._page.appbar = ft.AppBar(
            title=ft.Text(s.appbar_main, size=18, weight=ft.FontWeight.W_600),
            bgcolor=hex_to_flet(self._svc.state.theme.appbar_color),
            leading=self._logo(),
            leading_width=44,
            actions=[
                self.settings_btn, self.history_btn,
                self.proxy_btn, self.folder_btn, self.exit_btn,
            ],
        )
        self._page.bottom_appbar.content = self.main_status_container
        self._svc.safe_update()

    def show_settings(self, _=None) -> None:
        self._main.layout.visible     = False
        self._history.layout.visible  = False
        self._settings.layout.visible = True
        if self._pending_restored:
            self._settings.on_tools_restored(self._pending_restored[-1])
        s = Locale.load(self._svc.state.language)
        self._page.appbar = ft.AppBar(
            title=ft.Text(s.appbar_settings, size=18, weight=ft.FontWeight.W_600),
            bgcolor=hex_to_flet(self._svc.state.theme.appbar_color),
            leading=ft.IconButton(
                icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED, icon_color=ft.Colors.WHITE,
                icon_size=16, on_click=self.show_main,
            ),
        )
        self._page.bottom_appbar.content = self.settings_status_container
        self._svc.safe_update()

    def show_history(self, _=None) -> None:
        self._main.layout.visible     = False
        self._settings.layout.visible = False
        self._history.layout.visible  = True
        self._history.refresh()
        s = Locale.load(self._svc.state.language)
        self._page.appbar = ft.AppBar(
            title=ft.Text(s.appbar_history, size=18, weight=ft.FontWeight.W_600),
            bgcolor=hex_to_flet(self._svc.state.theme.appbar_color),
            leading=ft.IconButton(
                icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED, icon_color=ft.Colors.WHITE,
                icon_size=16, on_click=self.show_main,
            ),
        )
        self._page.bottom_appbar.content = ft.Container(height=0)
        self._svc.safe_update()

    # ── Приватное ─────────────────────────────────────────────────────────────

    def _logo(self) -> ft.Container:
        return ft.Container(
            content=ft.Image(
                src=str(AppPaths.app_dir() / "SaveMedia.png"),
                width=28,
                height=28,
                fit="contain",
            ),
            padding=ft.Padding(left=8, top=0, right=0, bottom=0),
            on_click=self._show_about,
            tooltip="About",
        )

    @staticmethod
    def _app_version() -> str:
        try:
            from importlib.metadata import version
            return version("savemediaclasses")
        except Exception:
            pass
        try:
            import tomllib
            with open(AppPaths.app_dir() / "pyproject.toml", "rb") as f:
                return tomllib.load(f)["project"]["version"]
        except Exception:
            return ""

    def _show_about(self, _) -> None:
        features = [
            "Тысячи сайтов — YouTube, VK, Rutube, Telegram и др.",
            "Видео, аудио, плейлисты, субтитры",
            "Автообновление yt-dlp и ffmpeg",
            "Прокси, cookies, кастомные аргументы",
            "История загрузок · Thumbnail-превью",
            "Локализация: RU / EN",
        ]
        dlg = ft.AlertDialog(
            modal=False,
            title=ft.Row(
                [
                    ft.Image(
                        src=str(AppPaths.app_dir() / "SaveMedia.png"),
                        width=32, height=32, fit="contain",
                    ),
                    ft.Text("SaveMedia", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        f"v{ver}" if (ver := self._app_version()) else "",
                        size=12, color=ft.Colors.GREY_500,
                    ),
                ],
                spacing=10,
            ),
            content=ft.Column(
                [
                    ft.Text(
                        "Графический интерфейс для yt-dlp + ffmpeg",
                        size=13, color=ft.Colors.GREY_400,
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
        self._page.overlay.append(dlg)
        dlg.open = True
        self._page.update()

    def _close_dlg(self, dlg: ft.AlertDialog) -> None:
        dlg.open = False
        self._page.update()
        self._page.overlay.remove(dlg)

    def _bind_toolbar(self) -> None:
        self.folder_btn.on_click   = self._open_folder_picker
        self.proxy_btn.on_click    = self._toggle_proxy
        self.settings_btn.on_click = self.show_settings
        self.history_btn.on_click  = self.show_history
        self.exit_btn.on_click     = self._window_ctrl.force_exit

    async def _open_folder_picker(self, _) -> None:
        path = await self._folder_picker.get_directory_path(
            dialog_title=self._folder_picker_title
        )
        if path:
            self._svc.state.download_path        = str(path)
            self._main.folder_label.value        = str(path)
            self._main.folder_label.color        = ft.Colors.GREEN_400
            try:
                os.makedirs(self._svc.state.download_path, exist_ok=True)
            except Exception:
                self._log.exception(
                    "Failed to create selected download directory: %s",
                    self._svc.state.download_path,
                )
            self._on_save()
            self._svc.safe_update()

    def _toggle_proxy(self, _) -> None:
        self._svc.state.proxy_enabled = not self._svc.state.proxy_enabled
        self.update_proxy_ui()
        self._on_save()
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
