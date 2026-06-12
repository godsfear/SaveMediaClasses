"""
ClipboardController — слежение за буфером обмена.

Ответственность:
  - Фоновый опрос буфера (page.clipboard), пока включён state.clipboard_watch.
  - Распознавание ссылок на загрузку (extract_download_urls) и публикация
    ClipboardUrlEvent — поле URL пополняет сам MainScreen по подписке.
  - Windows: перехват СКОПИРОВАННЫХ ФАЙЛОВ (Ctrl+C в проводнике кладёт
    CF_HDROP-список путей, а не текст — Flet его не видит). Пути фильтруются
    тем же валидатором, что и текст: проходят только .torrent/.metalink.

Не знает про экраны и виджеты (только page для доступа к буферу и шина).
Кнопка-тумблер живёт в тулбаре NavigationController и лишь меняет state —
контроллер перечитывает флаг на каждом цикле, отдельных сигналов не нужно.

Важно: при ВКЛЮЧЕНИИ слежения текущее содержимое буфера принимается за
базовую точку и не трогается — событие вызывают только НОВЫЕ копирования.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import flet as ft

from app_logging import get_logger
from config import CLIPBOARD_POLL_SECONDS, CLIPBOARD_MAX_CHARS, safe_str
from events import AppClosingEvent, ClipboardUrlEvent
from managers.providers import extract_download_urls

if TYPE_CHECKING:
    from services import Services

_CF_HDROP = 15   # стандартный формат буфера Windows: список скопированных файлов


def clipboard_file_paths() -> list[str]:
    """Пути файлов из буфера обмена (копирование в проводнике Windows).

    Читает CF_HDROP напрямую через WinAPI (ctypes): OpenClipboard →
    GetClipboardData → DragQueryFileW. На не-Windows и при любой ошибке
    (буфер занят другим процессом, нет файлов) — пустой список: опрос
    повторится на следующем тике.
    """
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    user32  = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    # restype/argtypes обязательны: на 64-битной Windows дефолтный c_int
    # обрезал бы HANDLE до 32 бит.
    user32.GetClipboardData.restype = ctypes.c_void_p
    shell32.DragQueryFileW.argtypes = [
        ctypes.c_void_p, wintypes.UINT, ctypes.c_wchar_p, wintypes.UINT,
    ]

    paths: list[str] = []
    try:
        if not user32.IsClipboardFormatAvailable(_CF_HDROP):
            return []
        if not user32.OpenClipboard(None):
            return []
        try:
            handle = user32.GetClipboardData(_CF_HDROP)
            if handle:
                count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
                for i in range(count):
                    length = shell32.DragQueryFileW(handle, i, None, 0)
                    buf = ctypes.create_unicode_buffer(length + 1)
                    shell32.DragQueryFileW(handle, i, buf, length + 1)
                    if buf.value:
                        paths.append(buf.value)
        finally:
            user32.CloseClipboard()
    except Exception:
        get_logger("app").debug("CF_HDROP clipboard read failed", exc_info=True)
        return []
    return paths


class ClipboardController:

    def __init__(self, page: ft.Page, svc: "Services") -> None:
        self._page    = page
        self._svc     = svc
        self._log     = get_logger("app")
        self._stopped = False
        svc.bus.on(AppClosingEvent, lambda _e: self._stop())

    def _stop(self) -> None:
        self._stopped = True

    async def run(self) -> None:
        """Цикл опроса; запускается один раз (page.run_task в app.py) и живёт
        до закрытия приложения. Выключенное слежение = холостые тики.

        Текст и скопированные файлы отслеживаются раздельно (своя базовая
        точка у каждого): копирование файла в проводнике не меняет текстовый
        буфер и наоборот."""
        last_text:   str | None = None
        last_files:  tuple      = ()
        was_enabled: bool       = False

        while not self._stopped:
            try:
                enabled = self._svc.state.clipboard_watch
                if enabled:
                    text  = safe_str(await self._page.clipboard.get())
                    files = tuple(clipboard_file_paths())
                    if not was_enabled:
                        # Только что включили: запомнить как базу, не обрабатывать.
                        last_text, last_files = text, files
                    else:
                        if files and files != last_files:
                            last_files = files
                            # Тот же валидатор, что и для текста: из скопированных
                            # файлов проходят только задания (.torrent/.metalink).
                            tasks = extract_download_urls("\n".join(files))
                            if tasks:
                                self._svc.bus.emit(ClipboardUrlEvent(urls=tuple(tasks)))
                        if text and text != last_text:
                            last_text = text
                            if len(text) <= CLIPBOARD_MAX_CHARS:
                                urls = extract_download_urls(text)
                                if urls:
                                    self._svc.bus.emit(ClipboardUrlEvent(urls=tuple(urls)))
                was_enabled = enabled
            except Exception:
                # Буфер бывает занят другим процессом / содержит не-текст —
                # это не ошибка приложения, просто пропускаем тик.
                self._log.debug("Clipboard poll failed", exc_info=True)
            await asyncio.sleep(CLIPBOARD_POLL_SECONDS)
