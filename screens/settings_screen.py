import asyncio

import flet as ft

from config import (
    THEME_FIELDS, PALETTE, ThemeConfig,
    hex_to_flet, is_valid_hex, safe_str
)
from events import EventBus, ToolsCheckedEvent, ToolsRestoredEvent, ToolsStatusMessageEvent
from managers.tools_manager import ToolsManager
from state import AppState


class SettingsScreen:

    def __init__(self, page: ft.Page, tools: ToolsManager, safe_update,
                 state: AppState, bus: EventBus) -> None:
        self._page        = page
        self._tools       = tools
        self._safe_update = safe_update
        self._state       = state
        self._bus         = bus

        # Единственный оставшийся колбэк — применение темы к виджетам.
        # Он не передаёт данные, а вызывает перерисовку в app.py,
        # где есть доступ ко всем виджетам обоих экранов.
        self._on_theme_changed:    callable = lambda: None
        self._on_settings_changed: callable = lambda: None

        self._build_widgets()
        self._build_theme_section()
        self._build_layout()

    # ── Синхронизация ─────────────────────────────────────────────────────────

    def sync_from_state(self) -> None:
        s = self._state
        self.proxy_input.value                 = s.proxy_address
        self.yt_args_input.value               = s.yt_dlp_args
        self.clean_titles_switch.value         = s.clean_titles
        self.playlist_switch.value             = s.playlist_enabled
        self.embed_metadata_switch.value       = s.embed_metadata
        self.save_to_source_switch.value       = s.save_to_source_folder
        self.cookies_browser_dropdown.value    = s.cookies_browser
        self.yt_api_input.value                = s.url_yt_api
        self.yt_download_input.value           = s.url_yt_download
        self.ffmpeg_version_input.value        = s.url_ffmpeg_version
        self.ffmpeg_download_input.value       = s.url_ffmpeg_download

    def sync_to_state(self) -> None:
        s = self._state
        s.proxy_address         = safe_str(self.proxy_input.value)
        s.yt_dlp_args           = safe_str(self.yt_args_input.value)
        s.clean_titles          = bool(self.clean_titles_switch.value)
        s.playlist_enabled      = bool(self.playlist_switch.value)
        s.embed_metadata        = bool(self.embed_metadata_switch.value)
        s.save_to_source_folder = bool(self.save_to_source_switch.value)
        s.cookies_browser       = safe_str(self.cookies_browser_dropdown.value)
        s.url_yt_api            = safe_str(self.yt_api_input.value)
        s.url_yt_download       = safe_str(self.yt_download_input.value)
        s.url_ffmpeg_version    = safe_str(self.ffmpeg_version_input.value)
        s.url_ffmpeg_download   = safe_str(self.ffmpeg_download_input.value)

    # ── Виджеты ───────────────────────────────────────────────────────────────

    def _build_widgets(self) -> None:
        self.proxy_input = ft.TextField(
            label="Адрес прокси-сервера", border_radius=8,
            focused_border_color=ft.Colors.BLUE
        )
        self.yt_args_input = ft.TextField(
            label="Параметры качества / Аргументы yt-dlp", border_radius=8,
            focused_border_color=ft.Colors.BLUE
        )
        self.clean_titles_switch     = ft.Switch(label="Чистые названия файлов (без ID)", active_color=ft.Colors.GREEN)
        self.playlist_switch         = ft.Switch(label="Скачивать плейлисты целиком",     active_color=ft.Colors.GREEN)
        self.embed_metadata_switch   = ft.Switch(label="Обогащать файлы (метаданные/обложка)", active_color=ft.Colors.GREEN)
        self.save_to_source_switch   = ft.Switch(label="Сортировать по подпапкам сервисов",    active_color=ft.Colors.GREEN)

        self.cookies_browser_dropdown = ft.Dropdown(
            label="Выбор источника Cookies",
            border_radius=8,
            focused_border_color=ft.Colors.BLUE,
            options=[
                ft.dropdown.Option("none",    "Не использовать / Выключить"),
                ft.dropdown.Option("chrome",  "Google Chrome"),
                ft.dropdown.Option("yandex",  "Яндекс.Браузер"),
                ft.dropdown.Option("firefox", "Mozilla Firefox"),
                ft.dropdown.Option("edge",    "Microsoft Edge"),
                ft.dropdown.Option("opera",   "Opera")
            ],
        )
        self.cookies_browser_dropdown.on_change = self._on_browser_dropdown_change

        self.yt_status      = ft.Text("yt-dlp: —",  color=ft.Colors.GREY_600, size=13, weight=ft.FontWeight.BOLD)
        self.ffmpeg_status  = ft.Text("ffmpeg: —",  color=ft.Colors.GREY_600, size=13, weight=ft.FontWeight.BOLD)
        self.ffplay_status  = ft.Text("ffplay: —",  color=ft.Colors.GREY_600, size=13, weight=ft.FontWeight.BOLD)
        self.ffprobe_status = ft.Text("ffprobe: —", color=ft.Colors.GREY_600, size=13, weight=ft.FontWeight.BOLD)

        self.progress_text = ft.Text("Компоненты: ожидание действий", size=12, color=ft.Colors.GREEN_400)
        self.progress_bar  = ft.ProgressBar(
            value=0.0, color=ft.Colors.GREEN_400,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, visible=False
        )

        self.yt_api_input          = ft.TextField(label="API утилиты yt-dlp",           border_radius=8, focused_border_color=ft.Colors.BLUE)
        self.yt_download_input     = ft.TextField(label="Ссылка на скачивание yt-dlp",  border_radius=8, focused_border_color=ft.Colors.BLUE)
        self.ffmpeg_version_input  = ft.TextField(label="Файл версии пакета FFmpeg",    border_radius=8, focused_border_color=ft.Colors.BLUE)
        self.ffmpeg_download_input = ft.TextField(label="Ссылка на zip-архив FFmpeg",   border_radius=8, focused_border_color=ft.Colors.BLUE)

        self.update_btn_icon = ft.Icon(ft.Icons.REFRESH_ROUNDED, color=ft.Colors.WHITE)
        self.update_btn_text = ft.Text("Проверить версии", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
        self.update_btn = ft.Button(
            content=ft.Row([self.update_btn_icon, self.update_btn_text], tight=True, spacing=8),
            bgcolor=ft.Colors.GREEN,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=2),
            on_click=self._handle_update_button_click
        )

        self.header_net   = ft.Text("Сеть и Безопасность",           size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self.header_rules = ft.Text("Правила обработки и имена",      size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self.header_deps  = ft.Text("Локальные зависимости системы",  size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self.header_theme = ft.Text("Оформление интерфейса",          size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self.header_urls  = ft.Text("Управление сервисными URL",      size=13, weight=ft.FontWeight.W_500, color=ft.Colors.CYAN_400)

    # ── Куки UI ───────────────────────────────────────────────────────────────

    def update_cookies_ui(self, cookies_enabled_switch: ft.Switch) -> None:
        if self.cookies_browser_dropdown.value == "none" or not self.cookies_browser_dropdown.value:
            cookies_enabled_switch.value    = False
            cookies_enabled_switch.disabled = True
            cookies_enabled_switch.label    = "Куки выключены (выберите браузер)"
        else:
            cookies_enabled_switch.disabled = False
            sel = next(
                (opt.text for opt in self.cookies_browser_dropdown.options
                 if opt.key == self.cookies_browser_dropdown.value), ""
            )
            cookies_enabled_switch.label = f"Использовать куки ({sel})"

    def _on_browser_dropdown_change(self, _):
        self.sync_to_state()
        self._on_settings_changed()
        self._page.update()

    # ── Секция темы ───────────────────────────────────────────────────────────

    def _build_theme_section(self) -> None:
        def make_color_row(key: str, label: str) -> ft.Column:
            preview = ft.Container(
                width=28, height=28, border_radius=6,
                bgcolor=hex_to_flet(getattr(self._state.theme, key, "FFFFFF")),
                border=ft.Border.all(1, "#555555"), tooltip="Открыть палитру",
            )
            field = ft.TextField(
                value=getattr(self._state.theme, key, "FFFFFF").upper().lstrip("#"),
                width=100, border_radius=6, text_size=13,
                capitalization=ft.TextCapitalization.CHARACTERS,
                max_length=6,
                content_padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                hint_text="RRGGBB",
            )
            palette_grid = ft.Row(wrap=True, spacing=4, run_spacing=4, width=280)
            palette_container = ft.Container(
                content=palette_grid, bgcolor="#1e1e1e", border_radius=8,
                padding=8, border=ft.Border.all(1, "#333333"), visible=False,
            )

            def apply_color(hex_val: str, f=field, p=preview, pc=palette_container):
                setattr(self._state.theme, key, hex_val)
                f.value        = hex_val.upper()
                f.border_color = None
                p.bgcolor      = hex_to_flet(hex_val)
                pc.visible     = False
                self._on_theme_changed()
                self._on_settings_changed()
                self._safe_update()

            for color_hex in PALETTE:
                c = color_hex
                palette_grid.controls.append(
                    ft.Container(
                        width=24, height=24, border_radius=4,
                        bgcolor=f"#{c}", border=ft.Border.all(1, "#00000044"),
                        tooltip=f"#{c}", on_click=lambda e, h=c: apply_color(h),
                    )
                )

            preview.on_click = lambda e, pc=palette_container: (
                setattr(pc, "visible", not pc.visible), self._safe_update()
            )

            def on_field_change(e, f=field, p=preview):
                val = safe_str(f.value).strip().lstrip("#").upper()
                if is_valid_hex(val):
                    setattr(self._state.theme, key, val)
                    p.bgcolor      = hex_to_flet(val)
                    f.border_color = None
                    self._on_theme_changed()
                    self._safe_update()
                else:
                    f.border_color = ft.Colors.RED_400
                    self._safe_update()

            field.on_change = on_field_change

            return ft.Column([
                ft.Row([
                    ft.Text(label, size=12, expand=True, color=ft.Colors.GREY_300),
                    field, preview,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                palette_container,
            ], spacing=4, tight=True)

        self.theme_fields_column = ft.Column(
            [make_color_row(k, l) for k, l in THEME_FIELDS], spacing=10
        )
        self.theme_section = ft.Container(
            content=ft.Column([
                ft.Row([
                    self.header_theme,
                    ft.IconButton(
                        icon=ft.Icons.RESTART_ALT_ROUNDED, icon_color=ft.Colors.GREY_400,
                        icon_size=18, tooltip="Сбросить к стандартным цветам",
                        on_click=self._reset_theme
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Text("Формат: RRGGBB (без решётки)", size=11, color=ft.Colors.GREY_500),
                self.theme_fields_column,
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15
        )

    def _reset_theme(self, _):
        defaults = ThemeConfig()
        for key in vars(defaults):
            setattr(self._state.theme, key, getattr(defaults, key))
        self.refresh_theme_fields()
        self._on_theme_changed()
        self._on_settings_changed()
        self._safe_update()

    def refresh_theme_fields(self):
        for col in self.theme_fields_column.controls:
            if isinstance(col, ft.Column) and col.controls:
                top_row = col.controls[0]
                if isinstance(top_row, ft.Row) and len(top_row.controls) >= 3:
                    label_text = top_row.controls[0].value
                    key = next((k for k, l in THEME_FIELDS if l == label_text), None)
                    if key:
                        top_row.controls[1].value        = getattr(self._state.theme, key).upper().lstrip("#")
                        top_row.controls[1].border_color = None
                        top_row.controls[2].bgcolor      = hex_to_flet(getattr(self._state.theme, key))

    # ── Проверка / обновление инструментов ────────────────────────────────────

    def on_tools_restored(self, e: ToolsRestoredEvent) -> None:
        """Восстанавливает виджеты раздела скриптов из сохранённого state при перезапуске."""
        color_map = {
            "ok":      ft.Colors.GREEN_400,
            "outdated": ft.Colors.ORANGE_400,
            "missing":  ft.Colors.RED_400,
            "error":    ft.Colors.AMBER,
        }
        tool_status_map = {
            "yt-dlp":  self.yt_status,
            "ffmpeg":  self.ffmpeg_status,
            "ffplay":  self.ffplay_status,
            "ffprobe": self.ffprobe_status,
        }
        for name, widget in tool_status_map.items():
            pair = e.tool_versions.get(name)
            if pair:
                loc, rem, status_key = pair
                widget.value = f"{name}: Локально: {loc} | Сеть: {rem}"
                widget.color = color_map.get(status_key, ft.Colors.GREY_600)
            else:
                widget.value = f"{name}: —"
                widget.color = ft.Colors.GREY_600

        if e.needs_update:
            self.update_btn_text.value = "Обновить скрипты"
            self.update_btn_icon.name  = ft.Icons.DOWNLOAD_ROUNDED
            self.progress_text.value   = f"Есть обновления — следующая проверка через {e.mins_until_check} мин"
            self.progress_text.color   = ft.Colors.ORANGE_400
        else:
            self.update_btn_text.value = "Проверить версии"
            self.update_btn_icon.name  = ft.Icons.REFRESH_ROUNDED
            self.progress_text.value   = f"Все актуально — следующая проверка через {e.mins_until_check} мин"
            self.progress_text.color   = ft.Colors.GREEN_400
        # layout может быть невидим — safe_update всё равно фиксирует значения в дереве
        self._safe_update()

    async def check_tools(self) -> None:
        self.progress_text.value = "Проверка версий..."
        self.progress_text.color = ft.Colors.GREEN_400
        await asyncio.sleep(0.02)

        tool_status_map = {
            "yt-dlp":  self.yt_status,
            "ffmpeg":  self.ffmpeg_status,
            "ffplay":  self.ffplay_status,
            "ffprobe": self.ffprobe_status,
        }

        def on_local_version(name: str, version: str):
            tool_status_map[name].value = f"{name}: Локально: {version} | Сеть: опрос..."
            tool_status_map[name].color = ft.Colors.ORANGE_400
            self._page.update()

        def on_remote_done(name: str, loc: str, rem: str):
            tool_status_map[name].value = f"{name}: Локально: {loc} | Сеть: {rem}"
            is_equal = (loc == rem) or (
                "[" not in rem and "[" not in loc
                and "Ошибка" not in rem and "Отсутствует" not in loc
                and (rem in loc or loc in rem)
            )
            if "Отсутствует" in loc:
                tool_status_map[name].color = ft.Colors.RED_400
                status_key = "missing"
            elif "[" in loc or "Ошибка" in rem or "[" in rem:
                tool_status_map[name].color = ft.Colors.AMBER
                status_key = "error"
            elif is_equal:
                tool_status_map[name].color = ft.Colors.GREEN_400
                status_key = "ok"
            else:
                tool_status_map[name].color = ft.Colors.ORANGE_400
                status_key = "outdated"
            self._state.tool_versions[name] = (loc, rem, status_key)
            self._page.update()

        proxy_url = self._state.proxy_address.strip() if self._state.proxy_enabled else None

        await self._tools.check_all(
            yt_api_url=self._state.url_yt_api,
            ffmpeg_version_url=self._state.url_ffmpeg_version,
            proxy_url=proxy_url,
            on_local_version=on_local_version,
            on_remote_done=on_remote_done,
        )

        needs = self._tools.yt_needs_update or self._tools.ffmpeg_needs_update
        if needs:
            self.update_btn_text.value = "Обновить скрипты"
            self.update_btn_icon.name  = ft.Icons.DOWNLOAD_ROUNDED
            self.progress_text.value   = "Доступны новые обновления утилит!"
            self.progress_text.color   = ft.Colors.ORANGE
        else:
            self.update_btn_text.value = "Проверить версии"
            self.update_btn_icon.name  = ft.Icons.REFRESH_ROUNDED
            self.progress_text.value   = "Все компоненты обновлены и актуальны"
            self.progress_text.color   = ft.Colors.GREEN_400

        self.update_btn.disabled = False

        # Публикуем результат — app.py сохранит, MainScreen покажет статус
        self._bus.emit(ToolsCheckedEvent(needs_update=needs))
        self._page.update()

    async def _update_tools(self) -> None:
        self.update_btn.disabled   = True
        self.update_btn_icon.name  = ft.Icons.HOURGLASS_TOP_ROUNDED
        self.update_btn_text.value = "Обновление..."
        self.progress_bar.visible  = True
        self.progress_bar.value    = 0.0
        self.progress_text.value   = "Подготовка фоновой загрузки..."
        self.progress_text.color   = ft.Colors.GREEN_400
        self._safe_update()

        proxy_url = self._state.proxy_address.strip() if self._state.proxy_enabled else None

        def on_yt_status(message: str, state: str):
            self.yt_status.value = message
            self.yt_status.color = (
                ft.Colors.ORANGE    if state == "orange" else
                ft.Colors.GREEN_400 if state == "ok"     else ft.Colors.RED
            )
            self._safe_update()

        def on_ff_status(message: str, state: str):
            self.ffmpeg_status.value = message
            self.ffmpeg_status.color = (
                ft.Colors.ORANGE    if state == "orange" else
                ft.Colors.GREEN_400 if state == "ok"     else ft.Colors.RED
            )
            self._safe_update()

        def on_progress(message: str, value):
            self.progress_text.value = message
            self.progress_bar.value  = float(value) if value is not None else None
            self._safe_update()

        result = {"had_errors": False, "critical_err": ""}

        def on_done(had_errors: bool, critical_err: str = ""):
            result["had_errors"]   = had_errors
            result["critical_err"] = critical_err
            self.progress_bar.visible  = False
            if critical_err:
                self.progress_text.value = f"Критическая ошибка: {critical_err}"
                self.progress_text.color = ft.Colors.RED_400
            elif had_errors:
                self.progress_text.value = "Обновление завершено с ошибками"
                self.progress_text.color = ft.Colors.RED_400
            else:
                self.progress_text.value = "Обновление завершено успешно"
                self.progress_text.color = ft.Colors.GREEN_400
            self.update_btn.disabled   = False
            self.update_btn_icon.name  = ft.Icons.REFRESH_ROUNDED
            self.update_btn_text.value = "Проверить версии"
            self._safe_update()

        await self._tools.update_all(
            proxy_url=proxy_url,
            yt_download_url=self._state.url_yt_download,
            ffmpeg_download_url=self._state.url_ffmpeg_download,
            on_yt_status=on_yt_status,
            on_ff_status=on_ff_status,
            on_progress=on_progress,
            on_done=on_done,
        )

        if not result["had_errors"] and not result["critical_err"]:
            await self.check_tools()

    async def _handle_update_button_click(self, _):
        if "Проверить" in self.update_btn_text.value:
            self.update_btn.disabled   = True
            self.update_btn_text.value = "Проверка..."
            self._safe_update()
            await self.check_tools()
        else:
            await self._update_tools()

    # ── Колбэки из App (только 2 — тема и сохранение) ────────────────────────

    def set_on_theme_changed(self, callback) -> None:
        self._on_theme_changed = callback

    def set_on_settings_changed(self, callback) -> None:
        self._on_settings_changed = callback

    # ── Лэйаут ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        self.layout = ft.Column([
            ft.Container(
                content=ft.Column([
                    self.header_net,
                    self.proxy_input,
                    self.cookies_browser_dropdown,
                ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                bgcolor="#161616", border_radius=8, padding=15
            ),
            ft.Container(
                content=ft.Column([
                    self.header_rules,
                    self.yt_args_input,
                    ft.Column([
                        self.clean_titles_switch, self.playlist_switch,
                        self.embed_metadata_switch, self.save_to_source_switch
                    ], spacing=10)
                ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                bgcolor="#161616", border_radius=8, padding=15
            ),
            ft.Container(
                content=ft.Column([
                    self.header_deps,
                    ft.Column([self.yt_status, self.ffmpeg_status,
                               self.ffplay_status, self.ffprobe_status], spacing=6),
                    ft.Row([self.update_btn], alignment=ft.MainAxisAlignment.END)
                ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                bgcolor="#161616", border_radius=8, padding=15
            ),
            self.theme_section,
            ft.ExpansionTile(
                title=self.header_urls,
                controls=[ft.Container(
                    content=ft.Column([
                        self.yt_api_input, self.yt_download_input,
                        self.ffmpeg_version_input, self.ffmpeg_download_input
                    ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                    padding=10
                )]
            ),
        ], visible=False, scroll=ft.ScrollMode.AUTO, expand=True, spacing=15,
           horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
