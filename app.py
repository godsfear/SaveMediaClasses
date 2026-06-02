import asyncio
import time

import flet as ft

from app_logging import get_logger
from config import CHECK_INTERVAL_HOURS
from controllers import NavigationController, ThemeController, ToolsController, WindowController
from events import ToolsCheckedEvent, ToolsRestoredEvent, ToolsStatusMessageEvent
from screens.history_screen import HistoryScreen
from screens.main_screen import MainScreen
from screens.settings_screen import SettingsScreen
from services import Services
import os


class SaveMediaApp:

    async def main(self, page: ft.Page) -> None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log      = get_logger("app")

        # ── Тема страницы ─────────────────────────────────────────────────────
        page.theme_mode = ft.ThemeMode.DARK
        page.theme      = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
        page.title      = "SaveMedia"
        page.padding    = 15
        page.safe_area  = True

        # ── safe_update ───────────────────────────────────────────────────────
        def safe_update():
            try:
                page.update()
            except Exception:
                log.exception("Failed to page.update")

        # ── DI ────────────────────────────────────────────────────────────────
        svc = Services.create(base_dir, safe_update, page.run_task)

        # ── Экраны ────────────────────────────────────────────────────────────
        main_screen     = MainScreen(page, svc)
        settings_screen = SettingsScreen(page, svc)
        history_screen  = HistoryScreen(page, svc)

        main_screen.sync_from_state()
        settings_screen.sync_from_state()
        settings_screen.refresh_theme_fields()

        # ── Сохранение (экраны → state → диск) ───────────────────────────────
        def save_config():
            main_screen.sync_to_state()
            settings_screen.sync_to_state()
            svc.config_mgr.save(svc.state)

        # ── Контроллеры ───────────────────────────────────────────────────────
        window_ctrl = WindowController(page, svc, on_save=save_config)

        theme_ctrl = ThemeController(
            page, svc,
            screens=[main_screen, settings_screen, history_screen],
        )

        tools_ctrl = ToolsController(svc)
        settings_screen.bind_tools_controller(tools_ctrl)

        nav_ctrl = NavigationController(
            page, svc,
            main_screen=main_screen,
            settings_screen=settings_screen,
            history_screen=history_screen,
            theme_ctrl=theme_ctrl,
            window_ctrl=window_ctrl,
            on_save=save_config,
        )

        # ── Подписки Settings → контроллеры ──────────────────────────────────
        def _on_lang_changed():
            settings_screen.rebuild_for_language()
            main_screen.rebuild_for_language()
            history_screen.rebuild_for_language()
            nav_ctrl.on_language_changed()
            safe_update()

        settings_screen.set_on_language_changed(_on_lang_changed)
        settings_screen.set_on_theme_changed(theme_ctrl.apply)
        settings_screen.set_on_settings_changed(save_config)

        # ── Подписки на шину ──────────────────────────────────────────────────
        def _on_tools_checked(e: ToolsCheckedEvent) -> None:
            svc.state.last_check_time   = time.time()
            svc.state.last_needs_update = e.needs_update
            save_config()

        def _on_status_message(e: ToolsStatusMessageEvent) -> None:
            nav_ctrl.status_bar_text.value = e.message
            nav_ctrl.status_bar_text.color = e.color
            safe_update()

        def _on_tools_restored(e: ToolsRestoredEvent) -> None:
            settings_screen.on_tools_restored(e)
            nav_ctrl.on_tools_restored_pending(e)

        svc.bus.on(ToolsCheckedEvent,       _on_tools_checked)
        svc.bus.on(ToolsStatusMessageEvent, _on_status_message)
        svc.bus.on(ToolsRestoredEvent,      _on_tools_restored)

        # ── Инициализация окна и AppBar ───────────────────────────────────────
        window_ctrl.apply_geometry()
        page.update()

        page.appbar = ft.AppBar(
            title=ft.Text("SaveMedia [yt-dlp GUI]", size=18, weight=ft.FontWeight.W_600),
            bgcolor="#1c1c1c",
            actions=[
                nav_ctrl.settings_btn, nav_ctrl.history_btn,
                nav_ctrl.proxy_btn, nav_ctrl.folder_btn, nav_ctrl.exit_btn,
            ],
        )
        page.bottom_appbar = ft.BottomAppBar(
            content=nav_ctrl.main_status_container, bgcolor="#141414"
        )

        window_ctrl.register_close_handler()

        # ── Финальная инициализация ───────────────────────────────────────────
        nav_ctrl.update_proxy_ui()
        nav_ctrl.update_cookies_ui()
        theme_ctrl.apply()
        page.add(main_screen.layout, settings_screen.layout, history_screen.layout)

        window_ctrl.reveal()
        page.update()

        await asyncio.sleep(0.1)

        # ── Фоновая проверка версий ───────────────────────────────────────────
        now         = time.time()
        force_check = not svc.state.tool_versions
        if force_check or now - svc.state.last_check_time >= CHECK_INTERVAL_HOURS * 3600:
            page.run_task(settings_screen.check_tools)
        else:
            mins_left = int(
                (CHECK_INTERVAL_HOURS * 3600 - (now - svc.state.last_check_time)) / 60
            )
            svc.bus.emit(ToolsRestoredEvent(
                needs_update=svc.state.last_needs_update,
                tool_versions=svc.state.tool_versions,
                mins_until_check=mins_left,
            ))
            svc.bus.emit(ToolsCheckedEvent(needs_update=svc.state.last_needs_update))
            safe_update()
