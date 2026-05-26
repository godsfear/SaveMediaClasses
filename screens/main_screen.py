import asyncio
import os
import subprocess
import sys

import flet as ft

from config import safe_str, hex_to_flet
from managers.downloader import Downloader
from state import AppState

MAX_PARALLEL = 5
_POST_PROCESSING_TAGS = ["[Merger]", "[Metadata]", "[Thumbnails]", "[ExtractAudio]", "[Modify]"]


class DownloadCard:
    """
    Карточка одной загрузки: статус, прогресс-бар с процентом, кнопка отмены.
    Создаётся при каждом нажатии «Скачать», удаляется через 3с после завершения.
    """

    def __init__(self, url: str, on_cancel) -> None:
        self.url        = url
        self.downloader = None  # назначается из MainScreen
        self.cancelled  = False

        self._pct_text = ft.Text("0%", size=11, color=ft.Colors.GREY_400, width=36, text_align=ft.TextAlign.RIGHT)
        self._bar      = ft.ProgressBar(value=0.0, color=ft.Colors.GREEN,
                                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, expand=True)
        self._status   = ft.Text(self._short_url(url), size=11, color=ft.Colors.GREY_300,
                                 expand=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)
        self._cancel_btn = ft.IconButton(
            icon=ft.Icons.CLOSE_ROUNDED, icon_color=ft.Colors.RED_300,
            icon_size=16, tooltip="Отменить", on_click=on_cancel
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
    def _short_url(url: str) -> str:
        return url if len(url) <= 60 else url[:57] + "..."

    def set_progress(self, pct: float, status: str) -> None:
        self._bar.value    = pct
        self._bar.color    = ft.Colors.GREEN
        self._pct_text.value = f"{int(pct * 100)}%"
        self._status.value = status

    def set_postprocessing(self) -> None:
        self._bar.value    = None
        self._bar.color    = ft.Colors.BLUE_400
        self._pct_text.value = "..."
        self._status.value = "Постобработка..."

    def set_done(self, success: bool, message: str) -> None:
        self._bar.value      = 1.0 if success else 0.0
        self._bar.color      = ft.Colors.GREEN if success else ft.Colors.RED_400
        self._pct_text.value = "100%" if success else "✗"
        self._status.value   = message
        self._cancel_btn.visible = False

    def set_cancelled(self) -> None:
        self._bar.value      = 0.0
        self._bar.color      = ft.Colors.ORANGE
        self._pct_text.value = "—"
        self._status.value   = "Отменено"
        self._cancel_btn.visible = False


class MainScreen:

    def __init__(self, page: ft.Page, base_dir: str, tools_dir: str,
                 safe_update, state: AppState) -> None:
        self._page        = page
        self._base_dir    = base_dir
        self._tools_dir   = tools_dir
        self._safe_update = safe_update
        self._state       = state          # единственный источник истины

        # Колбэк уведомления статус-бара — назначается из App
        self._on_status: callable = lambda msg, color: None

        self._cards: list[DownloadCard] = []

        self._build_widgets()
        self._build_layout()

    # ── Виджеты ───────────────────────────────────────────────────────────────

    def _build_widgets(self) -> None:
        self.folder_label = ft.Text(
            "Папка не выбрана", color=ft.Colors.GREY_400, size=12, weight=ft.FontWeight.W_500,
            expand=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS
        )

        self.url_input = ft.TextField(
            label="URL медиафайла или плейлиста",
            hint_text="Вставьте ссылку для скачивания...",
            expand=True,
            border_radius=8,
            focused_border_color=ft.Colors.BLUE,
            on_change=self._on_url_change,
            suffix=ft.IconButton(
                icon=ft.Icons.CANCEL_ROUNDED,
                icon_color=ft.Colors.GREY_500,
                icon_size=18,
                tooltip="Очистить",
                on_click=lambda _: [
                    setattr(self.url_input, "value", ""),
                    self._on_url_change(None),
                    self._page.update()
                ]
            )
        )

        self.audio_only_switch      = ft.Switch(label="Только аудио (MP3)", active_color=ft.Colors.GREEN)
        self.cookies_enabled_switch = ft.Switch(label="Использовать куки", active_color=ft.Colors.GREEN, value=False)

        self._btn_icon = ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, color=ft.Colors.WHITE)
        self._btn_text = ft.Text("Скачать", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
        self.download_btn = ft.Button(
            content=ft.Row([self._btn_icon, self._btn_text], tight=True, spacing=8),
            bgcolor=ft.Colors.GREEN,
            tooltip="Начать загрузку",
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0),
            on_click=self._on_download_click
        )

        self._cards_column = ft.Column(spacing=6)

        self.header_folder = ft.Text("Папка назначения",    size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self.header_main   = ft.Text("Управление загрузкой", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self.header_queue  = ft.Text("Очередь загрузок",    size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self._log_btn = ft.IconButton(
            icon=ft.Icons.RECEIPT_LONG_ROUNDED,
            icon_color=ft.Colors.GREY_500,
            icon_size=18,
            tooltip="Открыть лог",
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
            self.folder_card,
            self.main_card,
            self._queue_card,
        ], visible=True, expand=True, spacing=15,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO)

    # ── Синхронизация виджетов ← state ───────────────────────────────────────

    def sync_from_state(self) -> None:
        """Переносит значения из AppState в виджеты. Вызывается один раз при старте."""
        s = self._state
        self.audio_only_switch.value      = s.audio_only
        self.cookies_enabled_switch.value = s.cookies_enabled
        if s.download_path:
            self.folder_label.value = s.download_path
            self.folder_label.color = ft.Colors.GREEN_400

    def sync_to_state(self) -> None:
        """Переносит значения из виджетов в AppState. Вызывается перед сохранением."""
        self._state.audio_only      = bool(self.audio_only_switch.value)
        self._state.cookies_enabled = bool(self.cookies_enabled_switch.value)

    # ── Валидация ─────────────────────────────────────────────────────────────

    def _on_url_change(self, _) -> None:
        val = safe_str(self.url_input.value).strip()
        if not val:
            self.url_input.border_color = None
        elif Downloader.is_valid_url(val):
            self.url_input.border_color = ft.Colors.GREEN_400
        else:
            self.url_input.border_color = ft.Colors.RED_400
        self._safe_update()

    # ── Управление карточками ─────────────────────────────────────────────────

    def _add_card(self, card: DownloadCard) -> None:
        self._cards.append(card)
        self._cards_column.controls.append(card.container)
        self._update_download_btn()
        self._safe_update()

    def _remove_card(self, card: DownloadCard) -> None:
        if card in self._cards:
            self._cards.remove(card)
        if card.container in self._cards_column.controls:
            self._cards_column.controls.remove(card.container)
        self._update_download_btn()
        self._safe_update()

    def _update_download_btn(self) -> None:
        active = len(self._cards)
        if active >= MAX_PARALLEL:
            self.download_btn.disabled = True
            self.download_btn.tooltip  = f"Максимум {MAX_PARALLEL} загрузок одновременно"
        else:
            self.download_btn.disabled = False
            self.download_btn.tooltip  = "Начать загрузку"

    # ── Запуск загрузки ───────────────────────────────────────────────────────

    async def _on_download_click(self, _) -> None:
        url_str = safe_str(self.url_input.value).strip()

        if not url_str:
            self._notify("Ошибка: Ссылка для загрузки пуста!", ft.Colors.RED)
            return
        if not Downloader.is_valid_url(url_str):
            self._notify("Ошибка: Ссылка должна начинаться с http:// или https://", ft.Colors.RED)
            self.url_input.border_color = ft.Colors.RED_400
            self._safe_update()
            return

        dl = Downloader(self._base_dir, self._tools_dir)
        yt_dlp_exe = dl.resolve_yt_dlp()
        if not yt_dlp_exe:
            self._notify("yt-dlp не найден — перейдите в настройки и нажмите «Обновить скрипты»",
                         ft.Colors.ORANGE)
            return

        card = DownloadCard(url_str, on_cancel=lambda _, c=None: None)
        card.downloader = dl

        async def do_cancel(_):
            card.cancelled = True
            card.downloader.cancel()
            card.set_cancelled()
            self._safe_update()
            await asyncio.sleep(3)
            self._remove_card(card)

        card._cancel_btn.on_click = do_cancel

        self._add_card(card)

        self.url_input.value        = ""
        self.url_input.border_color = None
        self._safe_update()

        self._page.run_task(self._run_download, card, dl, yt_dlp_exe, url_str)

    async def _run_download(self, card: DownloadCard, dl: Downloader,
                            yt_dlp_exe: str, url_str: str) -> None:
        # Читаем параметры из state — без обращения к другим экранам
        self.sync_to_state()
        opts = self._state.download_opts()

        if opts["download_path"]:
            try:
                os.makedirs(opts["download_path"], exist_ok=True)
            except Exception:
                pass

        log_path = os.path.join(self._base_dir, "savemedia.log")
        cmd_args = dl.build_command(yt_dlp_exe=yt_dlp_exe, url=url_str, **opts)
        returncode_holder = [0]

        def on_line(line_text: str):
            if card.cancelled:
                return
            pct = Downloader.parse_progress(line_text)
            if pct is None:
                try:
                    with open(log_path, "a", encoding="utf-8") as lf:
                        lf.write(line_text + "\n")
                except Exception:
                    pass
            if pct is not None:
                status = line_text.replace("[download]", "").strip()
                card.set_progress(pct, status[:60] if len(status) > 60 else status)
            elif any(tag in line_text for tag in _POST_PROCESSING_TAGS):
                card.set_postprocessing()
            elif len(line_text) < 80:
                card._status.value = line_text[:60]
            self._page.update()

        def on_finish(rc: int):
            returncode_holder[0] = rc

        try:
            await dl.run(cmd_args, on_line, on_finish)
        except Exception as err:
            card.set_done(False, f"Ошибка ОС: {err}")
            self._safe_update()
            await asyncio.sleep(3)
            self._remove_card(card)
            return

        if card.cancelled:
            return

        if returncode_holder[0] == 0:
            card.set_done(True, "Загрузка завершена!")
        else:
            card.set_done(False, f"Ошибка (код {returncode_holder[0]})")

        self._safe_update()
        await asyncio.sleep(3)
        self._remove_card(card)

    # ── Утилиты ───────────────────────────────────────────────────────────────

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

    def _notify(self, message: str, color) -> None:
        self._on_status(message, color)

    def notify_tools_status(self, needs_update: bool) -> None:
        if needs_update:
            self._notify(
                "Доступны обновления скриптов — перейдите в настройки и нажмите «Обновить скрипты»",
                ft.Colors.ORANGE
            )
        else:
            self._notify("Все компоненты актуальны", ft.Colors.GREEN_400)
