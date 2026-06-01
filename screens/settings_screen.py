import asyncio

import flet as ft

from config import (
    THEME_FIELDS, THEME_GROUPS, PALETTE, ThemeConfig,
    hex_to_flet, is_valid_hex, safe_str
)
from events import EventBus, ToolsCheckedEvent, ToolsRestoredEvent
from locale import Locale, Strings
from managers.tools_manager import ToolsManager
from services import Services


class SettingsScreen:

    def __init__(self, page: ft.Page, svc: Services) -> None:
        self._page        = page
        self._tools       = svc.tools
        self._safe_update = svc.safe_update
        self._state       = svc.state
        self._bus         = svc.bus

        self._on_theme_changed:    callable = lambda: None
        self._on_settings_changed: callable = lambda: None
        self._on_language_changed: callable = lambda: None

        self._s: Strings = Locale.load(self._state.language)
        

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
        self.language_dropdown.value           = s.language

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
        s.language              = Locale.resolve_language(
            safe_str(self.language_dropdown.value) or Locale.default_language()
        )

    # ── Виджеты ───────────────────────────────────────────────────────────────

    def _build_widgets(self) -> None:
        s = self._s

        self.proxy_input = ft.TextField(
            label=s.proxy_label, border_radius=8,
            focused_border_color=ft.Colors.BLUE,
        )
        self.yt_args_input = ft.TextField(
            label=s.yt_args_label, border_radius=8,
            focused_border_color=ft.Colors.BLUE,
        )
        self.clean_titles_switch   = ft.Switch(label=s.switch_clean,    active_color=ft.Colors.GREEN)
        self.playlist_switch       = ft.Switch(label=s.switch_playlist, active_color=ft.Colors.GREEN)
        self.embed_metadata_switch = ft.Switch(label=s.switch_metadata, active_color=ft.Colors.GREEN)
        self.save_to_source_switch = ft.Switch(label=s.switch_source,   active_color=ft.Colors.GREEN)

        self.cookies_browser_dropdown = ft.Dropdown(
            label=s.cookies_label,
            border_radius=8,
            focused_border_color=ft.Colors.BLUE,
            options=[
                ft.dropdown.Option("none",    s.cookies_none),
                ft.dropdown.Option("chrome",  s.cookies_chrome),
                ft.dropdown.Option("yandex",  s.cookies_yandex),
                ft.dropdown.Option("firefox", s.cookies_firefox),
                ft.dropdown.Option("edge",    s.cookies_edge),
                ft.dropdown.Option("opera",   s.cookies_opera),
            ],
            on_select=self._on_browser_dropdown_change,
        )

        self.language_dropdown = ft.Dropdown(
            label=s.language_label,
            border_radius=8,
            focused_border_color=ft.Colors.BLUE,
            width=220,
            options=[
                ft.dropdown.Option(code, name)
                for code, name in Locale.available()
            ],
            value=self._state.language,
            on_select=self._on_language_change,
        )

        self.yt_status      = ft.Text(s.fmt("tool_dash", name="yt-dlp"),  color=ft.Colors.GREY_600, size=13, weight=ft.FontWeight.BOLD)
        self.ffmpeg_status  = ft.Text(s.fmt("tool_dash", name="ffmpeg"),  color=ft.Colors.GREY_600, size=13, weight=ft.FontWeight.BOLD)
        self.ffplay_status  = ft.Text(s.fmt("tool_dash", name="ffplay"),  color=ft.Colors.GREY_600, size=13, weight=ft.FontWeight.BOLD)
        self.ffprobe_status = ft.Text(s.fmt("tool_dash", name="ffprobe"), color=ft.Colors.GREY_600, size=13, weight=ft.FontWeight.BOLD)

        self.progress_text = ft.Text(s.status_waiting, size=12, color=ft.Colors.GREEN_400)
        self.progress_bar  = ft.ProgressBar(
            value=0.0, color=ft.Colors.GREEN_400,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, visible=False,
        )

        self.yt_api_input          = ft.TextField(label=s.url_yt_api,          border_radius=8, focused_border_color=ft.Colors.BLUE)
        self.yt_download_input     = ft.TextField(label=s.url_yt_download,     border_radius=8, focused_border_color=ft.Colors.BLUE)
        self.ffmpeg_version_input  = ft.TextField(label=s.url_ffmpeg_version,  border_radius=8, focused_border_color=ft.Colors.BLUE)
        self.ffmpeg_download_input = ft.TextField(label=s.url_ffmpeg_download, border_radius=8, focused_border_color=ft.Colors.BLUE)

        self.update_btn_icon = ft.Icon(ft.Icons.REFRESH_ROUNDED, color=ft.Colors.WHITE)
        self.update_btn_text = ft.Text(s.btn_check, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
        self.update_btn = ft.Button(
            content=ft.Row([self.update_btn_icon, self.update_btn_text], tight=True, spacing=8),
            bgcolor=ft.Colors.GREEN,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=2),
            on_click=self._handle_update_button_click,
        )

        self.header_net        = ft.Text(s.section_network,    size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400)
        self.header_rules      = ft.Text(s.section_rules,      size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400)
        self.header_deps       = ft.Text(s.section_deps,       size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400)
        self.header_theme      = ft.Text(s.section_theme,      size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400)
        self.header_urls       = ft.Text(s.section_urls,       size=13, weight=ft.FontWeight.W_500, color=ft.Colors.CYAN_400)
        self.header_appearance = ft.Text(s.section_appearance, size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400)

    # ── Куки UI ───────────────────────────────────────────────────────────────

    def update_cookies_ui(self, cookies_enabled_switch: ft.Switch) -> None:
        s = self._s
        val = self.cookies_browser_dropdown.value
        if not val or val == "none":
            cookies_enabled_switch.value    = False
            cookies_enabled_switch.disabled = True
            cookies_enabled_switch.label    = s.cookies_switch_off
        else:
            browser_name = next(
                (opt.text for opt in self.cookies_browser_dropdown.options if opt.key == val), val
            )
            cookies_enabled_switch.disabled = False
            cookies_enabled_switch.label    = s.cookies_switch_on.format(browser=browser_name)

    def _on_browser_dropdown_change(self, _):
        self.sync_to_state()
        self._on_settings_changed()
        self._page.update()

    def _on_language_change(self, _) -> None:
        self.sync_to_state()
        self._on_settings_changed()
        self._on_language_changed()

    # ── Секция темы ───────────────────────────────────────────────────────────

    def _build_theme_section(self) -> None:
        s = self._s

        def make_color_row(field_key: str, label_key: str) -> ft.Column:
            label   = getattr(s, label_key, label_key)
            preview = ft.Container(
                width=28, height=28, border_radius=6,
                bgcolor=hex_to_flet(getattr(self._state.theme, field_key, "FFFFFF")),
                border=ft.Border.all(1, "#555555"),
            )
            field = ft.TextField(
                value=getattr(self._state.theme, field_key, "FFFFFF").upper().lstrip("#"),
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

            def apply_color(hex_val: str):
                setattr(self._state.theme, field_key, hex_val)
                field.value        = hex_val.upper()
                field.border_color = None
                preview.bgcolor    = hex_to_flet(hex_val)
                palette_container.visible = False
                self._on_theme_changed()
                self._on_settings_changed()
                self._safe_update()

            for c in PALETTE:
                palette_grid.controls.append(
                    ft.Container(
                        width=24, height=24, border_radius=4,
                        bgcolor=f"#{c}", border=ft.Border.all(1, "#00000044"),
                        tooltip=f"#{c}", on_click=lambda e, h=c: apply_color(h),
                    )
                )

            preview.on_click = lambda e: (
                setattr(palette_container, "visible", not palette_container.visible),
                self._safe_update(),
            )

            def on_field_change(e):
                val = safe_str(field.value).strip().lstrip("#").upper()
                if is_valid_hex(val):
                    setattr(self._state.theme, field_key, val)
                    preview.bgcolor    = hex_to_flet(val)
                    field.border_color = None
                    self._on_theme_changed()
                    self._safe_update()
                else:
                    field.border_color = ft.Colors.RED_400
                    self._safe_update()

            field.on_change = on_field_change

            return ft.Column([
                ft.Row([
                    ft.Text(label, size=12, expand=True, color=ft.Colors.GREY_300),
                    field, preview,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                palette_container,
            ], spacing=4, tight=True)

        # Строим по группам из THEME_GROUPS
        field_map = dict(THEME_FIELDS)   # {field_key: label_key}
        group_columns = []
        for group_label_key, field_keys in THEME_GROUPS:
            group_label = getattr(s, group_label_key, group_label_key)
            rows = [make_color_row(k, field_map[k]) for k in field_keys]
            group_columns.append(ft.Column([
                ft.Text(group_label, size=12, color=ft.Colors.GREY_500, weight=ft.FontWeight.W_500),
                ft.Divider(height=1, color="#2a2a2a"),
                *rows,
            ], spacing=8))

        self.theme_fields_column = ft.Column(group_columns, spacing=18)
        self.theme_section = ft.Container(
            content=ft.Column([
                ft.Row([
                    self.header_theme,
                    ft.IconButton(
                        icon=ft.Icons.RESTART_ALT_ROUNDED, icon_color=ft.Colors.GREY_400,
                        icon_size=18, tooltip=s.btn_reset_theme,
                        on_click=self._reset_theme,
                    ),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Text(s.theme_hint, size=11, color=ft.Colors.GREY_500),
                self.theme_fields_column,
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15,
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
        for group_col in self.theme_fields_column.controls:
            for ctrl in group_col.controls:
                if isinstance(ctrl, ft.Column) and ctrl.controls:
                    row = ctrl.controls[0]
                    if isinstance(row, ft.Row) and len(row.controls) >= 3:
                        # field_key восстанавливаем через label — ищем совпадение в Strings
                        label_text = row.controls[0].value
                        field_key = next(
                            (fk for fk, lk in THEME_FIELDS
                             if getattr(self._s, lk, "") == label_text),
                            None,
                        )
                        if field_key:
                            row.controls[1].value        = getattr(self._state.theme, field_key).upper().lstrip("#")
                            row.controls[1].border_color = None
                            row.controls[2].bgcolor      = hex_to_flet(getattr(self._state.theme, field_key))

    # ── Смена языка — перезагрузка Strings и обновление всех текстов ──────────

    def rebuild_for_language(self) -> None:
        """Загрузить новый locale-файл, обновить все текстовые метки и вызвать update() на каждом."""
        self._s = Locale.load(self._state.language)
        s = self._s

        # Поля ввода
        self.proxy_input.label    = s.proxy_label;    self.proxy_input.update()
        self.yt_args_input.label  = s.yt_args_label;  self.yt_args_input.update()

        # Переключатели
        self.clean_titles_switch.label   = s.switch_clean;    self.clean_titles_switch.update()
        self.playlist_switch.label       = s.switch_playlist; self.playlist_switch.update()
        self.embed_metadata_switch.label = s.switch_metadata; self.embed_metadata_switch.update()
        self.save_to_source_switch.label = s.switch_source;   self.save_to_source_switch.update()

        # Куки
        self.cookies_browser_dropdown.label = s.cookies_label
        _cookie_attrs = ["cookies_none", "cookies_chrome", "cookies_yandex",
                         "cookies_firefox", "cookies_edge", "cookies_opera"]
        for opt, attr in zip(self.cookies_browser_dropdown.options, _cookie_attrs):
            opt.text = getattr(s, attr)
        self.cookies_browser_dropdown.update()

        # Язык
        self.language_dropdown.label = s.language_label
        self.language_dropdown.update()

        # URL поля
        self.yt_api_input.label          = s.url_yt_api;          self.yt_api_input.update()
        self.yt_download_input.label     = s.url_yt_download;     self.yt_download_input.update()
        self.ffmpeg_version_input.label  = s.url_ffmpeg_version;  self.ffmpeg_version_input.update()
        self.ffmpeg_download_input.label = s.url_ffmpeg_download;  self.ffmpeg_download_input.update()

        # Заголовки секций
        self.header_net.value        = s.section_network;    self.header_net.update()
        self.header_rules.value      = s.section_rules;      self.header_rules.update()
        self.header_deps.value       = s.section_deps;       self.header_deps.update()
        self.header_theme.value      = s.section_theme;      self.header_theme.update()
        self.header_urls.value       = s.section_urls;       self.header_urls.update()
        self.header_appearance.value = s.section_appearance; self.header_appearance.update()

        # Кнопка и статус
        self.update_btn_text.value = s.btn_check;     self.update_btn_text.update()
        self.progress_text.value   = s.status_waiting; self.progress_text.update()

        # Группы цветов — используем индекс в THEME_GROUPS (порядок стабилен)
        field_map = dict(THEME_FIELDS)
        for group_idx, (group_key, field_keys) in enumerate(THEME_GROUPS):
            group_col = self.theme_fields_column.controls[group_idx]
            group_col.controls[0].value = getattr(s, group_key, "")
            group_col.controls[0].update()
            # Строки цветов начинаются с controls[2] (0=label, 1=divider)
            color_rows = [c for c in group_col.controls[2:] if isinstance(c, ft.Column)]
            for field_key, color_row in zip(field_keys, color_rows):
                if color_row.controls:
                    row = color_row.controls[0]
                    if isinstance(row, ft.Row) and row.controls:
                        row.controls[0].value = getattr(s, field_map[field_key], "")
                        row.controls[0].update()

    # ── Инструменты ───────────────────────────────────────────────────────────

    def on_tools_restored(self, e: ToolsRestoredEvent) -> None:
        s = self._s
        color_map = {
            "ok":       ft.Colors.GREEN_400,
            "outdated": ft.Colors.ORANGE_400,
            "missing":  ft.Colors.RED_400,
            "error":    ft.Colors.AMBER,
        }
        tool_widgets = {
            "yt-dlp": self.yt_status, "ffmpeg": self.ffmpeg_status,
            "ffplay": self.ffplay_status, "ffprobe": self.ffprobe_status,
        }
        for name, widget in tool_widgets.items():
            tv = e.tool_versions.get(name)
            if tv and isinstance(tv, tuple) and len(tv) == 3:
                loc, rem, status_key = tv
                widget.value = s.fmt("tool_versions", name=name, loc=loc, rem=rem)
                widget.color = color_map.get(status_key, ft.Colors.GREY_600)
            else:
                widget.value = s.fmt("tool_dash", name=name)
                widget.color = ft.Colors.GREY_600

        if e.needs_update:
            self.update_btn_text.value = s.btn_update
            self.update_btn_icon.name  = ft.Icons.DOWNLOAD_ROUNDED
            self.progress_text.value   = s.fmt("status_has_updates", mins=e.mins_until_check)
            self.progress_text.color   = ft.Colors.ORANGE_400
        else:
            self.update_btn_text.value = s.btn_check
            self.update_btn_icon.name  = ft.Icons.REFRESH_ROUNDED
            self.progress_text.value   = s.fmt("status_all_ok", mins=e.mins_until_check)
            self.progress_text.color   = ft.Colors.GREEN_400
        self._safe_update()

    async def check_tools(self) -> None:
        s = self._s
        self.progress_text.value = s.status_checking
        self.progress_text.color = ft.Colors.GREEN_400
        self.progress_text.update()

        tool_widgets = {
            "yt-dlp": self.yt_status, "ffmpeg": self.ffmpeg_status,
            "ffplay": self.ffplay_status, "ffprobe": self.ffprobe_status,
        }
        color_map = {
            "ok":       ft.Colors.GREEN_400,
            "outdated": ft.Colors.ORANGE_400,
            "missing":  ft.Colors.RED_400,
            "error":    ft.Colors.AMBER,
        }

        def on_local_version(name: str, local: str):
            if name not in tool_widgets:
                return
            loc_text = local if local else s.tool_status_missing
            tool_widgets[name].value = s.fmt("tool_querying", name=name, loc=loc_text)
            tool_widgets[name].color = ft.Colors.GREY_500
            tool_widgets[name].update()

        def on_remote_done(name: str, loc: str, rem: str):
            if name not in tool_widgets:
                return
            # Определяем статус здесь — tools_manager передаёт только версии
            if not loc:
                status = "missing"
            elif not rem or "[" in rem:
                status = "error"
            else:
                status = "ok" if (loc == rem or rem in loc or loc in rem) else "outdated"
            loc_text = loc if loc else s.tool_status_missing
            rem_text = rem if rem else s.tool_status_error
            tool_widgets[name].value = s.fmt("tool_versions", name=name,
                                             loc=loc_text, rem=rem_text)
            tool_widgets[name].color = color_map.get(status, ft.Colors.GREY_600)
            self._state.tool_versions[name] = (loc_text, rem_text, status)
            tool_widgets[name].update()

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
            self.update_btn_text.value = s.btn_update
            self.update_btn_icon.name  = ft.Icons.DOWNLOAD_ROUNDED
            self.progress_text.value   = s.status_updates
            self.progress_text.color   = ft.Colors.ORANGE_400
        else:
            self.update_btn_text.value = s.btn_check
            self.update_btn_icon.name  = ft.Icons.REFRESH_ROUNDED
            self.progress_text.value   = s.status_ok
            self.progress_text.color   = ft.Colors.GREEN_400

        self.update_btn.disabled = False
        self.update_btn_text.update()
        self.update_btn_icon.update()
        self.update_btn.update()
        self.progress_text.update()
        self._bus.emit(ToolsCheckedEvent(needs_update=needs))

    async def _update_tools(self) -> None:
        s = self._s
        self.update_btn.disabled   = True
        self.update_btn_icon.name  = ft.Icons.HOURGLASS_TOP_ROUNDED
        self.update_btn_text.value = s.btn_updating
        self.progress_bar.visible  = True
        self.progress_bar.value    = 0.0
        self.progress_text.value   = s.status_prep
        self.progress_text.color   = ft.Colors.GREEN_400
        self._safe_update()

        proxy_url = self._state.proxy_address.strip() if self._state.proxy_enabled else None

        def on_yt_status(code: str, detail: str):
            if code == "downloading":
                self.yt_status.value = f"yt-dlp: {s.tool_update_downloading}"
                self.yt_status.color = ft.Colors.ORANGE_400
            elif code == "ok":
                self.yt_status.value = f"yt-dlp: {s.tool_update_ok}"
                self.yt_status.color = ft.Colors.GREEN_400
            else:
                self.yt_status.value = f"yt-dlp: {s.fmt('tool_update_error', detail=detail)}"
                self.yt_status.color = ft.Colors.RED_400
            self._safe_update()

        def on_ff_status(code: str, detail: str):
            if code == "downloading":
                self.ffmpeg_status.value = f"ffmpeg: {s.tool_update_downloading}"
                self.ffmpeg_status.color = ft.Colors.ORANGE_400
            elif code == "ok":
                self.ffmpeg_status.value = f"ffmpeg: {s.tool_update_ok}"
                self.ffmpeg_status.color = ft.Colors.GREEN_400
            else:
                self.ffmpeg_status.value = f"ffmpeg: {s.fmt('tool_update_error', detail=detail)}"
                self.ffmpeg_status.color = ft.Colors.RED_400
            self._safe_update()

        def on_progress(pct):
            self.progress_bar.value = pct  # None = индетерминированный
            self._safe_update()

        result = {"had_errors": False, "critical_err": ""}

        def on_done(had_errors: bool, critical_err: str = ""):
            result["had_errors"]   = had_errors
            result["critical_err"] = critical_err
            self.progress_bar.visible  = False
            if critical_err:
                self.progress_text.value = s.fmt("status_critical", err=critical_err)
                self.progress_text.color = ft.Colors.RED_400
            elif had_errors:
                self.progress_text.value = s.status_done_errors
                self.progress_text.color = ft.Colors.RED_400
            else:
                self.progress_text.value = s.status_done_ok
                self.progress_text.color = ft.Colors.GREEN_400
            self.update_btn.disabled   = False
            self.update_btn_icon.name  = ft.Icons.REFRESH_ROUNDED
            self.update_btn_text.value = s.btn_check
            self.update_btn_text.update()
            self.update_btn_icon.update()
            self.update_btn.update()
            self._safe_update()

        await self._tools.update_all(
            proxy_url=proxy_url,
            yt_download_url=self._state.url_yt_download,
            ffmpeg_download_url=self._state.url_ffmpeg_download,
            on_yt_status=on_yt_status, on_ff_status=on_ff_status,
            on_progress=on_progress, on_done=on_done,
        )
        if not result["had_errors"] and not result["critical_err"]:
            await self.check_tools()

    async def _handle_update_button_click(self, _):
        s = self._s
        if self.update_btn_text.value == s.btn_update:
            await self._update_tools()
        else:
            self.update_btn.disabled   = True
            self.update_btn_text.value = s.btn_checking
            self._safe_update()
            await self.check_tools()

    # ── Колбэки из App ────────────────────────────────────────────────────────

    def set_on_theme_changed(self, cb) -> None:    self._on_theme_changed    = cb
    def set_on_settings_changed(self, cb) -> None: self._on_settings_changed = cb
    def set_on_language_changed(self, cb) -> None: self._on_language_changed = cb

    # ── Лэйаут ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        self.layout = ft.Column([
            ft.Container(
                content=ft.Column([
                    self.header_net,
                    self.proxy_input,
                    self.cookies_browser_dropdown,
                ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                bgcolor="#161616", border_radius=8, padding=15,
            ),
            ft.Container(
                content=ft.Column([
                    self.header_rules,
                    self.yt_args_input,
                    ft.Column([
                        self.clean_titles_switch, self.playlist_switch,
                        self.embed_metadata_switch, self.save_to_source_switch,
                    ], spacing=10),
                ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                bgcolor="#161616", border_radius=8, padding=15,
            ),
            ft.Container(
                content=ft.Column([
                    self.header_deps,
                    ft.Column([self.yt_status, self.ffmpeg_status,
                               self.ffplay_status, self.ffprobe_status], spacing=6),
                    ft.Row([self.update_btn], alignment=ft.MainAxisAlignment.END),
                    self.progress_bar,
                    self.progress_text,
                ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                bgcolor="#161616", border_radius=8, padding=15,
            ),
            self.theme_section,
            ft.Container(
                content=ft.Column([
                    self.header_appearance,
                    self.language_dropdown,
                ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                bgcolor="#161616", border_radius=8, padding=15,
            ),
            ft.ExpansionTile(
                title=self.header_urls,
                controls=[ft.Container(
                    content=ft.Column([
                        self.yt_api_input, self.yt_download_input,
                        self.ffmpeg_version_input, self.ffmpeg_download_input,
                    ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                    padding=10,
                )],
            ),
        ], visible=False, scroll=ft.ScrollMode.AUTO, expand=True, spacing=15,
           horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
