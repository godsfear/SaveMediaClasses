import asyncio
import time
import flet as ft

from app_logging import get_logger
from config import CHECK_INTERVAL_SECONDS, PERSIST_DEBOUNCE_SECONDS, hex_to_flet
from controllers import (
    ClipboardController, NavigationController, NotificationController,
    ThemeController, ToolsController, WindowController,
)
from events import (
    ToolsCheckedEvent, ToolsRestoredEvent,
    SettingsChangedEvent, LanguageChangedEvent, ThemeChangedEvent,
    ResumeDownloadEvent, AppClosingEvent,
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
        # page.theme (seed от accent_color) и theme_mode выставляет
        # theme_ctrl.apply() из state до reveal окна.
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

        # Срок хранения истории: чистим финальные записи старше лимита при старте.
        svc.db.purge_older_than(svc.state.history_keep_days)

        # ── Экраны ────────────────────────────────────────────────────────────
        main_screen     = MainScreen(page, svc)
        settings_screen = SettingsScreen(page, svc)
        history_screen  = HistoryScreen(page, svc)

        main_screen.sync_from_state()
        settings_screen.sync_from_state()
        settings_screen.refresh_theme_fields()

        # ── Сохранение: единый обработчик SettingsChangedEvent ───────────────
        # Источники (settings/nav/window) лишь публикуют событие — оркестрация здесь.
        #
        # Модель ОСОЗНАННО pull: свободно-редактируемые поля (текстовые инпуты,
        # переключатели) живут в виджетах как буфер правки и фиксируются в state
        # только в точках коммита (любой SettingsChangedEvent: навигация, выбор
        # в дропдауне, закрытие окна). Push (запись в state на каждый ввод)
        # означал бы сохранение на каждое нажатие клавиши без выгоды для
        # консистентности: между коммитами state читают только сами экраны.
        #
        # Запись на диск ДЕБАУНСИТСЯ: правка hex-цвета шлёт SettingsChangedEvent
        # на каждый символ — пишем после паузы тишины. Это безопасно: источники
        # события сами коммитят своё состояние в state ДО эмита, откладывается
        # только страховочный sync_to_state + сама запись файла. На закрытии
        # приложения — немедленный flush (AppClosingEvent приходит до destroy).
        def write_config() -> None:
            main_screen.sync_to_state()
            settings_screen.sync_to_state()
            svc.config_mgr.save(svc.state)

        pending_save: dict = {"task": None}

        async def _delayed_write() -> None:
            await asyncio.sleep(PERSIST_DEBOUNCE_SECONDS)
            write_config()

        def _cancel_pending() -> None:
            task = pending_save["task"]
            if task is not None and not task.done():
                task.cancel()

        def persist(_=None) -> None:
            _cancel_pending()
            pending_save["task"] = page.run_task(_delayed_write)

        def flush_config(_=None) -> None:
            _cancel_pending()
            write_config()

        # ── Контроллеры ───────────────────────────────────────────────────────
        window_ctrl = WindowController(page, svc)

        theme_ctrl = ThemeController(
            page, svc,
            screens=[main_screen, settings_screen, history_screen],
        )

        tools_ctrl     = ToolsController(svc, task_runner=page.run_task)
        clipboard_ctrl = ClipboardController(page, svc)
        NotificationController(page, svc)   # живёт подпиской на шину

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
            nav_ctrl.apply_appbar_theme()
            safe_update()

        def _on_tools_checked(e: ToolsCheckedEvent) -> None:
            svc.state.last_check_time   = time.time()
            svc.state.last_needs_update = e.needs_update
            svc.bus.emit(SettingsChangedEvent())

        # ToolsRestoredEvent обрабатывает сам SettingsScreen (подписан в конструкторе).
        # Возобновление из истории: загрузку запустит DownloadOrchestrator
        # (svc.downloads, подписан на ResumeDownloadEvent в Services.create),
        # карточку нарисует MainScreen (по DownloadAcceptedEvent), а здесь —
        # только переключение на главный экран.
        svc.bus.on(ResumeDownloadEvent, lambda e: nav_ctrl.show_main())
        svc.bus.on(SettingsChangedEvent, persist)
        svc.bus.on(AppClosingEvent,      flush_config)
        svc.bus.on(LanguageChangedEvent, _on_language_changed)
        svc.bus.on(ThemeChangedEvent,    _on_theme_changed)
        svc.bus.on(ToolsCheckedEvent,    _on_tools_checked)

        # ── Инициализация окна и AppBar ───────────────────────────────────────
        window_ctrl.apply_geometry()
        page.update()

        page.appbar = nav_ctrl.build_initial_appbar()
        page.bottom_appbar = ft.BottomAppBar(
            content=nav_ctrl.main_status_container,
            bgcolor=hex_to_flet(svc.state.theme.bottom_bar_color),
        )

        window_ctrl.register_close_handler()

        # ── Финальная инициализация ───────────────────────────────────────────
        nav_ctrl.update_proxy_ui()
        main_screen.update_cookies_ui()
        nav_ctrl.apply_appbar_theme()
        theme_ctrl.apply()
        page.add(main_screen.layout, settings_screen.layout, history_screen.layout)
        page.update()

        # Слежение за буфером: цикл живёт всегда, активен только при включённом
        # тумблере (state.clipboard_watch); останавливается по AppClosingEvent.
        page.run_task(clipboard_ctrl.run)

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

        # Окно стартует скрытым (hide_window_on_start в pyproject) — показываем его
        # ОДИН раз в самом конце main(), когда UI готов. reveal() из середины main()
        # в flet build (нативный flutter) не закрепляется, поэтому только здесь.
        await asyncio.sleep(0.3)
        window_ctrl.reveal()
        page.update()
