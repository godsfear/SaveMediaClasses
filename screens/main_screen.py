import asyncio
import os

import flet as ft

from config import safe_str, hex_to_flet
from managers.downloader import Downloader


class MainScreen:
    """
    Главный экран: URL-поле, кнопка скачать/отмена, переключатели, прогресс, лог.
    """

    _POST_PROCESSING_TAGS = ["[Merger]", "[Metadata]", "[Thumbnails]", "[ExtractAudio]", "[Modify]"]

    def __init__(self, page: ft.Page, downloader: Downloader, safe_update, current_theme: dict) -> None:
        self._page          = page
        self._dl            = downloader
        self._safe_update   = safe_update
        self._current_theme = current_theme
        self._cancelled     = False  # флаг отмены (пункт 1)

        self._build_widgets()
        self._build_layout()

    # ── Виджеты ───────────────────────────────────────────────────────────────

    def _build_widgets(self) -> None:
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
                on_click=lambda _: [setattr(self.url_input, "value", ""), self._on_url_change(None), self._page.update()]
            )
        )

        self.audio_only_switch      = ft.Switch(label="Только аудио (MP3)", active_color=ft.Colors.GREEN)
        self.cookies_enabled_switch = ft.Switch(label="Использовать куки", active_color=ft.Colors.GREEN, value=False)

        # Кнопка меняется между «Скачать» и «Отмена» (пункт 1)
        self._btn_icon = ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, color=ft.Colors.WHITE)
        self._btn_text = ft.Text("Скачать", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
        self.download_btn = ft.Button(
            content=ft.Row([self._btn_icon, self._btn_text], tight=True, spacing=8),
            bgcolor=ft.Colors.GREEN,
            tooltip="Начать загрузку",
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0),
            on_click=self._on_download_or_cancel
        )

        self.main_progress_text = ft.Text("Ожидание ссылки для начала загрузки", size=13, color=ft.Colors.GREEN_400)
        self.main_progress_bar  = ft.ProgressBar(
            value=0.0, color=ft.Colors.GREEN,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, visible=False
        )

        self.log_box = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=2)

        self.copy_btn = ft.IconButton(
            icon=ft.Icons.COPY_ROUNDED,
            icon_color=ft.Colors.GREY_500,
            icon_size=16,
            tooltip="Копировать лог",
            on_click=self._copy_log_to_clipboard
        )

        self.log_container = ft.Container(
            content=self.log_box,
            bgcolor="#0d0d0d",
            border=ft.Border(
                top=ft.BorderSide(1, "#222222"), bottom=ft.BorderSide(1, "#222222"),
                left=ft.BorderSide(1, "#222222"), right=ft.BorderSide(1, "#222222")
            ),
            border_radius=8, padding=12, expand=True
        )

        self.folder_label = ft.Text("Папка не выбрана", color=ft.Colors.GREY_400, size=12, weight=ft.FontWeight.W_500)

        self.header_main = ft.Text("Управление загрузкой",     size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
        self.header_log  = ft.Text("Консольный лог терминала:", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)

    def _build_layout(self) -> None:
        self.main_card = ft.Container(
            content=ft.Column([
                self.header_main,
                ft.Row([self.url_input, self.download_btn],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                ft.Column([self.audio_only_switch, self.cookies_enabled_switch], spacing=10)
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#161616", border_radius=8, padding=15
        )

        self.layout = ft.Column([
            self.main_card,
            ft.Container(
                content=ft.Column([self.main_progress_text, self.main_progress_bar], spacing=4, tight=True),
                padding=ft.Padding(left=5, right=5)
            ),
            ft.Row([
                ft.Container(content=self.header_log, padding=ft.Padding(left=15, right=0, top=0, bottom=0)),
                self.copy_btn,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self.log_container
        ], visible=True, expand=True, spacing=15, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    # ── Обработчики ───────────────────────────────────────────────────────────

    def _on_url_change(self, _) -> None:
        """Валидация URL в реальном времени (пункт 5)."""
        val = safe_str(self.url_input.value).strip()
        if not val:
            self.url_input.border_color = None
        elif Downloader.is_valid_url(val):
            self.url_input.border_color = ft.Colors.GREEN_400
        else:
            self.url_input.border_color = ft.Colors.RED_400
        self._safe_update()

    async def _on_download_or_cancel(self, _) -> None:
        """Единый обработчик кнопки: запуск или отмена (пункт 1)."""
        if self._cancelled is False and not self.download_btn.disabled:
            # Кнопка в режиме «Скачать» — запускаем
            await self._start_media_download()
        else:
            # Кнопка в режиме «Отмена»
            self._cancelled = True
            self._dl.cancel()
            self.main_progress_text.value = "Отмена загрузки..."
            self.main_progress_text.color = ft.Colors.ORANGE
            self._safe_update()

    def _set_download_mode(self) -> None:
        """Переключает кнопку в режим «Скачать»."""
        self._btn_icon.name    = ft.Icons.DOWNLOAD_ROUNDED
        self._btn_text.value   = "Скачать"
        self.download_btn.bgcolor  = hex_to_flet(self._current_theme.get("button_color", "4CAF50"))
        self.download_btn.disabled = False
        self.download_btn.tooltip  = "Начать загрузку"

    def _set_cancel_mode(self) -> None:
        """Переключает кнопку в режим «Отмена»."""
        self._btn_icon.name    = ft.Icons.STOP_ROUNDED
        self._btn_text.value   = "Отмена"
        self.download_btn.bgcolor  = ft.Colors.RED_700
        self.download_btn.disabled = False
        self.download_btn.tooltip  = "Остановить загрузку"

    async def _copy_log_to_clipboard(self, _):
        lines = [c.value for c in self.log_box.controls if hasattr(c, "value") and c.value]
        await ft.Clipboard().set("\n".join(lines))
        self.copy_btn.icon       = ft.Icons.CHECK_ROUNDED
        self.copy_btn.icon_color = ft.Colors.GREEN_400
        self._safe_update()
        async def reset_icon():
            await asyncio.sleep(1.5)
            self.copy_btn.icon       = ft.Icons.COPY_ROUNDED
            self.copy_btn.icon_color = ft.Colors.GREY_500
            self._safe_update()
        self._page.run_task(reset_icon)

    async def _start_media_download(self) -> None:
        url_str = safe_str(self.url_input.value).strip()

        # Пункт 5: валидация URL перед запуском
        if not url_str:
            self.main_progress_text.value = "Ошибка: Ссылка для загрузки пуста!"
            self.main_progress_text.color = ft.Colors.RED
            self._safe_update()
            return
        if not Downloader.is_valid_url(url_str):
            self.main_progress_text.value = "Ошибка: Некорректная ссылка — должна начинаться с http:// или https://"
            self.main_progress_text.color = ft.Colors.RED
            self.url_input.border_color   = ft.Colors.RED_400
            self._safe_update()
            return

        yt_dlp_exe = self._dl.resolve_yt_dlp()
        if not yt_dlp_exe:
            self.main_progress_text.value = "yt-dlp не найден — перейдите в настройки и нажмите «Обновить скрипты»"
            self.main_progress_text.color = ft.Colors.ORANGE
            self._safe_update()
            return

        # Переключаем кнопку в режим «Отмена» (пункт 1)
        self._cancelled = False
        self._set_cancel_mode()
        self.main_progress_bar.visible = True
        self.main_progress_bar.value   = 0.0
        self.main_progress_bar.color   = ft.Colors.GREEN
        self.main_progress_text.value  = "Анализ источника и метаданных..."
        self.main_progress_text.color  = ft.Colors.GREEN_400
        self.log_box.controls.clear()
        self.url_input.border_color    = None
        self._safe_update()

        opts = self._get_download_opts()
        if opts["download_path"]:
            try:
                os.makedirs(opts["download_path"], exist_ok=True)
            except Exception:
                pass

        cmd_args = self._dl.build_command(yt_dlp_exe=yt_dlp_exe, url=url_str, **opts)

        returncode_holder = [0]

        def on_line(line_text: str):
            is_prog = line_text.startswith("[download]") and "%" in line_text
            if is_prog and len(self.log_box.controls) > 0 and getattr(self.log_box.controls[-1], "data", None) == "progress":
                self.log_box.controls[-1].value = line_text
            else:
                new_text = ft.Text(
                    line_text,
                    color="#00ff00" if "[download]" in line_text else "#cccccc",
                    font_family="monospace",
                    size=11
                )
                if is_prog: new_text.data = "progress"
                self.log_box.controls.append(new_text)
                if len(self.log_box.controls) > 200:
                    self.log_box.controls.pop(0)

            pct = Downloader.parse_progress(line_text)
            if pct is not None:
                self.main_progress_bar.value  = pct
                self.main_progress_bar.color  = ft.Colors.GREEN  # пункт 8
                self.main_progress_text.value = f"Загрузка: {line_text.replace('[download]', '').strip()}"
            else:
                if len(line_text) < 75:
                    self.main_progress_text.value = line_text
                # Пункт 8: синий цвет прогресс-бара при постобработке
                if any(tag in line_text for tag in self._POST_PROCESSING_TAGS):
                    self.main_progress_bar.value  = None
                    self.main_progress_bar.color  = ft.Colors.BLUE_400
                    self.main_progress_text.value = "Постобработка и сведение тяжелых потоков медиа..."

            self._page.update()
            self._page.run_task(self.log_box.scroll_to, offset=-1, duration=0)

        def on_finish(rc: int):
            returncode_holder[0] = rc

        try:
            await self._dl.run(cmd_args, on_line, on_finish)
            if self._cancelled:
                self.main_progress_text.value = "Загрузка отменена пользователем"
                self.main_progress_text.color = ft.Colors.ORANGE
                self.main_progress_bar.value  = 0.0
            elif returncode_holder[0] == 0:
                self.main_progress_text.value = "Процесс загрузки успешно завершен!"
                self.main_progress_text.color = ft.Colors.GREEN
                self.main_progress_bar.value  = 1.0
            else:
                self.main_progress_text.value = f"Процесс аварийно прерван (код ошибки {returncode_holder[0]})"
                self.main_progress_text.color = ft.Colors.RED
        except Exception as err:
            self.main_progress_text.value = f"Ошибка операционной системы: {str(err)}"
            self.main_progress_text.color = ft.Colors.RED

        self.main_progress_bar.visible = False
        self.main_progress_bar.color   = ft.Colors.GREEN  # сброс цвета (пункт 8)
        self._cancelled                = False
        self._set_download_mode()
        self._page.update()

    # ── Колбэки, назначаются из App ───────────────────────────────────────────

    def set_download_opts_provider(self, provider) -> None:
        self._get_download_opts = provider

    def notify_tools_status(self, needs_update: bool) -> None:
        """Показывает предупреждение если скрипты требуют обновления."""
        if needs_update:
            self.main_progress_text.value = (
                "Доступны обновления скриптов — "
                "перейдите в настройки и нажмите «Обновить скрипты»"
            )
            self.main_progress_text.color = ft.Colors.ORANGE
        else:
            if not self._cancelled and self._dl._sub_proc is None:
                self.main_progress_text.value = "Ожидание ссылки для начала загрузки"
                self.main_progress_text.color = ft.Colors.GREEN_400
        self._safe_update()
