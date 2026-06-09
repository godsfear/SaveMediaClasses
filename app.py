import asyncio
import time
import flet as ft

from app_logging import get_logger
from config import CHECK_INTERVAL_SECONDS
from controllers import NavigationController, ThemeController, ToolsController, WindowController
from events import (
    ToolsCheckedEvent, ToolsRestoredEvent,
    SettingsChangedEvent, LanguageChangedEvent, ThemeChangedEvent,
)
from screens.history_screen import HistoryScreen
from screens.main_screen import MainScreen
from screens.settings_screen import SettingsScreen
from services import Services


_SESSION_CLOSED_MARKERS = ("session", "disconnect", "closed", "connection reset", "pipe")

def _is_session_closed(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _SESSION_CLOSED_MARKERS)


class SaveMediaApp:

    async def main(self, page: ft.Page) -> None:
        log = get_logger("app")

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
            except Exception as exc:
                if _is_session_closed(exc):
                    log.debug("page.update skipped: session closed (%s)", exc)
                else:
                    log.exception("Failed to page.update")

        # ── DI ────────────────────────────────────────────────────────────────
        svc = Services.create(safe_update, page.run_task)

        # ── Экраны ────────────────────────────────────────────────────────────
        main_screen     = MainScreen(page, svc)
        settings_screen = SettingsScreen(page, svc)
        history_screen  = HistoryScreen(page, svc)

        main_screen.sync_from_state()
        settings_screen.sync_from_state()
        settings_screen.refresh_theme_fields()

        # ── Сохранение: единый обработчик SettingsChangedEvent ───────────────
        # Источники (settings/nav/window) лишь публикуют событие — оркестрация здесь.
        def persist(_=None) -> None:
            main_screen.sync_to_state()
            settings_screen.sync_to_state()
            svc.config_mgr.save(svc.state)

        # ── Контроллеры ───────────────────────────────────────────────────────
        window_ctrl = WindowController(page, svc)

        theme_ctrl = ThemeController(
            page, svc,
            screens=[main_screen, settings_screen, history_screen],
        )

        tools_ctrl = ToolsController(svc)
        settings_screen.set_tools_controller(tools_ctrl)

        nav_ctrl = NavigationController(
            page, svc,
            main_screen=main_screen,
            settings_screen=settings_screen,
            history_screen=history_screen,
            theme_ctrl=theme_ctrl,
            window_ctrl=window_ctrl,
        )

        # ── Обработчики событий приложения ───────────────────────────────────
        def _on_language_changed(_e: LanguageChangedEvent) -> None:
            settings_screen.rebuild_for_language()
            main_screen.rebuild_for_language()
            history_screen.rebuild_for_language()
            nav_ctrl.on_language_changed()
            safe_update()

        def _on_theme_changed(_e: ThemeChangedEvent) -> None:
            theme_ctrl.apply()
            safe_update()

        def _on_tools_checked(e: ToolsCheckedEvent) -> None:
            svc.state.last_check_time   = time.time()
            svc.state.last_needs_update = e.needs_update
            svc.bus.emit(SettingsChangedEvent())

        def _on_tools_restored(e: ToolsRestoredEvent) -> None:
            settings_screen.on_tools_restored(e)
            nav_ctrl.on_tools_restored_pending(e)

        svc.bus.on(SettingsChangedEvent, persist)
        svc.bus.on(LanguageChangedEvent, _on_language_changed)
        svc.bus.on(ThemeChangedEvent,    _on_theme_changed)
        svc.bus.on(ToolsCheckedEvent,    _on_tools_checked)
        svc.bus.on(ToolsRestoredEvent,   _on_tools_restored)

        # ── Инициализация окна и AppBar ───────────────────────────────────────
        window_ctrl.apply_geometry()
        page.update()

        page.appbar = ft.AppBar(
            title=ft.Text("SaveMedia [yt-dlp GUI]", size=18, weight=ft.FontWeight.W_600),
            bgcolor="#1c1c1c",
            leading=nav_ctrl._logo(),
            leading_width=44,
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
        force_check = not any(vs.current for vs in svc.state.tool_versions.values())
        if force_check or now - svc.state.last_check_time >= CHECK_INTERVAL_SECONDS:
            page.run_task(tools_ctrl.check_tools)
        else:
            mins_left = int(
                (CHECK_INTERVAL_SECONDS - (now - svc.state.last_check_time)) / 60
            )
            svc.bus.emit(ToolsRestoredEvent(
                needs_update=svc.state.last_needs_update,
                versions=svc.state.tool_versions,
                mins_until_check=mins_left,
            ))
            svc.bus.emit(ToolsCheckedEvent(needs_update=svc.state.last_needs_update))
            safe_update()
