import asyncio
import os
import subprocess
import sys
from typing import Dict

import flet as ft

from config import safe_str
from events import (
    EventBus,
    DownloadProgressEvent,
    DownloadPostprocessingEvent,
    DownloadCompletedEvent,
    DownloadCancelledEvent,
    ToolsCheckedEvent,
    ToolsStatusMessageEvent,
)
from locale import Locale, Strings
from managers.download_manager import DownloadManager, DownloadSnapshot, MAX_PARALLEL
from services import Services
from managers.providers import YtDlpProvider as _DefaultProvider
from state import AppState


class DownloadCard:
    """Карточка одной загрузки. Только отрисовка — никакой логики."""

    def __init__(self, task_id: str, url: str, on_cancel, s: Strings) -> None:
        self.task_id   = task_id
        self._s        = s
        self._pct_text = ft.Text("0%", size=11, color=ft.Colors.GREY_400, width=36,
                                 text_align=ft.TextAlign.RIGHT)
        self._bar      = ft.ProgressBar(value=0.0, color=ft.Colors.GREEN,
                                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, expand=True)
        self._status   = ft.Text(self._short(url), size=11, color=ft.Colors.GREY_300,
                                 expand=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)
        self._cancel_btn = ft.IconButton(
            icon=ft.Icons.CLOSE_ROUNDED, icon_color=ft.Colors.RED_300,
            icon_size=16, tooltip=s.btn_clear, on_click=on_cancel
        )
        self.container = ft.Container(
            content=ft.Column([
                ft.Row([self._status, self._cancel_btn],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([self._bar, self._pct_text],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            ], spacing=4, tight=True),
            bgcolor="#1a1a1a",
            border=ft.Border.all(1, "#2a2a2a"),
            border_radius=6,
            padding=ft.Padding(left=10, right=4, top=8, bottom=8),
        )

    @staticmethod
    def _short(url: str) -> str:
        return url if len(url) <= 60 else url[:57] + "..."

    def set_progress(self, pct: float, status: str) -> None:
        self._bar.value      = pct
        self._bar.color      = ft.Colors.GREEN
        self._pct_text.value = f"{int(pct * 100)}%"
        self._status.value   = status

    def set_postprocessing(self) -> None:
        self._bar.value      = None
        self._bar.color      = ft.Colors.BLUE_400
        self._pct_text.value = "..."
        self._status.value   = self._s.status_postprocessing

    def set_done(self, success: bool, message: str) -> None:
        self._bar.value          = 1.0 if success else 0.0
        self._bar.color          = ft.Colors.GREEN if success else ft.Colors.RED_400
        self._pct_text.value     = "100%" if success else "✗"
        self._status.value       = message
        self._cancel_btn.visible = False

    def set_cancelled(self) -> None:
        self._bar.value          = 0.0
        self._bar.color          = ft.Colors.ORANGE
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


class MainScreen:

    def __init__(self, page: ft.Page, svc: Services) -> None:
        self._page        = page
        self._base_dir    = svc.base_dir
        self._tools_dir   = svc.tools_dir
        self._safe_update = svc.safe_update
        self._state       = svc.state
        self._dm          = svc.dm
        self._bus         = svc.bus
        self._db          = svc.db

        self._cards: Dict[str, DownloadCard] = {}

        self._subscribe()
        self._build_widgets()
        self._build_layout()

    def _s(self) -> Strings:
        return Locale.load(self._state.language)

    # ── Подписка на шину ──────────────────────────────────────────────────────

    def _subscribe(self) -> None:
        self._bus.on(DownloadProgressEvent,       self._on_progress)
        self._bus.on(DownloadPostprocessingEvent, self._on_postprocessing)
        self._bus.on(DownloadCompletedEvent,      self._on_completed)
        self._bus.on(DownloadCancelledEvent,      self._on_cancelled)
        self._bus.on(ToolsCheckedEvent,           self._on_tools_checked)
        self._bus.on(ToolsStatusMessageEvent,     self._on_tools_status_message)

    # ── Обработчики событий ───────────────────────────────────────────────────

    def _on_progress(self, e: DownloadProgressEvent) -> None:
        card = self._cards.get(e.task_id)
        if card:
            card.set_progress(e.pct, e.status)
            self._page.update()

    def _on_postprocessing(self, e: DownloadPostprocessingEvent) -> None:
        card = self._cards.get(e.task_id)
        if card:
            card.set_postprocessing()
            self._page.update()

    def _on_completed(self, e: DownloadCompletedEvent) -> None:
        card = self._cards.get(e.task_id)
        if card:
            card.set_done(e.success, e.message)
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

    def _on_tools_status_message(self, e: ToolsStatusMessageEvent) -> None:
        self._show_status(e.message, e.color)

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
        self.url_input = ft.TextField(
            label=s.url_label,
            hint_text=s.url_hint,
            expand=True, border_radius=8,
            focused_border_color=ft.Colors.BLUE,
            on_change=self._on_url_change,
            suffix=ft.IconButton(
                icon=ft.Icons.CANCEL_ROUNDED, icon_color=ft.Colors.GREY_500,
                icon_size=18, tooltip=s.btn_clear,
                on_click=lambda _: [
                    setattr(self.url_input, "value", ""),
                    self._on_url_change(None),
                    self._page.update()
                ]
            )
        )
        self.audio_only_switch      = ft.Switch(label=s.switch_audio_only, active_color=ft.Colors.GREEN)
        self.cookies_enabled_switch = ft.Switch(label=s.switch_cookies,    active_color=ft.Colors.GREEN, value=False)

        self._btn_icon = ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, color=ft.Colors.WHITE)
        self._btn_text = ft.Text(s.btn_download, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
        self.download_btn = ft.Button(
            content=ft.Row([self._btn_icon, self._btn_text], tight=True, spacing=8),
            bgcolor=ft.Colors.GREEN, tooltip=s.btn_download_tooltip,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0),
            on_click=self._on_download_click
        )

        self._cards_column = ft.Column(spacing=6)
        self.header_folder = ft.Text(s.header_folder,   size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self.header_main   = ft.Text(s.header_download, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self.header_queue  = ft.Text(s.header_queue,    size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self._log_btn = ft.IconButton(
            icon=ft.Icons.RECEIPT_LONG_ROUNDED, icon_color=ft.Colors.GREY_500,
            icon_size=18, tooltip=s.btn_open_log,
            on_click=lambda _: self._open_log(os.path.join(self._base_dir, "savemedia.log"))
        )

    def _build_layout(self) -> None:
        self.folder_card = ft.Container(
            content=ft.Column([
                self.header_folder,
                ft.Row([self.folder_label], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15
        )
        self.main_card = ft.Container(
            content=ft.Column([
                self.header_main,
                ft.Row([self.url_input, self.download_btn],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                ft.Column([self.audio_only_switch, self.cookies_enabled_switch], spacing=10)
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15
        )
        self._queue_card = ft.Container(
            content=ft.Column([
                ft.Row([self.header_queue, self._log_btn],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self._cards_column,
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15,
        )
        self.layout = ft.Column([
            self.folder_card, self.main_card, self._queue_card,
        ], visible=True, expand=True, spacing=15,
           horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
           scroll=ft.ScrollMode.AUTO)

    # ── Синхронизация ─────────────────────────────────────────────────────────

    def sync_from_state(self) -> None:
        s = self._state
        self.audio_only_switch.value      = s.audio_only
        self.cookies_enabled_switch.value = s.cookies_enabled
        if s.download_path:
            self.folder_label.value = s.download_path
            self.folder_label.color = ft.Colors.GREEN_400

    def sync_to_state(self) -> None:
        self._state.audio_only      = bool(self.audio_only_switch.value)
        self._state.cookies_enabled = bool(self.cookies_enabled_switch.value)

    # ── Смена языка ───────────────────────────────────────────────────────────

    def rebuild_for_language(self) -> None:
        s = self._s()
        self.header_folder.value  = s.header_folder;   self.header_folder.update()
        self.header_main.value    = s.header_download; self.header_main.update()
        self.header_queue.value   = s.header_queue;    self.header_queue.update()
        self.url_input.label      = s.url_label;       self.url_input.update()
        self.url_input.hint_text  = s.url_hint
        self.audio_only_switch.label      = s.switch_audio_only; self.audio_only_switch.update()
        self.cookies_enabled_switch.label = s.switch_cookies;    self.cookies_enabled_switch.update()
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
        elif _DefaultProvider.is_valid_url(val):
            self.url_input.border_color = ft.Colors.GREEN_400
        else:
            self.url_input.border_color = ft.Colors.RED_400
        self._safe_update()

    # ── Нажатие «Скачать» ────────────────────────────────────────────────────

    def _on_download_click(self, _) -> None:
        s   = self._s()
        url = safe_str(self.url_input.value).strip()

        if not url:
            self._show_status(s.err_url_empty, ft.Colors.RED)
            return
        if not _DefaultProvider.is_valid_url(url):
            self._show_status(s.err_url_invalid, ft.Colors.RED)
            self.url_input.border_color = ft.Colors.RED_400
            self._safe_update()
            return
        if self._dm.at_capacity:
            self._show_status(s.fmt("err_max_parallel", n=MAX_PARALLEL), ft.Colors.ORANGE)
            return

        self.sync_to_state()
        snapshot = DownloadSnapshot(
            url=url,
            download_path=self._state.download_path,
            proxy_enabled=self._state.proxy_enabled,
            proxy_address=self._state.proxy_address,
            cookies_enabled=self._state.cookies_enabled,
            cookies_browser=self._state.cookies_browser,
            playlist_enabled=self._state.playlist_enabled,
            embed_metadata=self._state.embed_metadata,
            audio_only=self._state.audio_only,
            yt_dlp_args=self._state.yt_dlp_args,
            clean_titles=self._state.clean_titles,
            save_to_source=self._state.save_to_source_folder,
        )

        task_id = self._dm.add(self._page, snapshot)
        if task_id is None:
            self._show_status(s.status_ytdlp_missing, ft.Colors.ORANGE)
            return

        self._add_card(task_id, url)
        self.url_input.value        = ""
        self.url_input.border_color = None
        self._update_download_btn()
        self._safe_update()
        self._page.run_task(self._fetch_and_show_thumbnail, task_id, url)

    # ── Карточки ──────────────────────────────────────────────────────────────

    def _add_card(self, task_id: str, url: str) -> None:
        card = DownloadCard(
            task_id=task_id, url=url,
            on_cancel=lambda _: self._dm.cancel(task_id),
            s=self._s(),
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
            provider = YtDlpProvider(self._base_dir, self._tools_dir)
            exe = provider.resolve_exe()
            if not exe:
                return
            thumb_data, meta = await provider.fetch_thumbnail(exe, url)
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
            pass

    def _show_status(self, message: str, color) -> None:
        self._bus.emit(ToolsStatusMessageEvent(message=message, color=color))

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
            pass
