import asyncio
import os
import threading
from typing import Any, Dict

import flet as ft
from PIL import Image, ImageDraw
import pystray

from config import DEFAULT_CONFIG, THEME_FIELDS, hex_to_flet, safe_str, safe_int, get_fallback_bool
from managers.config_manager import ConfigManager
from managers.tools_manager import ToolsManager
from managers.downloader import Downloader
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

        config_mgr  = ConfigManager(os.path.join(base_dir, "config.json"))
        tools       = ToolsManager(base_dir, tools_dir)
        downloader  = Downloader(base_dir, tools_dir)

        current_theme: Dict[str, str] = dict(DEFAULT_CONFIG["theme"])

        # ── Геометрия окна (оригинальная логика) ──────────────────────────────
        geo = config_mgr.load_window_geometry()
        current_geometry = dict(geo)

        page.window.width  = geo["width"]
        page.window.height = geo["height"]
        page.window.left   = geo["left"]
        page.window.top    = geo["top"]
        page.window.icon   = "SaveMedia.png"

        if page.platform in [ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS, ft.PagePlatform.LINUX]:
            page.window.min_width     = 500
            page.window.min_height    = 550
            page.window.prevent_close = True
            page.window.visible       = False

        page.update()

        page.title     = "SaveMedia"
        page.padding   = 15
        page.safe_area = True

        download_path = ""
        proxy_enabled = False

        # ── Экраны ────────────────────────────────────────────────────────────
        main_screen     = MainScreen(page, downloader, safe_update, current_theme)
        settings_screen = SettingsScreen(page, tools, safe_update, current_theme, lambda: save_config())

        # Все переключатели для apply_theme
        all_headers = [
            main_screen.header_main, main_screen.header_log,
            settings_screen.header_net, settings_screen.header_rules,
            settings_screen.header_deps, settings_screen.header_theme,
            settings_screen.header_urls,
        ]
        all_switches = [
            main_screen.audio_only_switch, main_screen.cookies_enabled_switch,
            settings_screen.minimize_to_tray_switch, settings_screen.clean_titles_switch,
            settings_screen.playlist_switch, settings_screen.embed_metadata_switch,
            settings_screen.save_to_source_switch,
        ]

        # ── Применение темы (оригинальная логика) ────────────────────────────
        def apply_theme():
            accent     = hex_to_flet(current_theme.get("accent_color",   "00B4D8"))
            switch_c   = hex_to_flet(current_theme.get("switch_color",   "4CAF50"))
            header_c   = hex_to_flet(current_theme.get("header_color",   "00B4D8"))
            text_c     = hex_to_flet(current_theme.get("text_color",     "E0E0E0"))
            progress_c = hex_to_flet(current_theme.get("progress_color", "4CAF50"))
            button_c   = hex_to_flet(current_theme.get("button_color",   "4CAF50"))
            appbar_c   = hex_to_flet(current_theme.get("appbar_color",   "1c1c1c"))
            card_c     = hex_to_flet(current_theme.get("card_color",     "161616"))

            for h in all_headers:
                h.color = header_c
            for sw in all_switches:
                sw.active_color = switch_c

            main_screen.download_btn.bgcolor        = button_c
            main_screen.main_progress_text.color    = progress_c
            main_screen.main_progress_bar.color     = progress_c
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

            if hasattr(main_screen.layout, "controls") and main_screen.layout.controls:
                main_screen.layout.controls[0].bgcolor = card_c
            if hasattr(settings_screen.layout, "controls") and settings_screen.layout.controls:
                for ctrl in settings_screen.layout.controls:
                    if isinstance(ctrl, ft.Container):
                        ctrl.bgcolor = card_c

        settings_screen.set_apply_theme_callback(apply_theme)

        # ── Сохранение конфига (оригинальная логика) ─────────────────────────
        def synchronize_geometry_cache():
            w, h, l, t = page.window.width, page.window.height, page.window.left, page.window.top
            if w is not None and w > 10: current_geometry["width"]  = int(w)
            if h is not None and h > 10: current_geometry["height"] = int(h)
            if l is not None: current_geometry["left"] = int(l)
            if t is not None: current_geometry["top"]  = int(t)

        def save_config():
            nonlocal download_path
            synchronize_geometry_cache()
            config_data = {
                "settings": {
                    "download_path":         download_path,
                    "proxy_address":         safe_str(settings_screen.proxy_input.value),
                    "proxy_enabled":         proxy_enabled,
                    "yt_dlp_args":           safe_str(settings_screen.yt_args_input.value),
                    "audio_only":            bool(main_screen.audio_only_switch.value),
                    "cookies_browser":       safe_str(settings_screen.cookies_browser_dropdown.value),
                    "cookies_enabled":       bool(main_screen.cookies_enabled_switch.value),
                    "embed_metadata":        bool(settings_screen.embed_metadata_switch.value),
                    "playlist_enabled":      bool(settings_screen.playlist_switch.value),
                    "clean_titles":          bool(settings_screen.clean_titles_switch.value),
                    "save_to_source_folder": bool(settings_screen.save_to_source_switch.value),
                    "minimize_to_tray":      bool(settings_screen.minimize_to_tray_switch.value),
                    "urls": {
                        "yt_api":          safe_str(settings_screen.yt_api_input.value),
                        "yt_download":     safe_str(settings_screen.yt_download_input.value),
                        "ffmpeg_version":  safe_str(settings_screen.ffmpeg_version_input.value),
                        "ffmpeg_download": safe_str(settings_screen.ffmpeg_download_input.value),
                    },
                },
                "window": current_geometry,
                "theme":  dict(current_theme),
            }
            config_mgr.save(config_data)

        # ── Кнопки тулбара ────────────────────────────────────────────────────
        def update_proxy_button_ui():
            if proxy_enabled:
                proxy_btn.icon       = ft.Icons.SHIELD_ROUNDED
                proxy_btn.icon_color = ft.Colors.GREEN_400
                proxy_btn.tooltip    = "Прокси: ВКЛ"
            else:
                proxy_btn.icon       = ft.Icons.SHIELD_OUTLINED
                proxy_btn.icon_color = ft.Colors.WHITE
                proxy_btn.tooltip    = "Прокси: ВЫКЛ"

        def update_cookies_ui():
            settings_screen.update_cookies_ui(main_screen.cookies_enabled_switch)

        settings_screen.set_cookies_change_callback(update_cookies_ui)
        settings_screen.set_proxy_enabled_callback(lambda: proxy_enabled)

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

        # ── Навигация (оригинальная логика) ───────────────────────────────────
        main_status_container = ft.Container(
            content=main_screen.folder_label, padding=ft.Padding(left=10, right=10)
        )
        settings_status_container = ft.Container(
            content=ft.Column([settings_screen.progress_text, settings_screen.progress_bar], spacing=4, tight=True),
            padding=ft.Padding(left=10, right=10)
        )

        def show_settings(_):
            main_screen.layout.visible     = False
            settings_screen.layout.visible = True
            page.appbar = ft.AppBar(
                title=ft.Text("Настройки конфигурации", size=18, weight=ft.FontWeight.W_600),
                bgcolor=hex_to_flet(current_theme.get("appbar_color", "1c1c1c")),
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
                title=ft.Text("SaveMedia Dashboard", size=18, weight=ft.FontWeight.W_600),
                bgcolor=hex_to_flet(current_theme.get("appbar_color", "1c1c1c")),
                actions=[settings_btn, proxy_btn, folder_btn, exit_btn]
            )
            page.bottom_appbar.content = main_status_container
            safe_update()

        async def open_folder_picker(_):
            path = await ft.FilePicker().get_directory_path(dialog_title="Выберите папку сохранения медиа")
            if path:
                nonlocal download_path
                download_path = str(path)
                main_screen.folder_label.value = f"Папка назначения: {path}"
                main_screen.folder_label.color = ft.Colors.GREEN_400
                try:
                    os.makedirs(download_path, exist_ok=True)
                except Exception:
                    pass
                save_config()
                safe_update()

        def toggle_proxy(_):
            nonlocal proxy_enabled
            proxy_enabled = not proxy_enabled
            update_proxy_button_ui()
            save_config()
            safe_update()

        folder_btn.on_click   = open_folder_picker
        proxy_btn.on_click    = toggle_proxy
        settings_btn.on_click = show_settings

        # Провайдер параметров загрузки для MainScreen
        def get_download_opts() -> dict:
            return {
                "download_path":   download_path,
                "proxy_enabled":   proxy_enabled,
                "proxy_address":   safe_str(settings_screen.proxy_input.value),
                "cookies_enabled": bool(main_screen.cookies_enabled_switch.value),
                "cookies_browser": safe_str(settings_screen.cookies_browser_dropdown.value),
                "playlist_enabled":bool(settings_screen.playlist_switch.value),
                "embed_metadata":  bool(settings_screen.embed_metadata_switch.value),
                "audio_only":      bool(main_screen.audio_only_switch.value),
                "yt_dlp_args":     safe_str(settings_screen.yt_args_input.value),
                "clean_titles":    bool(settings_screen.clean_titles_switch.value),
                "save_to_source":  bool(settings_screen.save_to_source_switch.value),
            }

        main_screen.set_download_opts_provider(get_download_opts)

        # ── Загрузка конфига (оригинальная логика) ────────────────────────────
        def load_config():
            nonlocal download_path, proxy_enabled
            config_data = config_mgr.load()

            saved_theme = config_data.get("theme", {})
            if isinstance(saved_theme, dict):
                for key in DEFAULT_CONFIG["theme"]:
                    current_theme[key] = (
                        safe_str(saved_theme.get(key, DEFAULT_CONFIG["theme"][key]))
                        or DEFAULT_CONFIG["theme"][key]
                    )

            cfg = config_data.get("settings", {})
            download_path = safe_str(cfg.get("download_path", ""))
            if not download_path:
                download_path = os.path.join(os.path.expanduser("~"), "Downloads")
            try:
                os.makedirs(download_path, exist_ok=True)
            except Exception:
                pass

            def fb_str(d, k, def_val):
                return def_val if d.get(k) is None or d.get(k) == "" else str(d.get(k))

            settings_screen.proxy_input.value    = fb_str(cfg, "proxy_address", str(DEFAULT_CONFIG["settings"]["proxy_address"]))
            proxy_enabled                         = bool(cfg.get("proxy_enabled", DEFAULT_CONFIG["settings"]["proxy_enabled"]))
            settings_screen.yt_args_input.value  = fb_str(cfg, "yt_dlp_args",  str(DEFAULT_CONFIG["settings"]["yt_dlp_args"]))

            main_screen.audio_only_switch.value          = get_fallback_bool(cfg, "audio_only",           bool(DEFAULT_CONFIG["settings"]["audio_only"]))
            settings_screen.clean_titles_switch.value    = get_fallback_bool(cfg, "clean_titles",          bool(DEFAULT_CONFIG["settings"]["clean_titles"]))
            settings_screen.playlist_switch.value        = get_fallback_bool(cfg, "playlist_enabled",      bool(DEFAULT_CONFIG["settings"]["playlist_enabled"]))
            settings_screen.embed_metadata_switch.value  = get_fallback_bool(cfg, "embed_metadata",        bool(DEFAULT_CONFIG["settings"]["embed_metadata"]))
            settings_screen.save_to_source_switch.value  = get_fallback_bool(cfg, "save_to_source_folder", bool(DEFAULT_CONFIG["settings"]["save_to_source_folder"]))
            settings_screen.minimize_to_tray_switch.value = get_fallback_bool(cfg, "minimize_to_tray",     bool(DEFAULT_CONFIG["settings"]["minimize_to_tray"]))

            settings_screen.cookies_browser_dropdown.value = fb_str(cfg, "cookies_browser", str(DEFAULT_CONFIG["settings"]["cookies_browser"]))
            main_screen.cookies_enabled_switch.value        = get_fallback_bool(cfg, "cookies_enabled", bool(DEFAULT_CONFIG["settings"]["cookies_enabled"]))

            urls = cfg.get("urls", {})
            settings_screen.yt_api_input.value          = fb_str(urls, "yt_api",          str(DEFAULT_CONFIG["settings"]["urls"]["yt_api"]))
            settings_screen.yt_download_input.value     = fb_str(urls, "yt_download",     str(DEFAULT_CONFIG["settings"]["urls"]["yt_download"]))
            settings_screen.ffmpeg_version_input.value  = fb_str(urls, "ffmpeg_version",  str(DEFAULT_CONFIG["settings"]["urls"]["ffmpeg_version"]))
            settings_screen.ffmpeg_download_input.value = fb_str(urls, "ffmpeg_download", str(DEFAULT_CONFIG["settings"]["urls"]["ffmpeg_download"]))

            if download_path:
                main_screen.folder_label.value = f"Папка назначения: {download_path}"
                main_screen.folder_label.color = ft.Colors.GREEN_400

            update_proxy_button_ui()
            update_cookies_ui()

        # ── Трей (оригинальная логика) ────────────────────────────────────────
        def show_tray():
            try:
                if os.path.exists("SaveMedia.png"):
                    image = Image.open("SaveMedia.png")
                else:
                    raise FileNotFoundError
            except Exception:
                image = Image.new("RGBA", (64, 64), color=(30, 30, 30, 255))
                draw  = ImageDraw.Draw(image)
                draw.ellipse([10, 10, 54, 54], fill=(0, 119, 255, 255))

            def on_restore(icon, item):
                icon.stop()
                async def restore_ui():
                    page.window.visible   = True
                    page.window.minimized = False
                    page.update()
                page.run_task(restore_ui)

            def on_quit(icon, item):
                icon.stop()
                try:
                    save_config()
                except Exception:
                    pass
                async def kill_window():
                    page.window.prevent_close = False
                    page.window.on_event      = None
                    page.update()
                    await page.window.destroy()
                page.run_task(kill_window)

            menu = pystray.Menu(
                pystray.MenuItem("Развернуть", on_restore, default=True),
                pystray.MenuItem("Выход", on_quit)
            )
            icon = pystray.Icon("SaveMedia", image, "SaveMedia", menu)
            page.window.visible = False
            page.update()
            threading.Thread(target=icon.run, daemon=True).start()

        async def handle_window_event(e):
            ev = str(getattr(e, "type", None) or getattr(e, "data", None)).lower()
            if "close" in ev:
                try:
                    save_config()
                except Exception:
                    pass
                if settings_screen.minimize_to_tray_switch.value:
                    show_tray()
                else:
                    page.window.prevent_close = False
                    page.window.on_event      = None
                    page.update()
                    await page.window.destroy()
            elif "minimize" in ev:
                if settings_screen.minimize_to_tray_switch.value:
                    show_tray()

        page.window.on_event = handle_window_event

        # ── AppBar / BottomAppBar ──────────────────────────────────────────────
        page.appbar = ft.AppBar(
            title=ft.Text("SaveMedia Dashboard", size=18, weight=ft.FontWeight.W_600),
            bgcolor="#1c1c1c",
            actions=[settings_btn, proxy_btn, folder_btn, exit_btn]
        )
        page.bottom_appbar = ft.BottomAppBar(content=main_status_container, bgcolor="#141414")

        # ── Финальная инициализация ───────────────────────────────────────────
        load_config()
        settings_screen.refresh_theme_fields()
        apply_theme()
        page.add(main_screen.layout, settings_screen.layout)

        if page.platform in [ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS, ft.PagePlatform.LINUX]:
            page.window.visible = True
        page.update()

        await asyncio.sleep(0.1)
        await settings_screen.check_tools(proxy_enabled)
