
import flet as ft

from config import (
    THEME_FIELDS, THEME_GROUPS, SEVERITY_TOKENS, TOOL_STATUS_TOKENS,
    COOKIE_BROWSERS, ThemeConfig, NamedTheme,
    hex_to_flet, safe_str, severity_color,
)
from managers.tools_manager import (
    TOOL_VERSION_MISSING, TOOL_VERSION_CALL_ERROR,
    TOOL_VERSION_REMOTE_ERR, TOOL_VERSION_UNKNOWN, TOOL_VERSION_NEEDS_RUNTIME,
)
from managers.tool_registry import DEFAULT_TOOLS
from managers.providers import Aria2cProvider
from controllers.i18n_target import I18nTarget
from controllers.theme_target import ThemeTarget
from screens.color_row import ColorRow
from events import (
    ToolsRestoredEvent, ToolsActionRequestedEvent,
    ToolVersionLocalEvent, ToolVersionRemoteEvent,
    ToolButtonStateEvent,
    ToolProgressEvent, ToolProgressMessageEvent,
    ToolInstallStatusEvent,
    SettingsChangedEvent, ThemeChangedEvent, LanguageChangedEvent,
    CookiesChangedEvent, AppClosingEvent,
)
from i18n import Locale, Strings
from services import Services


def _resolve_version(version: str, s) -> str:
    """Перевести sentinel-значение версии инструмента в отображаемую строку.

    Sentinel-константы из tools_manager не содержат переведённого текста —
    они языконезависимы. Перевод происходит здесь, на уровне UI.
    """
    if version == TOOL_VERSION_MISSING:       return s.tool_status_missing
    if version == TOOL_VERSION_CALL_ERROR:    return s.tool_status_call_error
    if version == TOOL_VERSION_NEEDS_RUNTIME: return s.tool_status_needs_python
    if version in (TOOL_VERSION_REMOTE_ERR, TOOL_VERSION_UNKNOWN):
        return s.tool_status_error
    return version


def _fmt_size(num: int) -> str:
    """Размер в байтах → читаемая строка (B/KB/MB/GB/TB)."""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(num)} B"


class SettingsScreen(ThemeTarget, I18nTarget):

    def __init__(self, page: ft.Page, svc: Services) -> None:
        super().__init__()
        self._page        = page
        self._safe_update = svc.safe_update
        self._state       = svc.state
        self._bus         = svc.bus
        self._dm          = svc.dm
        self._db          = svc.db

        self._s: Strings = Locale.load(self._state.language)
        # Последнее ToolsRestoredEvent — повторно показывается при входе в
        # настройки (reapply_restored вызывает навигация).
        self._last_restored: ToolsRestoredEvent | None = None

        self._build_widgets()
        self._build_theme_section()
        self._build_theme_sets_section()
        self._build_layout()

        self._unsubs = [
            self._bus.on(ToolsRestoredEvent,       self._on_tools_restored),
            self._bus.on(ToolVersionLocalEvent,    self._on_tool_local),
            self._bus.on(ToolVersionRemoteEvent,   self._on_tool_remote),
            self._bus.on(ToolButtonStateEvent,     self._on_btn_state),
            self._bus.on(ToolProgressEvent,        self._on_progress),
            self._bus.on(ToolProgressMessageEvent, self._on_progress_msg),
            self._bus.on(ToolInstallStatusEvent,   self._on_install_status),
            self._bus.on(AppClosingEvent,          lambda e: self.dispose()),
        ]

    def dispose(self) -> None:
        """Отписаться от шины при уничтожении экрана."""
        for unsub in self._unsubs:
            unsub()

    # ── Синхронизация ─────────────────────────────────────────────────────────

    def sync_from_state(self) -> None:
        s = self._state
        p = s.ytdlp.parameters
        self.proxy_input.value                 = s.proxy_address
        self.max_parallel_dropdown.value       = str(s.max_parallel)
        self.history_keep_dropdown.value       = str(s.history_keep_days)
        self.notify_switch.value               = s.notify_on_complete
        self.yt_args_input.value               = p.extra_args.value
        self.clean_titles_switch.value         = p.clean_titles.state
        self.playlist_switch.value             = p.playlist.state
        self.embed_metadata_switch.value       = p.embed_metadata.state
        self.save_to_source_switch.value       = p.save_to_source.state
        self.cookies_browser_dropdown.value    = p.cookies.browser
        self.yt_api_input.value          = s.ytdlp.version_url
        self.yt_download_input.value     = s.ytdlp.download_url
        self.ffmpeg_version_input.value  = s.ffmpeg.version_url
        self.ffmpeg_download_input.value = s.ffmpeg.download_url
        self.aria2_version_input.value   = s.aria2c.version_url
        self.aria2_download_input.value  = s.aria2c.download_url
        self.language_dropdown.value           = s.language

    def sync_to_state(self) -> None:
        s = self._state
        p = s.ytdlp.parameters
        s.proxy_address              = safe_str(self.proxy_input.value)
        parallel = self.max_parallel_dropdown.value
        if parallel and str(parallel).isdigit():
            s.max_parallel = max(1, int(parallel))
        keep = self.history_keep_dropdown.value
        if keep is not None and str(keep).isdigit():
            s.history_keep_days = max(0, int(keep))
        s.notify_on_complete = bool(self.notify_switch.value)
        p.extra_args.value           = safe_str(self.yt_args_input.value)
        p.clean_titles.state         = bool(self.clean_titles_switch.value)
        p.playlist.state             = bool(self.playlist_switch.value)
        p.embed_metadata.state       = bool(self.embed_metadata_switch.value)
        p.save_to_source.state       = bool(self.save_to_source_switch.value)
        p.cookies.browser            = safe_str(self.cookies_browser_dropdown.value)
        s.ytdlp.version_url   = safe_str(self.yt_api_input.value)
        s.ytdlp.download_url  = safe_str(self.yt_download_input.value)
        s.ffmpeg.version_url  = safe_str(self.ffmpeg_version_input.value)
        s.ffmpeg.download_url = safe_str(self.ffmpeg_download_input.value)
        s.aria2c.version_url  = safe_str(self.aria2_version_input.value)
        s.aria2c.download_url = safe_str(self.aria2_download_input.value)
        s.language              = Locale.resolve_language(
            safe_str(self.language_dropdown.value) or Locale.default_language()
        )

    # ── Тема ─────────────────────────────────────────────────────────────────

    def apply_theme(self, t) -> None:
        """Применить ThemeConfig к виджетам экрана."""
        super().apply_theme(t)
        # Подложка прогресс-бара (register_progress красит только .color).
        self.progress_bar.bgcolor = hex_to_flet(t.border_color)
        # Кнопки «Тёмная/Светлая» строятся из цветов темы — перестроить.
        self._rebuild_mode_buttons()
        # Статусы инструментов и строка прогресса: перекрасить по их последним
        # токенам/severity из новой палитры (семантика цвета сохраняется).
        for name, token in self._tool_tokens.items():
            self._color_tool(name, token)
        self.progress_text.color = severity_color(t, self._progress_severity)

    # ── Виджеты ───────────────────────────────────────────────────────────────

    def _build_widgets(self) -> None:
        s = self._s

        self.proxy_input = self.register_accents(ft.TextField(
            label=s.proxy_label, border_radius=8,
            focused_border_color=ft.Colors.BLUE,
        ))
        self.register_i18n(self.proxy_input, label="proxy_label")
        self.yt_args_input = self.register_accents(ft.TextField(
            label=s.yt_args_label, border_radius=8,
            focused_border_color=ft.Colors.BLUE,
        ))
        self.register_i18n(self.yt_args_input, label="yt_args_label")
        self.clean_titles_switch   = self.register_switches(ft.Switch(label=s.switch_clean,    active_color=ft.Colors.GREEN))
        self.playlist_switch       = self.register_switches(ft.Switch(label=s.switch_playlist, active_color=ft.Colors.GREEN))
        self.embed_metadata_switch = self.register_switches(ft.Switch(label=s.switch_metadata, active_color=ft.Colors.GREEN))
        self.save_to_source_switch = self.register_switches(ft.Switch(label=s.switch_source,   active_color=ft.Colors.GREEN))
        self.register_i18n(self.clean_titles_switch,   label="switch_clean")
        self.register_i18n(self.playlist_switch,       label="switch_playlist")
        self.register_i18n(self.embed_metadata_switch, label="switch_metadata")
        self.register_i18n(self.save_to_source_switch, label="switch_source")

        # Лимит одновременных загрузок: применяется на лету (менеджер читает
        # state динамически, ожидающие задачи перепроверяют слоты по событию).
        self.max_parallel_dropdown = self.register_accents(ft.Dropdown(
            label=s.max_parallel_label,
            border_radius=8, width=220,
            focused_border_color=ft.Colors.BLUE,
            options=self._max_parallel_options(),
            value=str(self._state.max_parallel),
            on_select=self._on_max_parallel_change,
        ))
        self.register_i18n(self.max_parallel_dropdown, label="max_parallel_label")

        # Пункты — из единого реестра COOKIE_BROWSERS (он же у главного экрана).
        self.cookies_browser_dropdown = self.register_accents(ft.Dropdown(
            label=s.cookies_label,
            border_radius=8,
            focused_border_color=ft.Colors.BLUE,
            options=[
                ft.dropdown.Option(code, getattr(s, label_key))
                for code, label_key in COOKIE_BROWSERS
            ],
            on_select=self._on_browser_dropdown_change,
        ))
        self.register_i18n(self.cookies_browser_dropdown, label="cookies_label")

        # Уведомления о завершении (показываются при свёрнутом/неактивном окне).
        self.notify_switch = self.register_switches(ft.Switch(
            label=s.notify_label, active_color=ft.Colors.GREEN,
        ))
        self.register_i18n(self.notify_switch, label="notify_label")

        # Срок хранения истории; чистка — при старте и при смене значения.
        self.history_keep_dropdown = self.register_accents(ft.Dropdown(
            label=s.history_keep_label,
            border_radius=8, width=220,
            focused_border_color=ft.Colors.BLUE,
            options=self._history_keep_options(s),
            value=str(self._state.history_keep_days),
            on_select=self._on_history_keep_change,
        ))
        self.register_i18n(self.history_keep_dropdown, label="history_keep_label")

        self.language_dropdown = self.register_accents(ft.Dropdown(
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
        ))
        self.register_i18n(self.language_dropdown, label="language_label")

        # Статусные строки инструментов строятся из реестра — добавление
        # нового инструмента автоматически добавляет его строку, без правок здесь.
        self._tool_status: dict[str, ft.Text] = {}
        for spec in DEFAULT_TOOLS:
            for b in spec.binaries(self._state):
                self._tool_status[b.name] = ft.Text(
                    s.fmt("tool_dash", name=b.name),
                    color=hex_to_flet(self._state.theme.text_muted_color),
                    size=13, weight=ft.FontWeight.BOLD,
                )
        # Токен цвета каждой строки статуса (по последнему событию): apply_theme
        # перекрашивает строки из новой палитры, не теряя их семантику.
        self._tool_tokens: dict[str, str] = {
            name: "text_muted_color" for name in self._tool_status
        }

        # progress_text НЕ регистрируется в теме: его цвет несёт severity
        # последнего сообщения, а не токен progress_color. Запоминаем severity
        # и перекрашиваем в apply_theme.
        self._progress_severity = "ok"
        self.progress_text = ft.Text(
            s.status_waiting, size=12,
            color=severity_color(self._state.theme, "ok"),
        )
        self.progress_bar  = self.register_progress(ft.ProgressBar(
            value=0.0,
            color=hex_to_flet(self._state.theme.progress_color),
            bgcolor=hex_to_flet(self._state.theme.border_color),
            visible=False,
        ))

        self.yt_api_input          = self.register_accents(ft.TextField(label=s.url_yt_api,          border_radius=8, focused_border_color=ft.Colors.BLUE))
        self.yt_download_input     = self.register_accents(ft.TextField(label=s.url_yt_download,     border_radius=8, focused_border_color=ft.Colors.BLUE))
        self.ffmpeg_version_input  = self.register_accents(ft.TextField(label=s.url_ffmpeg_version,  border_radius=8, focused_border_color=ft.Colors.BLUE))
        self.ffmpeg_download_input = self.register_accents(ft.TextField(label=s.url_ffmpeg_download, border_radius=8, focused_border_color=ft.Colors.BLUE))
        self.aria2_version_input   = self.register_accents(ft.TextField(label=s.url_aria2_version,   border_radius=8, focused_border_color=ft.Colors.BLUE))
        self.aria2_download_input  = self.register_accents(ft.TextField(label=s.url_aria2_download,  border_radius=8, focused_border_color=ft.Colors.BLUE))
        self.register_i18n(self.yt_api_input,          label="url_yt_api")
        self.register_i18n(self.yt_download_input,     label="url_yt_download")
        self.register_i18n(self.ffmpeg_version_input,  label="url_ffmpeg_version")
        self.register_i18n(self.ffmpeg_download_input, label="url_ffmpeg_download")
        self.register_i18n(self.aria2_version_input,   label="url_aria2_version")
        self.register_i18n(self.aria2_download_input,  label="url_aria2_download")
        # Ручная очистка временных .part-папок aria2c (см. _clean_temp).
        self.aria2_clean_btn = self.register_buttons(ft.Button(
            content=ft.Row([
                self.register_button_texts(ft.Icon(ft.Icons.CLEANING_SERVICES_OUTLINED, size=18)),
                self.register_i18n(
                    self.register_button_texts(ft.Text(s.btn_clean_temp)),
                    value="btn_clean_temp"),
            ], tight=True, spacing=8),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            on_click=self._clean_temp,
        ))

        self.update_btn_icon = self.register_button_texts(ft.Icon(ft.Icons.REFRESH_ROUNDED, color=ft.Colors.WHITE))
        self.update_btn_text = self.register_button_texts(ft.Text(s.btn_check, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD))
        self.update_btn = self.register_buttons(ft.Button(
            content=ft.Row([self.update_btn_icon, self.update_btn_text], tight=True, spacing=8),
            bgcolor=ft.Colors.GREEN,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=2),
            on_click=self._handle_update_button_click,
        ))

        # _urls-подзаголовки (серые) намеренно НЕ регистрируются как headers.
        self.header_net           = self.register_headers(ft.Text(s.section_network,     size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400))
        self.header_downloaders   = self.register_headers(ft.Text(s.section_downloaders, size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400))
        self.header_cookies       = self.register_headers(ft.Text(s.section_cookies,     size=13, weight=ft.FontWeight.W_600, color=ft.Colors.CYAN_400))
        self.header_ytdlp         = self.register_headers(ft.Text(s.section_ytdlp,       size=13, weight=ft.FontWeight.W_600, color=ft.Colors.CYAN_400))
        self.header_ytdlp_urls    = self.register_muted_text(ft.Text(s.section_ytdlp_urls,  size=12, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_400))
        self.header_aria2         = self.register_headers(ft.Text(s.section_aria2,       size=13, weight=ft.FontWeight.W_600, color=ft.Colors.CYAN_400))
        self.header_aria2_urls    = self.register_muted_text(ft.Text(s.section_aria2_urls,  size=12, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_400))
        self.header_deps          = self.register_headers(ft.Text(s.section_deps,        size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400))
        self.header_deps_urls     = self.register_muted_text(ft.Text(s.section_deps_urls,   size=12, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_400))
        self.header_history_set   = self.register_headers(ft.Text(s.section_history,     size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400))
        self.header_theme         = self.register_headers(ft.Text(s.section_theme,       size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400))
        self.header_modes         = self.register_headers(ft.Text(s.section_modes,       size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400))
        self.header_appearance    = self.register_headers(ft.Text(s.section_appearance, size=14, weight=ft.FontWeight.BOLD,  color=ft.Colors.CYAN_400))
        self.register_i18n(self.header_net,         value="section_network")
        self.register_i18n(self.header_downloaders, value="section_downloaders")
        self.register_i18n(self.header_cookies,     value="section_cookies")
        self.register_i18n(self.header_ytdlp,       value="section_ytdlp")
        self.register_i18n(self.header_ytdlp_urls,  value="section_ytdlp_urls")
        self.register_i18n(self.header_aria2,       value="section_aria2")
        self.register_i18n(self.header_aria2_urls,  value="section_aria2_urls")
        self.register_i18n(self.header_deps,        value="section_deps")
        self.register_i18n(self.header_deps_urls,   value="section_deps_urls")
        self.register_i18n(self.header_history_set, value="section_history")
        self.register_i18n(self.header_theme,       value="section_theme")
        self.register_i18n(self.header_modes,       value="section_modes")
        self.register_i18n(self.header_appearance,  value="section_appearance")

    # ── Куки UI ───────────────────────────────────────────────────────────────

    def _history_keep_options(self, s: Strings) -> list:
        """«Всегда» + стандартные сроки + текущее значение (если задано вручную)."""
        days = sorted({30, 90, 180, 365, self._state.history_keep_days} - {0})
        return [ft.dropdown.Option("0", s.history_keep_forever)] + [
            ft.dropdown.Option(str(d), s.fmt("history_keep_n_days", n=d)) for d in days
        ]

    def _on_history_keep_change(self, _) -> None:
        self.sync_to_state()
        # Применяем сразу: старые финальные записи удаляются, не дожидаясь рестарта.
        self._db.purge_older_than(self._state.history_keep_days)
        self._bus.emit(SettingsChangedEvent())
        self._safe_update()

    def _max_parallel_options(self) -> list:
        """1..10 + текущее значение из конфига (если задано больше вручную)."""
        values = sorted({*range(1, 11), self._state.max_parallel})
        return [ft.dropdown.Option(str(v)) for v in values]

    def _on_max_parallel_change(self, _) -> None:
        self.sync_to_state()
        self._bus.emit(SettingsChangedEvent())
        self._safe_update()

    def _on_browser_dropdown_change(self, _):
        self.sync_to_state()
        self._bus.emit(SettingsChangedEvent())
        self._bus.emit(CookiesChangedEvent())
        self._safe_update()

    def _on_language_change(self, _) -> None:
        self.sync_to_state()
        self._bus.emit(SettingsChangedEvent())
        self._bus.emit(LanguageChangedEvent())

    # ── Очистка временных папок aria2c ────────────────────────────────────────

    def _clean_temp(self, _) -> None:
        """Спросить подтверждение и удалить .part-папки (кроме активных загрузок)."""
        s = self._s

        def do_clean(_e) -> None:
            self._page.pop_dialog()
            removed, freed = Aria2cProvider.clean_temp_dirs(
                self._state.download_path, exclude=self._dm.active_temp_dirs(),
                part_dirname=self._state.aria2c.parameters.part_dirname)
            msg = (s.fmt("clean_temp_result", n=removed, size=_fmt_size(freed))
                   if removed else s.clean_temp_empty)
            self._page.show_dialog(ft.AlertDialog(
                modal=True, title=ft.Text(s.btn_clean_temp), content=ft.Text(msg),
                bgcolor=hex_to_flet(self._state.theme.card_color),
                actions=[ft.TextButton(s.btn_close, on_click=lambda e: self._page.pop_dialog())],
            ))
            self._safe_update()

        self._page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(s.btn_clean_temp),
            content=ft.Text(s.clean_temp_confirm),
            bgcolor=hex_to_flet(self._state.theme.card_color),
            actions=[
                ft.TextButton(s.btn_cancel,     on_click=lambda e: self._page.pop_dialog()),
                ft.TextButton(s.btn_clean_temp, on_click=do_clean),
            ],
        ))

    # ── Секция темы ───────────────────────────────────────────────────────────

    def _build_theme_section(self) -> None:
        s = self._s

        # Каждая строка цвета — самостоятельный ColorRow с явными ссылками на свои
        # виджеты. Храним плоский список строк — refresh работает по ссылкам,
        # без обхода дерева; переводы (метки групп/строк) идут через register_i18n.
        field_map = dict(THEME_FIELDS)   # {field_key: label_key}
        self._color_rows: list[ColorRow] = []
        group_columns = []
        for group_label_key, field_keys in THEME_GROUPS:
            group_label = self.register_i18n(self.register_muted_text(ft.Text(
                getattr(s, group_label_key, group_label_key),
                size=12, color=ft.Colors.GREY_500, weight=ft.FontWeight.W_500,
            )), value=group_label_key)
            divider = self.register_dividers(ft.Divider(height=1, color="#2a2a2a"))
            rows = []
            for k in field_keys:
                cr = ColorRow(self, self._state, self._bus, self._safe_update,
                              s, k, field_map[k])
                self._color_rows.append(cr)
                rows.append(cr.control)
            group_columns.append(ft.Column([group_label, divider, *rows], spacing=8))

        self.theme_fields_column = ft.Column(group_columns, spacing=18)
        self.theme_section = self.register_cards(ft.Container(
            content=ft.Column([
                ft.Row([
                    self.header_theme,
                    self.register_i18n(self.register_icon_buttons(ft.IconButton(
                        icon=ft.Icons.RESTART_ALT_ROUNDED, icon_color=ft.Colors.GREY_400,
                        icon_size=18, tooltip=s.btn_reset_theme,
                        on_click=self._reset_theme,
                    )), tooltip="btn_reset_theme"),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                self.register_i18n(self.register_muted_text(
                    ft.Text(s.theme_hint, size=11, color=ft.Colors.GREY_500)),
                    value="theme_hint"),
                self.theme_fields_column,
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15,
        ))

    # ── Секция «Тёмная/Светлая» + именованные наборы ─────────────────────────

    def _build_theme_sets_section(self) -> None:
        s = self._s

        self._mode_row = ft.Row(spacing=8)
        self._rebuild_mode_buttons()

        self.theme_set_dropdown = self.register_accents(ft.Dropdown(
            label=s.theme_saved_label, border_radius=8, width=220,
            focused_border_color=ft.Colors.BLUE, options=[],
        ))
        self.register_i18n(self.theme_set_dropdown, label="theme_saved_label")
        self._refresh_set_options()

        self._btn_set_apply = self.register_icon_buttons(ft.IconButton(
            icon=ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED, icon_size=20,
            tooltip=s.btn_theme_apply, on_click=self._apply_saved_theme,
        ))
        self._btn_set_delete = self.register_icon_buttons(ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE_ROUNDED, icon_size=20,
            tooltip=s.btn_theme_delete, on_click=self._delete_saved_theme,
        ))
        self.register_i18n(self._btn_set_apply,  tooltip="btn_theme_apply")
        self.register_i18n(self._btn_set_delete, tooltip="btn_theme_delete")
        self._btn_set_save = self.register_buttons(ft.Button(
            content=ft.Row([self.register_button_texts(ft.Icon(ft.Icons.SAVE_OUTLINED, size=18)),
                            self.register_i18n(
                                self.register_button_texts(ft.Text(s.btn_theme_save)),
                                value="btn_theme_save")], tight=True, spacing=8),
            on_click=self._open_save_dialog,
        ))

        self.theme_sets_section = self.register_cards(ft.Container(
            content=ft.Column([
                self.header_modes,
                self._mode_row,
                ft.Row([self.theme_set_dropdown, self._btn_set_apply, self._btn_set_delete],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                ft.Row([self._btn_set_save], alignment=ft.MainAxisAlignment.START),
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            border_radius=8, padding=15,
        ))

    def _rebuild_mode_buttons(self) -> None:
        s = self._s
        t = self._state.theme
        accent   = hex_to_flet(t.accent_color)
        on_acc   = hex_to_flet(t.button_text_color)
        inactive = hex_to_flet(t.text_secondary_color)
        border   = hex_to_flet(t.border_color)
        defs = [(s.theme_mode_dark, "dark"), (s.theme_mode_light, "light")]
        self._mode_row.controls = [
            ft.TextButton(
                content=ft.Text(
                    lbl, size=13,
                    color=on_acc if self._state.theme_mode == m else inactive,
                ),
                style=ft.ButtonStyle(
                    bgcolor=accent if self._state.theme_mode == m else ft.Colors.TRANSPARENT,
                    shape=ft.RoundedRectangleBorder(radius=8),
                    side=ft.BorderSide(1, border),
                    padding=ft.Padding.symmetric(horizontal=18, vertical=6),
                ),
                on_click=lambda _, mm=m: self._set_mode(mm),
            )
            for lbl, m in defs
        ]

    def _refresh_set_options(self) -> None:
        self.theme_set_dropdown.options = [
            ft.dropdown.Option(name) for name in sorted(self._state.saved_themes.keys())
        ]
        if self.theme_set_dropdown.value not in self._state.saved_themes:
            self.theme_set_dropdown.value = None

    def _set_mode(self, mode: str) -> None:
        if self._state.theme_mode == mode:
            return
        self._state.theme_mode = mode
        self._rebuild_mode_buttons()
        self.refresh_theme_fields()
        self._bus.emit(ThemeChangedEvent())
        self._bus.emit(SettingsChangedEvent())
        self._safe_update()

    def _apply_saved_theme(self, _) -> None:
        name = safe_str(self.theme_set_dropdown.value)
        nt = self._state.saved_themes.get(name)
        if nt is None:
            return
        new_cfg = ThemeConfig.from_dict(nt.config.to_dict())   # глубокая копия
        if nt.mode == "light":
            self._state.theme_light = new_cfg
        else:
            self._state.theme_dark = new_cfg
        self._state.theme_mode = nt.mode
        self._rebuild_mode_buttons()
        self.refresh_theme_fields()
        self._bus.emit(ThemeChangedEvent())
        self._bus.emit(SettingsChangedEvent())
        self._safe_update()

    def _delete_saved_theme(self, _) -> None:
        name = safe_str(self.theme_set_dropdown.value)
        if name in self._state.saved_themes:
            del self._state.saved_themes[name]
            self._refresh_set_options()
            self._bus.emit(SettingsChangedEvent())
            self._safe_update()

    def _open_save_dialog(self, _) -> None:
        s = self._s
        name_field = ft.TextField(
            label=s.theme_name_label, autofocus=True, border_radius=8, max_length=40,
        )

        def do_save(_e) -> None:
            name = safe_str(name_field.value).strip()
            if not name:
                name_field.border_color = hex_to_flet(self._state.theme.status_error_color)
                name_field.update()
                return
            self._state.saved_themes[name] = NamedTheme(
                mode=self._state.theme_mode,
                config=ThemeConfig.from_dict(self._state.theme.to_dict()),
            )
            self._refresh_set_options()
            self.theme_set_dropdown.value = name
            self._bus.emit(SettingsChangedEvent())
            self._page.pop_dialog()
            self._safe_update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(s.theme_save_dialog_title),
            content=name_field,
            bgcolor=hex_to_flet(self._state.theme.card_color),
            actions=[
                ft.TextButton(s.btn_cancel, on_click=lambda e: self._page.pop_dialog()),
                ft.TextButton(s.btn_ok, on_click=do_save),
            ],
        )
        self._page.show_dialog(dlg)

    def _reset_theme(self, _):
        defaults = ThemeConfig.dark_default() if self._state.theme_mode == "dark" \
            else ThemeConfig.light_default()
        for key in vars(defaults):
            setattr(self._state.theme, key, getattr(defaults, key))
        self.refresh_theme_fields()
        self._bus.emit(ThemeChangedEvent())
        self._bus.emit(SettingsChangedEvent())

    def refresh_theme_fields(self):
        for row in self._color_rows:
            row.refresh()

    # ── Смена языка — перезагрузка Strings и обновление всех текстов ──────────

    def rebuild_for_language(self) -> None:
        """Перезагрузить Strings; статичные тексты — по регистрации
        (apply_language), здесь только динамика. Отрисовку завершает общий
        safe_update() оркестратора в app.py."""
        self._s = Locale.load(self._state.language)
        s = self._s
        self.apply_language(s)

        # Пункты дропдаунов: тексты зависят от значений/реестров.
        self.history_keep_dropdown.options = self._history_keep_options(s)
        for opt, (_code, label_key) in zip(self.cookies_browser_dropdown.options,
                                           COOKIE_BROWSERS):
            opt.text = getattr(s, label_key)

        # Состояние-зависимые подписи.
        self._rebuild_mode_buttons()
        self.update_btn_text.value = s.btn_check
        self.progress_text.value   = s.status_waiting

    # ── Инструменты ───────────────────────────────────────────────────────────

    def reapply_restored(self) -> None:
        """Повторно показать восстановленное состояние версий (зовёт навигация
        при входе в настройки — промежуточные события могли его перетереть)."""
        if self._last_restored is not None:
            self._on_tools_restored(self._last_restored)

    def _on_tools_restored(self, e: ToolsRestoredEvent) -> None:
        self._last_restored = e
        s = self._s
        t = self._state.theme
        for name, widget in self._tool_status.items():
            info = e.versions.get(name)
            if info:
                widget.value = s.fmt("tool_versions",
                                     name=name,
                                     loc=_resolve_version(info.current, s),
                                     rem=_resolve_version(info.latest, s))
                self._color_tool(name, TOOL_STATUS_TOKENS.get(info.status, "text_muted_color"))
            else:
                widget.value = s.fmt("tool_dash", name=name)
                self._color_tool(name, "text_muted_color")

        if e.needs_update:
            self.update_btn_text.value = s.btn_update
            self.update_btn_icon.name  = ft.Icons.DOWNLOAD_ROUNDED
            self.progress_text.value   = s.fmt("status_has_updates", mins=e.mins_until_check)
            self._progress_severity    = "warning"
        else:
            self.update_btn_text.value = s.btn_check
            self.update_btn_icon.name  = ft.Icons.REFRESH_ROUNDED
            self.progress_text.value   = s.fmt("status_all_ok", mins=e.mins_until_check)
            self._progress_severity    = "ok"
        self.progress_text.color = severity_color(t, self._progress_severity)
        self._safe_update()

    # ── Обработчики событий шины (инструменты) ───────────────────────────────

    def _on_tool_local(self, e: ToolVersionLocalEvent) -> None:
        s = self._s
        widget = self._tool_widget(e.tool_name)
        if widget is None:
            return
        widget.value = s.fmt("tool_querying", name=e.tool_name, loc=_resolve_version(e.local_version, s))
        self._color_tool(e.tool_name, "text_muted_color")
        widget.update()

    def _on_tool_remote(self, e: ToolVersionRemoteEvent) -> None:
        s = self._s
        widget = self._tool_widget(e.tool_name)
        if widget is None:
            return
        widget.value = s.fmt("tool_versions", name=e.tool_name,
                             loc=_resolve_version(e.local_version, s),
                             rem=_resolve_version(e.remote_version, s))
        self._color_tool(e.tool_name, TOOL_STATUS_TOKENS.get(e.status, "text_muted_color"))
        widget.update()

    def _on_btn_state(self, e: ToolButtonStateEvent) -> None:
        s = self._s
        if e.mode == "check":
            self.update_btn.disabled   = False
            self.update_btn_icon.name  = ft.Icons.REFRESH_ROUNDED
            self.update_btn_text.value = s.btn_check
        elif e.mode == "update":
            self.update_btn.disabled   = False
            self.update_btn_icon.name  = ft.Icons.DOWNLOAD_ROUNDED
            self.update_btn_text.value = s.btn_update
        elif e.mode == "checking":
            self.update_btn.disabled   = True
            self.update_btn_text.value = s.btn_checking
        elif e.mode == "updating":
            self.update_btn.disabled   = True
            self.update_btn_icon.name  = ft.Icons.HOURGLASS_TOP_ROUNDED
            self.update_btn_text.value = s.btn_updating
        self.update_btn_text.update()
        self.update_btn_icon.update()
        self.update_btn.update()

    def _on_progress(self, e: ToolProgressEvent) -> None:
        self.progress_bar.visible = e.visible
        self.progress_bar.value   = e.pct
        self._safe_update()

    def _on_progress_msg(self, e: ToolProgressMessageEvent) -> None:
        s = self._s
        # Текст — перевод ключа; цвет — severity события через токены темы.
        msg_map = {
            "checking":    s.status_checking,
            "prep":        s.status_prep,
            "updates":     s.status_updates,
            "ok":          s.status_ok,
            "done_ok":     s.status_done_ok,
            "done_errors": s.status_done_errors,
        }
        if e.key in msg_map:
            text = msg_map[e.key]
        elif e.key.startswith("critical:"):
            text = s.fmt("status_critical", err=e.key[len("critical:"):])
        else:
            text = e.key
        self.progress_text.value = text
        self._progress_severity  = e.severity
        self.progress_text.color = severity_color(self._state.theme, e.severity)
        self._safe_update()

    def _on_install_status(self, e: ToolInstallStatusEvent) -> None:
        s = self._s
        widget = self._tool_widget(e.tool_name)
        if widget is None:
            return
        if e.code == "downloading":
            widget.value = f"{e.tool_name}: {s.tool_update_downloading}"
            severity = "warning"
        elif e.code == "ok":
            widget.value = f"{e.tool_name}: {s.tool_update_ok}"
            severity = "ok"
        elif e.code == "manual":
            widget.value = f"{e.tool_name}: {s.fmt('tool_update_manual', hint=e.detail)}"
            severity = "warning"
        else:
            widget.value = f"{e.tool_name}: {s.fmt('tool_update_error', detail=e.detail)}"
            severity = "error"
        self._color_tool(e.tool_name, SEVERITY_TOKENS[severity])
        self._safe_update()

    def _tool_widget(self, name: str) -> ft.Text | None:
        return self._tool_status.get(name)

    def _color_tool(self, name: str, token: str) -> None:
        """Запомнить токен цвета строки инструмента и применить его из активной темы."""
        self._tool_tokens[name] = token
        widget = self._tool_status.get(name)
        if widget is not None:
            widget.color = hex_to_flet(getattr(self._state.theme, token))

    # ── Обработчик кнопки — публикует намерение (маршрутизирует ToolsController) ──

    def _handle_update_button_click(self, _) -> None:
        self._bus.emit(ToolsActionRequestedEvent())

    # ── Лэйаут ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        # surface + border на одном контейнере — регистрации вкладываются.
        ytdlp_section = self.register_surfaces(self.register_borders(ft.Container(
            content=ft.Column([
                self.header_ytdlp,
                self.yt_args_input,
                ft.Column([
                    self.clean_titles_switch, self.playlist_switch,
                    self.embed_metadata_switch, self.save_to_source_switch,
                ], spacing=10),
                ft.ExpansionTile(
                    title=self.header_ytdlp_urls,
                    controls=[ft.Container(
                        content=ft.Column([
                            self.yt_api_input, self.yt_download_input,
                        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                        padding=ft.Padding.only(left=8, right=8, bottom=8),
                    )],
                ),
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#121212", border_radius=6, padding=12,
            border=ft.Border.all(1, "#2a2a2a"),
        )))

        # Именованный раздел aria2c — по образцу yt-dlp (заголовок + действие +
        # сворачиваемые URL). Версия/обновление инструмента — в карточке зависимостей.
        aria2_section = self.register_surfaces(self.register_borders(ft.Container(
            content=ft.Column([
                self.header_aria2,
                ft.Row([self.aria2_clean_btn], alignment=ft.MainAxisAlignment.START),
                ft.ExpansionTile(
                    title=self.header_aria2_urls,
                    controls=[ft.Container(
                        content=ft.Column([
                            self.aria2_version_input, self.aria2_download_input,
                        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                        padding=ft.Padding.only(left=8, right=8, bottom=8),
                    )],
                ),
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#121212", border_radius=6, padding=12,
            border=ft.Border.all(1, "#2a2a2a"),
        )))

        self._card_net = self.register_cards(ft.Container(
            content=ft.Column([
                self.header_net,
                self.proxy_input,
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15,
        ))
        self._card_downloaders = self.register_cards(ft.Container(
            content=ft.Column([
                self.header_downloaders,
                self.max_parallel_dropdown,
                self.header_cookies,
                self.cookies_browser_dropdown,
                ytdlp_section,
                aria2_section,
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15,
        ))
        self._card_deps = self.register_cards(ft.Container(
            content=ft.Column([
                self.header_deps,
                ft.Column(list(self._tool_status.values()), spacing=6),
                ft.Row([self.update_btn], alignment=ft.MainAxisAlignment.END),
                ft.ExpansionTile(
                    title=self.header_deps_urls,
                    controls=[ft.Container(
                        content=ft.Column([
                            self.ffmpeg_version_input, self.ffmpeg_download_input,
                        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                        padding=ft.Padding.only(left=8, right=8, bottom=8),
                    )],
                ),
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15,
        ))
        self._card_history = self.register_cards(ft.Container(
            content=ft.Column([
                self.header_history_set,
                self.history_keep_dropdown,
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15,
        ))
        self._card_appearance = self.register_cards(ft.Container(
            content=ft.Column([
                self.header_appearance,
                self.language_dropdown,
                self.notify_switch,
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15,
        ))

        self.layout = ft.Column([
            self._card_net,
            self._card_downloaders,
            self._card_deps,
            self._card_history,
            self.theme_sets_section,
            self.theme_section,
            self._card_appearance,
        ], visible=False, scroll=ft.ScrollMode.AUTO, expand=True, spacing=15,
           horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
