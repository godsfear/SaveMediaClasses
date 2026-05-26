import asyncio
import os
import time

import flet as ft

from config import DEFAULT_CONFIG, THEME_FIELDS, CHECK_INTERVAL_HOURS, hex_to_flet, safe_str
from managers.config_manager import ConfigManager
from managers.tools_manager import ToolsManager
from screens.main_screen import MainScreen
from screens.settings_screen import SettingsScreen


class SaveMediaApp:

    async def main(self, page: ft.Page) -> None:
        base_dir  = os.path.dirname(os.path.abspath(__file__))
        tools_dir = os.path.join(base_dir, "tools")
        os.makedirs(tools_dir, exist_ok=True)

        page.theme_mode = ft.ThemeMode.DARK
        page.theme      = ft.Theme(color_scheme_seed=ft.Colors.BLUE)

        def safe_update():
            try:
                page.update()
            except Exception:
                pass

        config_mgr = ConfigManager(os.path.join(base_dir, "config.json"))
        tools      = ToolsManager(base_dir, tools_dir)

        # ── Геометрия окна — читаем до создания экранов ───────────────────────
        geo = config_mgr.load_window_geometry()
        page.window.width  = geo["width"]
        page.window.height = geo["height"]
        page.window.left   = geo["left"]
        page.window.top    = geo["top"]
        page.window.icon   = "vload.png"

        if page.platform in [ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS, ft.PagePlatform.LINUX]:
            page.window.min_width     = 500
            page.window.min_height    = 550
            page.window.prevent_close = True
            page.window.visible       = False

        page.update()
        page.title     = "SaveMedia"
        page.padding   = 15
        page.safe_area = True

        # ── Загружаем состояние ───────────────────────────────────────────────
        state = config_mgr.load()

        # ── Экраны получают state — никаких колбэков для передачи данных ──────
        main_screen     = MainScreen(page, base_dir, tools_dir, safe_update, state)
        settings_screen = SettingsScreen(page, tools, safe_update, state)

        # ── Синхронизируем виджеты из state ──────────────────────────────────
        main_screen.sync_from_state()
        settings_screen.sync_from_state()
        settings_screen.refresh_theme_fields()

        # ── Сохранение ────────────────────────────────────────────────────────

        def _sync_window_to_state():
            w, h, l, t = page.window.width, page.window.height, page.window.left, page.window.top
            if w and w > 10: state.window["width"]  = int(w)
            if h and h > 10: state.window["height"] = int(h)
            if l is not None: state.window["left"]  = int(l)
            if t is not None: state.window["top"]   = int(t)

        def save_config():
            # Снимаем актуальные значения со всех виджетов перед записью
            main_screen.sync_to_state()
            settings_screen.sync_to_state()
            _sync_window_to_state()
            config_mgr.save(state)

        # ── Тема ──────────────────────────────────────────────────────────────

        all_headers = [
            main_screen.header_folder, main_screen.header_main, main_screen.header_queue,
            settings_screen.header_net, settings_screen.header_rules,
            settings_screen.header_deps, settings_screen.header_theme,
            settings_screen.header_urls,
        ]
        all_switches = [
            main_screen.audio_only_switch, main_screen.cookies_enabled_switch,
            settings_screen.clean_titles_switch,
            settings_screen.playlist_switch, settings_screen.embed_metadata_switch,
            settings_screen.save_to_source_switch,
        ]

        def apply_theme():
            t = state.theme
            accent     = hex_to_flet(t.get("accent_color",   "00B4D8"))
            switch_c   = hex_to_flet(t.get("switch_color",   "4CAF50"))
            header_c   = hex_to_flet(t.get("header_color",   "00B4D8"))
            text_c     = hex_to_flet(t.get("text_color",     "E0E0E0"))
            progress_c = hex_to_flet(t.get("progress_color", "4CAF50"))
            button_c   = hex_to_flet(t.get("button_color",   "4CAF50"))
            appbar_c   = hex_to_flet(t.get("appbar_color",   "1c1c1c"))
            card_c     = hex_to_flet(t.get("card_color",     "161616"))

            for h in all_headers:
                h.color = header_c
            for sw in all_switches:
                sw.active_color = switch_c

            main_screen.download_btn.bgcolor        = button_c
            settings_screen.update_btn.bgcolor      = button_c
            settings_screen.progress_text.color     = progress_c
            settings_screen.progress_bar.color      = progress_c

            main_screen.url_input.focused_border_color                        = accent
            settings_screen.proxy_input.focused_border_color                  = accent
            settings_screen.yt_args_input.focused_border_color                = accent
            settings_screen.cookies_browser_dropdown.focused_border_color     = accent
            settings_screen.yt_api_input.focused_border_color                 = accent
            settings_screen.yt_download_input.focused_border_color            = accent
            settings_screen.ffmpeg_version_input.focused_border_color         = accent
            settings_screen.ffmpeg_download_input.focused_border_color        = accent

            main_screen.folder_label.color = text_c

            if page.appbar:
                page.appbar.bgcolor = appbar_c

            for layout in [main_screen.layout, settings_screen.layout]:
                if hasattr(layout, "controls"):
                    for ctrl in layout.controls:
                        if isinstance(ctrl, ft.Container):
                            ctrl.bgcolor = card_c

        # ── Колбэки экранов — только смысловые ───────────────────────────────

        settings_screen.set_on_theme_changed(apply_theme)
        settings_screen.set_on_notify_main(main_screen.notify_tools_status)
        settings_screen.set_on_settings_changed(save_config)
        settings_screen.set_on_check_done(lambda: (
            setattr(state, "last_check_time",   time.time()),
            setattr(state, "last_needs_update",
                    settings_screen._tools.yt_needs_update or settings_screen._tools.ffmpeg_needs_update),
            save_config()
        ))

        main_screen._on_status = lambda msg, color: (
            setattr(status_bar_text, "value", msg),
            setattr(status_bar_text, "color", color),
            safe_update()
        )

        # ── Кнопки тулбара ────────────────────────────────────────────────────

        def update_proxy_button_ui():
            if state.proxy_enabled:
                proxy_btn.icon       = ft.Icons.SHIELD_ROUNDED
                proxy_btn.icon_color = ft.Colors.GREEN_400
                proxy_btn.tooltip    = "Прокси: ВКЛ"
            else:
                proxy_btn.icon       = ft.Icons.SHIELD_OUTLINED
                proxy_btn.icon_color = ft.Colors.WHITE
                proxy_btn.tooltip    = "Прокси: ВЫКЛ"

        def update_cookies_ui():
            settings_screen.update_cookies_ui(main_screen.cookies_enabled_switch)

        folder_btn   = ft.IconButton(icon=ft.Icons.FOLDER_OPEN_ROUNDED, icon_color=ft.Colors.WHITE, tooltip="Выбрать папку")
        proxy_btn    = ft.IconButton(icon=ft.Icons.SHIELD_OUTLINED,     icon_color=ft.Colors.WHITE, tooltip="Прокси")
        settings_btn = ft.IconButton(icon=ft.Icons.SETTINGS_ROUNDED,    icon_color=ft.Colors.WHITE, tooltip="Настройки")
        exit_btn     = ft.IconButton(icon=ft.Icons.POWER_SETTINGS_NEW_ROUNDED, icon_color=ft.Colors.RED_400, tooltip="Полный выход")

        async def force_exit_app(_):
            try:
                save_config()
            except Exception:
                pass
            page.window.prevent_close = False
            page.window.on_event      = None
            page.update()
            await page.window.destroy()

        exit_btn.on_click = force_exit_app

        # ── Навигация ─────────────────────────────────────────────────────────

        status_bar_text = ft.Text("", size=12, color=ft.Colors.GREEN_400)
        main_status_container = ft.Container(
            content=status_bar_text, padding=ft.Padding(left=10, right=10)
        )
        settings_status_container = ft.Container(
            content=ft.Column([settings_screen.progress_text, settings_screen.progress_bar],
                              spacing=4, tight=True),
            padding=ft.Padding(left=10, right=10)
        )

        def show_settings(_):
            main_screen.layout.visible     = False
            settings_screen.layout.visible = True
            page.appbar = ft.AppBar(
                title=ft.Text("Настройки конфигурации", size=18, weight=ft.FontWeight.W_600),
                bgcolor=hex_to_flet(state.theme.get("appbar_color", "1c1c1c")),
                leading=ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
                    icon_color=ft.Colors.WHITE,
                    icon_size=16,
                    on_click=show_main
                )
            )
            page.bottom_appbar.content = settings_status_container
            safe_update()

        def show_main(_):
            save_config()
            update_cookies_ui()
            main_screen.layout.visible     = True
            settings_screen.layout.visible = False
            page.appbar = ft.AppBar(
                title=ft.Text("SaveMedia [yt-dlp GUI]", size=18, weight=ft.FontWeight.W_600),
                bgcolor=hex_to_flet(state.theme.get("appbar_color", "1c1c1c")),
                actions=[settings_btn, proxy_btn, folder_btn, exit_btn]
            )
            page.bottom_appbar.content = main_status_container
            safe_update()

        async def open_folder_picker(_):
            path = await ft.FilePicker().get_directory_path(dialog_title="Выберите папку сохранения медиа")
            if path:
                state.download_path            = str(path)
                main_screen.folder_label.value = str(path)
                main_screen.folder_label.color = ft.Colors.GREEN_400
                try:
                    os.makedirs(state.download_path, exist_ok=True)
                except Exception:
                    pass
                save_config()
                safe_update()

        def toggle_proxy(_):
            state.proxy_enabled = not state.proxy_enabled
            update_proxy_button_ui()
            save_config()
            safe_update()

        folder_btn.on_click   = open_folder_picker
        proxy_btn.on_click    = toggle_proxy
        settings_btn.on_click = show_settings

        # ── Закрытие окна ─────────────────────────────────────────────────────

        async def handle_window_event(e):
            ev = str(getattr(e, "type", None) or getattr(e, "data", None)).lower()
            if "close" in ev:
                try:
                    save_config()
                except Exception:
                    pass
                page.window.prevent_close = False
                page.window.on_event      = None
                page.update()
                await page.window.destroy()

        page.window.on_event = handle_window_event

        # ── AppBar / BottomAppBar ──────────────────────────────────────────────
        page.appbar = ft.AppBar(
            title=ft.Text("SaveMedia [yt-dlp GUI]", size=18, weight=ft.FontWeight.W_600),
            bgcolor="#1c1c1c",
            actions=[settings_btn, proxy_btn, folder_btn, exit_btn]
        )
        page.bottom_appbar = ft.BottomAppBar(content=main_status_container, bgcolor="#141414")

        # ── Финальная инициализация ───────────────────────────────────────────
        update_proxy_button_ui()
        update_cookies_ui()
        apply_theme()
        page.add(main_screen.layout, settings_screen.layout)

        if page.platform in [ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS, ft.PagePlatform.LINUX]:
            page.window.visible = True
        page.update()

        await asyncio.sleep(0.1)

        # ── Фоновая проверка версий ───────────────────────────────────────────
        now = time.time()
        if now - state.last_check_time >= CHECK_INTERVAL_HOURS * 3600:
            async def _do_check():
                await settings_screen.check_tools()
            page.run_task(_do_check)
        else:
            mins_left = int((CHECK_INTERVAL_HOURS * 3600 - (now - state.last_check_time)) / 60)
            settings_screen.progress_text.value = (
                f"Версии проверены недавно — следующая проверка через {mins_left} мин"
            )
            settings_screen.progress_text.color = ft.Colors.GREY_400

            if state.last_needs_update:
                settings_screen.update_btn_text.value = "Обновить скрипты"
                settings_screen.update_btn_icon.name  = ft.Icons.DOWNLOAD_ROUNDED
                settings_screen._tools.yt_needs_update = True
                tool_msg   = "Доступны обновления"
                tool_color = ft.Colors.ORANGE_400
            else:
                settings_screen.update_btn_text.value = "Проверить версии"
                settings_screen.update_btn_icon.name  = ft.Icons.REFRESH_ROUNDED
                tool_msg   = "Актуально"
                tool_color = ft.Colors.GREEN_400

            for w, name in [
                (settings_screen.yt_status,      "yt-dlp"),
                (settings_screen.ffmpeg_status,  "ffmpeg"),
                (settings_screen.ffplay_status,  "ffplay"),
                (settings_screen.ffprobe_status, "ffprobe"),
            ]:
                w.value = f"{name}: {tool_msg}"
                w.color = tool_color

            main_screen.notify_tools_status(state.last_needs_update)
            safe_update()
