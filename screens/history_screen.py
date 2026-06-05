"""
HistoryScreen — экран истории загрузок.

Pull-модель: данные читаются из БД при открытии экрана, не по подписке.
Фильтрация по статусу, статистика, теги из JSON-params.
"""

import datetime
import os
import subprocess
import sys
from typing import Optional

import flet as ft

from app_logging import get_logger
from config import hex_to_flet
from controllers.theme_target import ThemeTarget
from i18l import Locale, Strings
from managers.download_repository import DownloadRecord, DownloadRepository
from services import Services

_STATUS_COLOR = {
    "completed": ft.Colors.GREEN_400,
    "failed":    ft.Colors.RED_400,
    "cancelled": ft.Colors.ORANGE_400,
    "running":   ft.Colors.BLUE_400,
}
_STATUS_ICON = {
    "completed": ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED,
    "failed":    ft.Icons.ERROR_OUTLINE_ROUNDED,
    "cancelled": ft.Icons.CANCEL_OUTLINED,
    "running":   ft.Icons.DOWNLOADING_ROUNDED,
}


class HistoryScreen(ThemeTarget):

    def __init__(self, page: ft.Page, svc: Services) -> None:
        super().__init__()
        self._page           = page
        self._db             = svc.db
        self._state          = svc.state
        self._current_filter: Optional[str] = None

        self._build_widgets()
        self._build_layout()

    def _s(self) -> Strings:
        return Locale.load(self._state.language)

    # ── Виджеты ───────────────────────────────────────────────────────────────

    def _build_widgets(self) -> None:
        s = self._s()
        self.header = ft.Text(
            s.header_history, size=14,
            weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400
        )
        self._filter_row = ft.Row(spacing=6, wrap=True)
        self._stats_text = ft.Text("", size=12, color=ft.Colors.GREY_500)
        self._list       = ft.Column(spacing=6)
        self._empty      = ft.Text(
            s.history_empty, size=13, color=ft.Colors.GREY_600,
            text_align=ft.TextAlign.CENTER, visible=False
        )
        self._rebuild_filter_buttons()

    def _rebuild_filter_buttons(self) -> None:
        s = self._s()
        filters = [
            (s.filter_all,       None),
            (s.filter_completed, "completed"),
            (s.filter_failed,    "failed"),
            (s.filter_cancelled, "cancelled"),
        ]
        self._filter_row.controls = [
            ft.TextButton(
                content=ft.Text(
                    label,
                    color=ft.Colors.WHITE if self._current_filter == status
                          else ft.Colors.GREY_400,
                    size=13,
                ),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_700 if self._current_filter == status
                            else ft.Colors.TRANSPARENT,
                    shape=ft.RoundedRectangleBorder(radius=6),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                ),
                on_click=lambda _, st=status: self._set_filter(st),
            )
            for label, status in filters
        ]

    # ── Лэйаут ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        s = self._s()
        self._card_header = ft.Container(
            content=ft.Column([
                ft.Row([
                    self.header,
                    ft.IconButton(
                        icon=ft.Icons.REFRESH_ROUNDED,
                        icon_color=ft.Colors.GREY_500,
                        icon_size=18, tooltip=s.btn_refresh,
                        on_click=lambda _: self.refresh(),
                    ),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self._filter_row,
                self._stats_text,
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15,
        )
        self._card_list = ft.Container(
            content=ft.Column(
                [self._empty, self._list],
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            bgcolor="#161616", border_radius=8, padding=15, expand=True,
        )
        self.layout = ft.Column(
            [self._card_header, self._card_list],
            visible=False, expand=True, spacing=15,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        # ── Регистрация виджетов для ThemeTarget ──────────────────────────────
        self.register_headers(self.header)
        self.register_cards(self._card_header, self._card_list)

    def apply_theme(self, t) -> None:
        """Применить ThemeConfig к виджетам экрана."""
        super().apply_theme(t)

    # ── Публичный API ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        records = self._db.get_history(limit=200, status=self._current_filter)
        self._render_list(records)
        self._render_stats()
        self._page.update()

    def rebuild_for_language(self) -> None:
        s = self._s()
        self.header.value   = s.header_history;  self.header.update()
        self._empty.value   = s.history_empty;   self._empty.update()
        self._rebuild_filter_buttons()
        self._filter_row.update()
        self._render_stats()

    # ── Фильтр ────────────────────────────────────────────────────────────────

    def _set_filter(self, status: Optional[str]) -> None:
        self._current_filter = status
        self._rebuild_filter_buttons()
        self.refresh()

    # ── Рендер ────────────────────────────────────────────────────────────────

    def _render_list(self, records: list) -> None:
        self._list.controls.clear()
        if not records:
            self._empty.visible = True
            self._list.visible  = False
            return
        self._empty.visible = False
        self._list.visible  = True
        for rec in records:
            self._list.controls.append(self._make_card(rec))

    def _make_card(self, rec: DownloadRecord) -> ft.Container:
        s     = self._s()
        color = _STATUS_COLOR.get(rec.status, ft.Colors.GREY_400)
        icon  = _STATUS_ICON.get(rec.status,  ft.Icons.HELP_OUTLINE_ROUNDED)

        # Статус из локали
        status_labels = {
            "completed": s.status_completed,
            "failed":    s.status_failed,
            "cancelled": s.status_cancelled,
            "running":   s.status_running,
        }
        label = status_labels.get(rec.status, rec.status)

        started  = _fmt_ts(rec.started_at)
        duration = _fmt_duration(rec.started_at, rec.finished_at)

        # Метаданные из yt-dlp
        meta = rec.meta or {}
        rec_title     = meta.get("title") or meta.get("fulltitle") or ""
        rec_extractor = meta.get("extractor_key") or meta.get("extractor") or ""

        url_short = rec.url if len(rec.url) <= 58 else rec.url[:55] + "…"

        # Теги
        p    = rec.params
        tags = []
        if p.get("audio_only"):      tags.append(s.tag_mp3)
        if p.get("proxy_enabled"):   tags.append(s.tag_proxy)
        if p.get("cookies_enabled"): tags.append(s.tag_cookies)
        is_playlist = meta.get("_is_playlist") or meta.get("_type") == "playlist"
        if is_playlist: tags.append(s.tag_playlist)

        # Thumbnail
        import base64 as _b64
        thumb_data = getattr(rec, "thumbnail", None)
        if thumb_data:
            b64str = "data:image/jpeg;base64," + _b64.b64encode(thumb_data).decode()
            thumbnail_widget = ft.Container(
                width=96, height=54, border_radius=4,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=ft.Image(src=b64str, width=96, height=54, fit=ft.BoxFit.COVER),
            )
        else:
            thumbnail_widget = ft.Container(
                width=96, height=54, bgcolor="#252525", border_radius=4,
                content=ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED,
                                color=ft.Colors.GREY_800, size=24),
                alignment=ft.Alignment(0, 0),
            )

        # Папка загрузки
        base_folder    = rec.params.get("download_path") or ""
        save_to_source = rec.params.get("save_to_source", False)
        folder = os.path.join(base_folder, rec_extractor) \
            if save_to_source and rec_extractor and base_folder else base_folder

        # Кнопки
        btn_folder = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN_OUTLINED,
            icon_color=ft.Colors.GREY_500, icon_size=16,
            tooltip=s.btn_open_folder, disabled=not bool(folder),
            on_click=lambda _, f=folder: _open_folder(f),
        )
        btn_delete = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
            icon_color=ft.Colors.GREY_600, icon_size=16,
            tooltip=s.btn_delete_record,
            on_click=lambda _, tid=rec.task_id: self._delete_record(tid),
        )

        title_short = (rec_title[:60] + "…") if len(rec_title) > 62 else rec_title

        info_column = ft.Column([
            ft.Row([
                ft.Text(title_short or url_short, size=12, color=ft.Colors.WHITE,
                        weight=ft.FontWeight.W_500, expand=True, no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS),
                btn_folder, btn_delete,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
            ft.Text(url_short, size=11, color=ft.Colors.GREY_500,
                    no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS,
                    visible=bool(title_short)),
            ft.Row([
                *([ft.Container(
                    content=ft.Text(t, size=10, color=ft.Colors.GREY_400),
                    bgcolor="#252525", border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                ) for t in tags] if tags else []),
                ft.Row([
                    ft.Icon(icon, color=color, size=12),
                    ft.Text(label, size=11, color=color),
                    ft.Text(f"{started}{duration}", size=11, color=ft.Colors.GREY_600),
                ], spacing=4, tight=True),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
               vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
            ft.Text(rec.error_message, size=10, color=ft.Colors.RED_300,
                    visible=bool(rec.error_message),
            ) if rec.error_message else ft.Container(height=0),
        ], spacing=3, tight=True, expand=True)

        return ft.Container(
            content=ft.Row([thumbnail_widget, info_column],
                           spacing=10, vertical_alignment=ft.CrossAxisAlignment.START),
            bgcolor="#1a1a1a", border=ft.Border.all(1, "#2a2a2a"),
            border_radius=6, padding=ft.Padding(left=10, right=10, top=8, bottom=8),
        )

    def _delete_record(self, task_id: str) -> None:
        self._db.delete(task_id)
        self.refresh()

    def _render_stats(self) -> None:
        s  = self._s()
        st = self._db.get_stats()
        if not st or not st.get("total"):
            self._stats_text.value = ""
            return
        total = st.get("total", 0)
        ok    = int(st.get("completed") or 0)
        fail  = int(st.get("failed") or 0)
        avg   = st.get("avg_duration_sec")
        avg_s = s.fmt("stats_avg", n=int(avg)) if avg else ""
        self._stats_text.value = s.fmt("stats_text", total=total, ok=ok, fail=fail, avg=avg_s)


# ── Утилиты ───────────────────────────────────────────────────────────────────

def _open_folder(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        get_logger("app").exception("Failed to open download folder: %s", path)


def _fmt_ts(ts: Optional[float]) -> str:
    if not ts:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%d %b %Y  %H:%M")
    except Exception:
        return "—"


def _fmt_duration(started: Optional[float], finished: Optional[float]) -> str:
    if not started or not finished:
        return ""
    secs = int(finished - started)
    if secs < 1:
        return ""
    if secs < 60:
        return f"  •  {secs}с"
    return f"  •  {secs // 60}м {secs % 60}с"
