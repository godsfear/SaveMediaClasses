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
_STATUS_LABEL = {
    "completed": "Завершено",
    "failed":    "Ошибка",
    "cancelled": "Отменено",
    "running":   "Загружается",
}


class HistoryScreen:

    def __init__(self, page: ft.Page, svc: Services) -> None:
        self._page           = page
        self._db             = svc.db
        self._current_filter: Optional[str] = None  # None = все

        self._build_widgets()
        self._build_layout()

    # ── Виджеты ───────────────────────────────────────────────────────────────

    def _build_widgets(self) -> None:
        self.header = ft.Text(
            "История загрузок", size=14,
            weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400
        )
        self._filter_row = ft.Row(spacing=6, wrap=True)
        self._stats_text = ft.Text("", size=12, color=ft.Colors.GREY_500)
        self._list       = ft.Column(spacing=6)
        self._empty      = ft.Text(
            "Загрузок пока нет", size=13, color=ft.Colors.GREY_600,
            text_align=ft.TextAlign.CENTER, visible=False
        )
        self._rebuild_filter_buttons()

    def _rebuild_filter_buttons(self) -> None:
        filters = [
            ("Все",          None),
            ("Завершённые",  "completed"),
            ("Ошибки",       "failed"),
            ("Отменённые",   "cancelled"),
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
                on_click=lambda _, s=status: self._set_filter(s),
            )
            for label, status in filters
        ]

    # ── Лэйаут ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        self.layout = ft.Column(
            [
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            self.header,
                            ft.IconButton(
                                icon=ft.Icons.REFRESH_ROUNDED,
                                icon_color=ft.Colors.GREY_500,
                                icon_size=18, tooltip="Обновить",
                                on_click=lambda _: self.refresh(),
                            ),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        self._filter_row,
                        self._stats_text,
                    ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                    bgcolor="#161616", border_radius=8, padding=15,
                ),
                ft.Container(
                    content=ft.Column(
                        [self._empty, self._list],
                        expand=True,
                        scroll=ft.ScrollMode.AUTO,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    bgcolor="#161616", border_radius=8, padding=15, expand=True,
                ),
            ],
            visible=False, expand=True, spacing=15,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    # ── Публичный API ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Перечитать БД и перерисовать. Вызывается при открытии экрана."""
        records = self._db.get_history(limit=200, status=self._current_filter)
        self._render_list(records)
        self._render_stats()
        self._page.update()

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
        color = _STATUS_COLOR.get(rec.status, ft.Colors.GREY_400)
        icon  = _STATUS_ICON.get(rec.status,  ft.Icons.HELP_OUTLINE_ROUNDED)
        label = _STATUS_LABEL.get(rec.status, rec.status)

        started  = _fmt_ts(rec.started_at)
        duration = _fmt_duration(rec.started_at, rec.finished_at)

        # Теги из JSON-params — совместимы со старыми записями через .get()
        p    = rec.params
        tags = []
        if p.get("audio_only"):        tags.append("MP3")
        if p.get("proxy_enabled"):     tags.append("Прокси")
        if p.get("playlist_enabled"):  tags.append("Плейлист")
        if p.get("cookies_enabled"):   tags.append("Куки")

        url_short = rec.url if len(rec.url) <= 58 else rec.url[:55] + "…"

        # Thumbnail — BLOB из БД, отдаём в ft.Image через src_base64
        thumb_data = getattr(rec, "thumbnail", None)
        if thumb_data:
            thumbnail_widget = ft.Container(
                width=96, height=54,
                border_radius=4,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=ft.Image(
                    src=thumb_data,
                    width=96, height=54,
                    fit="cover",
                ),
            )
        else:
            thumbnail_widget = ft.Container(
                width=96, height=54,
                bgcolor="#252525",
                border_radius=4,
                content=ft.Icon(
                    ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED,
                    color=ft.Colors.GREY_800, size=24,
                ),
                alignment=ft.alignment.center,
            )

        # Папка загрузки из params
        folder = rec.params.get("download_path") or ""

        # Кнопки действий
        btn_folder = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN_OUTLINED,
            icon_color=ft.Colors.GREY_500,
            icon_size=16,
            tooltip="Открыть папку",
            disabled=not bool(folder),
            on_click=lambda _, f=folder: _open_folder(f),
        )
        btn_delete = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
            icon_color=ft.Colors.GREY_600,
            icon_size=16,
            tooltip="Удалить из истории",
            on_click=lambda _, tid=rec.task_id: self._delete_record(tid),
        )

        # Правая часть карточки — статус, URL, теги, ошибка, кнопки
        info_column = ft.Column([
            ft.Row([
                ft.Icon(icon, color=color, size=15),
                ft.Text(label, size=12, color=color, weight=ft.FontWeight.W_500),
                ft.Text(
                    f"{started}{duration}", size=11, color=ft.Colors.GREY_500,
                    expand=True, text_align=ft.TextAlign.RIGHT,
                ),
                btn_folder,
                btn_delete,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
            ft.Text(
                url_short, size=11, color=ft.Colors.GREY_300,
                no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS,
            ),
            ft.Row(
                [ft.Container(
                    content=ft.Text(t, size=10, color=ft.Colors.GREY_400),
                    bgcolor="#252525", border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                ) for t in tags],
                spacing=4, wrap=True,
            ) if tags else ft.Container(height=0),
            ft.Text(
                rec.error_message, size=10, color=ft.Colors.RED_300,
                visible=bool(rec.error_message),
            ) if rec.error_message else ft.Container(height=0),
        ], spacing=4, tight=True, expand=True)

        return ft.Container(
            content=ft.Row([
                thumbnail_widget,
                info_column,
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START),
            bgcolor="#1a1a1a",
            border=ft.Border.all(1, "#2a2a2a"),
            border_radius=6,
            padding=ft.Padding(left=10, right=10, top=8, bottom=8),
        )

    def _delete_record(self, task_id: str) -> None:
        self._db.delete(task_id)
        self.refresh()

    def _render_stats(self) -> None:
        s = self._db.get_stats()
        if not s or not s.get("total"):
            self._stats_text.value = ""
            return
        total = s.get("total", 0)
        ok    = int(s.get("completed") or 0)
        fail  = int(s.get("failed") or 0)
        avg   = s.get("avg_duration_sec")
        avg_s = f"  •  ср. {int(avg)}с" if avg else ""
        self._stats_text.value = f"Всего: {total}  •  ✓ {ok}  •  ✗ {fail}{avg_s}"


# ── Утилиты ───────────────────────────────────────────────────────────────────

def _open_folder(path: str) -> None:
    """Открыть папку в проводнике."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def _fmt_ts(ts: Optional[float]) -> str:
    if not ts:
        return "—"
    try:
        # %d - день месяца (01-31)
        # %b - сокращенное название месяца в текущей локали
        # %Y - год (4 цифры)
        # %H:%M - часы и минуты
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
