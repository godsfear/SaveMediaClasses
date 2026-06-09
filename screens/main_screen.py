import asyncio
import os
import subprocess
import sys
from typing import Dict

import flet as ft

from app_logging import get_logger
from config import safe_str, hex_to_flet, ThemeConfig, download_display_name
from controllers.theme_target import ThemeTarget
from events import (
    EventBus,
    DownloadProgressEvent,
    DownloadPostprocessingEvent,
    DownloadCompletedEvent,
    DownloadCancelledEvent,
    ToolsCheckedEvent,
    StatusMessageEvent,
    CookiesChangedEvent,
    SettingsChangedEvent,
    AppClosingEvent,
)
from i18l import Locale, Strings
from managers.download_manager import DownloadManager, DownloadSnapshot, MAX_PARALLEL
from services import Services
from managers.providers import YtDlpProvider, Aria2cProvider
from state import AppState

# Доступные загрузчики: ключ провайдера → класс (для is_valid_url и выпадающего списка).
# Ключи совпадают с ключами реестра провайдеров в Services.create / DownloadManager.
_PROVIDER_CLASSES = {
    "yt-dlp": YtDlpProvider,
    "aria2c": Aria2cProvider,
}


class DownloadCard:
    """Карточка одной загрузки. Только отрисовка — никакой логики.

    Цвета берутся из активной ThemeConfig; apply_theme() позволяет перекрасить
    живую карточку при смене темы/режима."""

    def __init__(self, task_id: str, title: str, on_cancel, s: Strings, t: ThemeConfig) -> None:
        self.task_id   = task_id
        self._s        = s
        self._t        = t
        self._pct_text = ft.Text("0%", size=11, color=hex_to_flet(t.text_secondary_color),
                                 width=36, text_align=ft.TextAlign.RIGHT)
        self._bar      = ft.ProgressBar(value=0.0, color=hex_to_flet(t.progress_color),
                                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, expand=True)
        # Имя загрузки — фиксированная строка (не затирается прогрессом).
        self._title    = ft.Text(self._short(title), size=12, weight=ft.FontWeight.W_500,
                                 color=hex_to_flet(t.text_color),
                                 expand=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)
        # Детали (скорость/ETA, «готово», «отменено») — отдельная строка под баром.
        self._status   = ft.Text("", size=11,
                                 color=hex_to_flet(t.text_secondary_color),
                                 no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)
        self._cancel_btn = ft.IconButton(
            icon=ft.Icons.CLOSE_ROUNDED, icon_color=hex_to_flet(t.status_error_color),
            icon_size=16, tooltip=s.btn_clear, on_click=on_cancel
        )
        self.container = ft.Container(
            content=ft.Column([
                ft.Row([self._title, self._cancel_btn],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([self._bar, self._pct_text],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                self._status,
            ], spacing=4, tight=True),
            bgcolor=hex_to_flet(t.surface_color),
            border=ft.Border.all(1, hex_to_flet(t.border_color)),
            border_radius=6,
            padding=ft.Padding(left=10, right=4, top=8, bottom=8),
        )

    @staticmethod
    def _short(url: str) -> str:
        return url if len(url) <= 60 else url[:57] + "..."

    def apply_theme(self, t: ThemeConfig) -> None:
        """Перекрасить статичные элементы карточки под новую тему."""
        self._t = t
        self.container.bgcolor = hex_to_flet(t.surface_color)
        self.container.border  = ft.Border.all(1, hex_to_flet(t.border_color))
        self._title.color      = hex_to_flet(t.text_color)
        self._status.color     = hex_to_flet(t.text_secondary_color)
        self._pct_text.color   = hex_to_flet(t.text_secondary_color)
        self._cancel_btn.icon_color = hex_to_flet(t.status_error_color)

    def set_progress(self, pct: float, status: str) -> None:
        self._bar.value      = pct
        self._bar.color      = hex_to_flet(self._t.progress_color)
        self._pct_text.value = f"{int(pct * 100)}%"
        self._status.value   = status

    def set_postprocessing(self) -> None:
        self._bar.value      = None
        self._bar.color      = hex_to_flet(self._t.status_running_color)
        self._pct_text.value = "..."
        self._status.value   = self._s.status_postprocessing

    def set_done(self, success: bool, message: str) -> None:
        self._bar.value          = 1.0 if success else 0.0
        self._bar.color          = hex_to_flet(
            self._t.status_ok_color if success else self._t.status_error_color)
        self._pct_text.value     = "100%" if success else "✗"
        self._status.value       = message
        self._cancel_btn.visible = False

    def set_cancelled(self) -> None:
        self._bar.value          = 0.0
        self._bar.color          = hex_to_flet(self._t.status_warning_color)
        self._pct_text.value     = "—"
        self._status.value       = self._s.status_cancelled
        self._cancel_btn.visible = False

    def set_thumbnail(self, data: bytes) -> None:
        import base64 as _b64
        b64str = "data:image/jpeg;base64," + _b64.b64encode(data).decode()
        img = ft.Container(
            width=96, height=54, border_radius=4,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Image(src=b64str, width=96, height=54, fit=ft.BoxFit.COVER),
        )
        inner = self.container.content
        self.container.content = ft.Row(
            [img, ft.Column(inner.controls, spacing=4, tight=True, expand=True)],
            spacing=10, vertical_alignment=ft.CrossAxisAlignment.START,
        )


class MainScreen(ThemeTarget):

    def __init__(self, page: ft.Page, svc: Services) -> None:
        super().__init__()
        self._page        = page
        self._paths       = svc.paths
        self._safe_update = svc.safe_update
        self._state       = svc.state
        self._dm          = svc.dm
        self._bus         = svc.bus
        self._db          = svc.db
        self._log         = get_logger("app")

        self._cards: Dict[str, DownloadCard] = {}

        self._subscribe()
        self._build_widgets()
        self._build_layout()

    def _s(self) -> Strings:
        return Locale.load(self._state.language)

    # ── Подписка на шину ──────────────────────────────────────────────────────

    def _subscribe(self) -> None:
        self._unsubs = [
            self._bus.on(DownloadProgressEvent,       self._on_progress),
            self._bus.on(DownloadPostprocessingEvent, self._on_postprocessing),
            self._bus.on(DownloadCompletedEvent,      self._on_completed),
            self._bus.on(DownloadCancelledEvent,      self._on_cancelled),
            self._bus.on(ToolsCheckedEvent,           self._on_tools_checked),
            self._bus.on(CookiesChangedEvent,         self._on_cookies_changed),
            self._bus.on(AppClosingEvent,             lambda e: self.dispose()),
        ]

    def dispose(self) -> None:
        """Отписаться от всех событий шины. Вызывать при пересоздании экрана."""
        for unsub in getattr(self, "_unsubs", []):
            unsub()

    # ── Обработчики событий ───────────────────────────────────────────────────

    def _on_progress(self, e: DownloadProgressEvent) -> None:
        card = self._cards.get(e.task_id)
        if card:
            card.set_progress(e.pct, e.status)
            self._safe_update()

    def _on_postprocessing(self, e: DownloadPostprocessingEvent) -> None:
        card = self._cards.get(e.task_id)
        if card:
            card.set_postprocessing()
            self._safe_update()

    def _on_completed(self, e: DownloadCompletedEvent) -> None:
        card = self._cards.get(e.task_id)
        if card:
            s = self._s()
            if e.success:
                msg = s.download_completed
            elif e.error_detail:
                msg = s.fmt("download_error_os", detail=e.error_detail)
            else:
                msg = s.fmt("download_error_code", code=e.error_code or 1)
            card.set_done(e.success, msg)
            self._safe_update()
            self._page.run_task(self._remove_card_after_delay, e.task_id)

    def _on_cancelled(self, e: DownloadCancelledEvent) -> None:
        card = self._cards.get(e.task_id)
        if card:
            card.set_cancelled()
            self._safe_update()
            self._page.run_task(self._remove_card_after_delay, e.task_id)

    def _on_tools_checked(self, e: ToolsCheckedEvent) -> None:
        s = self._s()
        if e.needs_update:
            self._show_status(s.status_tools_update, ft.Colors.ORANGE)
        else:
            self._show_status(s.status_tools_ok, ft.Colors.GREEN_400)

    def _on_cookies_changed(self, _e: CookiesChangedEvent) -> None:
        self.update_cookies_ui()
        self._safe_update()

    # ── Cookies-переключатель: состояние выводится из state ────────────────────

    # Ключ браузера → i18n-ключ его отображаемого имени (тот же набор, что в
    # выпадающем списке настроек). Экран сам резолвит имя, не обращаясь к Settings.
    _COOKIE_LABEL_KEYS = {
        "none":    "cookies_none",
        "chrome":  "cookies_chrome",
        "yandex":  "cookies_yandex",
        "firefox": "cookies_firefox",
        "edge":    "cookies_edge",
        "opera":   "cookies_opera",
    }

    def update_cookies_ui(self) -> None:
        """Привести переключатель cookies в соответствие с выбранным браузером.

        Источник истины — state (p.cookies.browser), а не виджет другого экрана.
        Вызывается при инициализации, по CookiesChangedEvent и при смене языка."""
        s       = self._s()
        browser = self._state.ytdlp.parameters.cookies.browser
        if not browser or browser == "none":
            self.cookies_enabled_switch.value    = False
            self.cookies_enabled_switch.disabled = True
            self.cookies_enabled_switch.label    = s.cookies_switch_off
        else:
            name_key     = self._COOKIE_LABEL_KEYS.get(browser)
            browser_name = getattr(s, name_key, browser) if name_key else browser
            self.cookies_enabled_switch.disabled = False
            self.cookies_enabled_switch.label    = s.cookies_switch_on.format(browser=browser_name)

    async def _remove_card_after_delay(self, task_id: str) -> None:
        await asyncio.sleep(3)
        self._remove_card(task_id)

    # ── Виджеты ───────────────────────────────────────────────────────────────

    def _build_widgets(self) -> None:
        s = self._s()
        self.folder_label = ft.Text(
            s.folder_not_selected, color=ft.Colors.GREY_400, size=12,
            weight=ft.FontWeight.W_500, expand=True,
            no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS
        )
        url_clear_btn = self.register_icon_buttons(ft.IconButton(
            icon=ft.Icons.CANCEL_ROUNDED, icon_color=ft.Colors.GREY_500,
            icon_size=18, tooltip=s.btn_clear,
            on_click=lambda _: [
                setattr(self.url_input, "value", ""),
                self._on_url_change(None),
            ]
        ))
        self.url_input = self.register_accents(ft.TextField(
            label=s.url_label,
            hint_text=s.url_hint,
            expand=True, border_radius=8,
            focused_border_color=ft.Colors.BLUE,
            on_change=self._on_url_change,
            suffix=url_clear_btn,
        ))
        # Выбор загрузчика для текущей ссылки: yt-dlp (медиа-сайты) или aria2c
        # (прямые файловые ссылки). Стоит справа от поля URL; выбор запоминается.
        self.downloader_dropdown = self.register_accents(ft.Dropdown(
            label=s.downloader_label,
            border_radius=8, width=130,
            focused_border_color=ft.Colors.BLUE,
            options=[ft.dropdown.Option(key) for key in _PROVIDER_CLASSES],
            value=self._state.download_tool,
            on_select=self._on_downloader_change,
        ))
        self.audio_only_switch      = self.register_switches(ft.Switch(label=s.switch_audio_only, active_color=ft.Colors.GREEN))
        self.cookies_enabled_switch = self.register_switches(ft.Switch(label=s.switch_cookies,    active_color=ft.Colors.GREEN, value=False))

        self._btn_icon = self.register_button_texts(ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, color=ft.Colors.WHITE))
        self._btn_text = self.register_button_texts(ft.Text(s.btn_download, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD))
        self.download_btn = self.register_buttons(ft.Button(
            content=ft.Row([self._btn_icon, self._btn_text], tight=True, spacing=8),
            bgcolor=ft.Colors.GREEN, tooltip=s.btn_download_tooltip,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0),
            on_click=self._on_download_click
        ))

        self._cards_column = ft.Column(spacing=6)
        self.header_folder = self.register_headers(ft.Text(s.header_folder,   size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400))
        self.header_main   = self.register_headers(ft.Text(s.header_download, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400))
        self.header_queue  = self.register_headers(ft.Text(s.header_queue,    size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400))
        self._log_btn = self.register_icon_buttons(ft.IconButton(
            icon=ft.Icons.RECEIPT_LONG_ROUNDED, icon_color=ft.Colors.GREY_500,
            icon_size=18, tooltip=s.btn_open_log,
            on_click=lambda _: self._open_log(str(self._paths.log_file))
        ))

    def _build_layout(self) -> None:
        self.folder_card = self.register_cards(ft.Container(
            content=ft.Column([
                self.header_folder,
                ft.Row([self.folder_label], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15
        ))
        self.main_card = self.register_cards(ft.Container(
            content=ft.Column([
                self.header_main,
                ft.Row([self.url_input, self.downloader_dropdown, self.download_btn],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                ft.Column([self.audio_only_switch, self.cookies_enabled_switch], spacing=10)
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15
        ))
        self._queue_card = self.register_cards(ft.Container(
            content=ft.Column([
                ft.Row([self.header_queue, self._log_btn],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self._cards_column,
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15,
        ))
        self.layout = ft.Column([
            self.folder_card, self.main_card, self._queue_card,
        ], visible=True, expand=True, spacing=15,
           horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
           scroll=ft.ScrollMode.AUTO)

    # ── Синхронизация ─────────────────────────────────────────────────────────

    def sync_from_state(self) -> None:
        s = self._state
        p = s.ytdlp.parameters
        self.audio_only_switch.value      = p.audio_only.state
        self.cookies_enabled_switch.value = p.cookies.state
        self.downloader_dropdown.value    = self._selected_tool()
        if s.download_path:
            self.folder_label.value = s.download_path
            self.folder_label.color = hex_to_flet(s.theme.status_ok_color)

    def sync_to_state(self) -> None:
        p = self._state.ytdlp.parameters
        p.audio_only.state = bool(self.audio_only_switch.value)
        p.cookies.state    = bool(self.cookies_enabled_switch.value)
        self._state.download_tool = self._selected_tool()

    # ── Выбор загрузчика ──────────────────────────────────────────────────────

    def _selected_tool(self) -> str:
        """Текущий ключ провайдера: значение дропдауна, иначе сохранённый в state.
        Неизвестный ключ откатывается к yt-dlp."""
        tool = safe_str(self.downloader_dropdown.value) or self._state.download_tool
        return tool if tool in _PROVIDER_CLASSES else "yt-dlp"

    def _selected_provider_cls(self):
        return _PROVIDER_CLASSES[self._selected_tool()]

    def _on_downloader_change(self, _) -> None:
        self.sync_to_state()
        self._on_url_change(None)          # перепроверить URL под новый загрузчик
        self._bus.emit(SettingsChangedEvent())

    # ── Тема ─────────────────────────────────────────────────────────────────

    def apply_theme(self, t) -> None:
        """Применить ThemeConfig к виджетам экрана и живым карточкам загрузок."""
        super().apply_theme(t)
        # folder_label: text_color если путь не выбран, иначе «успех» (статус ok)
        self.folder_label.color = (
            hex_to_flet(t.status_ok_color) if self._state.download_path
            else hex_to_flet(t.text_color)
        )
        for card in self._cards.values():
            card.apply_theme(t)

    # ── Смена языка ───────────────────────────────────────────────────────────

    def rebuild_for_language(self) -> None:
        s = self._s()
        self.header_folder.value  = s.header_folder;   self.header_folder.update()
        self.header_main.value    = s.header_download; self.header_main.update()
        self.header_queue.value   = s.header_queue;    self.header_queue.update()
        self.url_input.label      = s.url_label;       self.url_input.update()
        self.url_input.hint_text  = s.url_hint
        self.downloader_dropdown.label = s.downloader_label; self.downloader_dropdown.update()
        self.audio_only_switch.label      = s.switch_audio_only; self.audio_only_switch.update()
        self.update_cookies_ui();                                self.cookies_enabled_switch.update()
        self._btn_text.value      = s.btn_download;    self._btn_text.update()
        self.download_btn.tooltip = s.btn_download_tooltip
        if self.folder_label.value == self.folder_label.value:  # всегда обновляем если нет пути
            if not self._state.download_path:
                self.folder_label.value = s.folder_not_selected
                self.folder_label.update()

    # ── Валидация URL ─────────────────────────────────────────────────────────

    def _on_url_change(self, _) -> None:
        val = safe_str(self.url_input.value).strip()
        if not val:
            self.url_input.border_color = None
        elif self._selected_provider_cls().is_valid_url(val):
            self.url_input.border_color = ft.Colors.GREEN_400
        else:
            self.url_input.border_color = ft.Colors.RED_400
        self._safe_update()

    # ── Нажатие «Скачать» ────────────────────────────────────────────────────

    def _on_download_click(self, _) -> None:
        s    = self._s()
        url  = safe_str(self.url_input.value).strip()
        tool = self._selected_tool()

        if not url:
            self._show_status(s.err_url_empty, ft.Colors.RED)
            return
        if not _PROVIDER_CLASSES[tool].is_valid_url(url):
            self._show_status(s.err_url_invalid, ft.Colors.RED)
            self.url_input.border_color = ft.Colors.RED_400
            self._safe_update()
            return
        if self._dm.at_capacity:
            self._show_status(s.fmt("err_max_parallel", n=MAX_PARALLEL), ft.Colors.ORANGE)
            return

        self.sync_to_state()
        snapshot = DownloadSnapshot.from_state(self._state, url)

        task_id = self._dm.add(snapshot, provider_key=tool)
        if task_id is None:
            self._show_status(s.status_ytdlp_missing, ft.Colors.ORANGE)
            return

        self._add_card(task_id, url)
        self.url_input.value        = ""
        self.url_input.border_color = None
        self._update_download_btn()
        self._safe_update()
        # Превью/метаданные умеет получать только yt-dlp (по странице медиа).
        if tool == "yt-dlp":
            self._page.run_task(self._fetch_and_show_thumbnail, task_id, url)

    # ── Карточки ──────────────────────────────────────────────────────────────

    def _add_card(self, task_id: str, url: str) -> None:
        card = DownloadCard(
            task_id=task_id, title=download_display_name(url),
            on_cancel=lambda _: self._dm.cancel(task_id),
            s=self._s(), t=self._state.theme,
        )
        self._cards[task_id] = card
        self._cards_column.controls.append(card.container)

    def _remove_card(self, task_id: str) -> None:
        card = self._cards.pop(task_id, None)
        if card and card.container in self._cards_column.controls:
            self._cards_column.controls.remove(card.container)
        self._update_download_btn()
        self._safe_update()

    def _update_download_btn(self) -> None:
        s = self._s()
        if self._dm.at_capacity:
            self.download_btn.disabled = True
            self.download_btn.tooltip  = s.fmt("err_max_parallel", n=MAX_PARALLEL)
        else:
            self.download_btn.disabled = False
            self.download_btn.tooltip  = s.btn_download_tooltip

    # ── Утилиты ───────────────────────────────────────────────────────────────

    async def _fetch_and_show_thumbnail(self, task_id: str, url: str) -> None:
        try:
            from managers.providers import YtDlpProvider
            provider = YtDlpProvider(self._paths)
            exe = provider.resolve_exe()
            if not exe:
                return
            proxy_url = self._state.proxy_address.strip() if self._state.proxy_enabled else None
            thumb_data, meta = await provider.fetch_thumbnail(exe, url, proxy_url=proxy_url)
            if self._db is not None:
                if thumb_data:
                    self._db.save_thumbnail(task_id, thumb_data)
                if meta:
                    self._db.save_meta(task_id, meta)
            if thumb_data:
                card = self._cards.get(task_id)
                if card:
                    card.set_thumbnail(thumb_data)
                    self._safe_update()
        except Exception:
            self._log.warning("Failed to fetch thumbnail for %s", url, exc_info=True)

    def _show_status(self, message: str, color) -> None:
        self._bus.emit(StatusMessageEvent(message=message, color=color))

    @staticmethod
    def _open_log(path: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            get_logger("app").exception("Failed to open log file: %s", path)
