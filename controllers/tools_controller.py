"""
controllers/tools_controller.py — бизнес-логика проверки и обновления инструментов.

Ответственность:
  - check_tools()   : опрос локальных и удалённых версий, обновление кнопки/прогресса
  - update_tools()  : скачивание/установка yt-dlp и ffmpeg, обновление прогресса
  - _btn_mode       : явное состояние кнопки (не по тексту)

SettingsScreen предоставляет коллбэки для обновления конкретных виджетов;
сам экран не содержит ни одной строки бизнес-логики инструментов.
"""

from __future__ import annotations

from typing import Callable, Literal

import flet as ft

from events import ToolsCheckedEvent
from managers.tools_manager import (
    TOOL_VERSION_MISSING, TOOL_VERSION_CALL_ERROR,
    TOOL_VERSION_REMOTE_ERR, TOOL_VERSION_UNKNOWN,
)
from services import Services


class ToolsController:

    def __init__(self, svc: Services) -> None:
        self._tools       = svc.tools
        self._state       = svc.state
        self._bus         = svc.bus

        # Явное состояние кнопки — не опираемся на локализованный текст
        self._btn_mode: Literal["check", "update"] = "check"

        # Коллбэки, которые SettingsScreen регистрирует при построении
        self._on_tool_local:   Callable[[str, str], None]             = lambda n, v: None
        self._on_tool_remote:  Callable[[str, str, str, str], None]   = lambda n, l, r, s: None
        self._on_btn_state:    Callable[[str], None]                   = lambda mode: None
        self._on_progress_pct: Callable[[float | None], None]         = lambda p: None
        self._on_progress_bar_visible: Callable[[bool], None]         = lambda v: None
        self._on_progress_msg: Callable[[str, str], None]             = lambda msg, color: None
        self._on_yt_status:    Callable[[str, str], None]             = lambda code, detail: None
        self._on_ff_status:    Callable[[str, str], None]             = lambda code, detail: None

    # ── Регистрация коллбэков из SettingsScreen ───────────────────────────────

    def set_on_tool_local(self,          cb: Callable[[str, str], None])           -> None: self._on_tool_local          = cb
    def set_on_tool_remote(self,         cb: Callable[[str, str, str, str], None]) -> None: self._on_tool_remote         = cb
    def set_on_btn_state(self,           cb: Callable[[str], None])                -> None: self._on_btn_state           = cb
    def set_on_progress_pct(self,        cb: Callable[[float | None], None])       -> None: self._on_progress_pct        = cb
    def set_on_progress_bar_visible(self,cb: Callable[[bool], None])               -> None: self._on_progress_bar_visible= cb
    def set_on_progress_msg(self,        cb: Callable[[str, str], None])           -> None: self._on_progress_msg        = cb
    def set_on_yt_status(self,           cb: Callable[[str, str], None])           -> None: self._on_yt_status           = cb
    def set_on_ff_status(self,           cb: Callable[[str, str], None])           -> None: self._on_ff_status           = cb

    # ── Публичный API для SettingsScreen ──────────────────────────────────────

    @property
    def btn_mode(self) -> Literal["check", "update"]:
        return self._btn_mode

    async def handle_button_click(self) -> None:
        """Роутер клика по кнопке Check/Update."""
        if self._btn_mode == "update":
            await self._update_tools()
        else:
            self._on_btn_state("checking")
            await self.check_tools()

    async def check_tools(self) -> None:
        """Проверить локальные и удалённые версии инструментов."""
        self._on_progress_msg("checking", ft.Colors.GREEN_400)

        def on_local_version(name: str, local: str) -> None:
            self._on_tool_local(name, local)

        def on_remote_done(name: str, loc: str, rem: str) -> None:
            status = _classify_version(loc, rem)
            self._state.tool_versions[name] = (loc, rem, status)
            self._on_tool_remote(name, loc, rem, status)

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
            self._btn_mode = "update"
            self._on_btn_state("update")
            self._on_progress_msg("updates", ft.Colors.ORANGE_400)
        else:
            self._btn_mode = "check"
            self._on_btn_state("check")
            self._on_progress_msg("ok", ft.Colors.GREEN_400)

        self._bus.emit(ToolsCheckedEvent(needs_update=needs))

    # ── Внутренняя логика обновления ──────────────────────────────────────────

    async def _update_tools(self) -> None:
        """Скачать и установить yt-dlp и/или ffmpeg."""
        self._on_btn_state("updating")
        self._on_progress_bar_visible(True)
        self._on_progress_pct(0.0)
        self._on_progress_msg("prep", ft.Colors.GREEN_400)

        proxy_url = self._state.proxy_address.strip() if self._state.proxy_enabled else None

        def on_yt_status(code: str, detail: str) -> None:
            self._on_yt_status(code, detail)

        def on_ff_status(code: str, detail: str) -> None:
            self._on_ff_status(code, detail)

        def on_progress(pct: float | None) -> None:
            self._on_progress_pct(pct)

        had_errors_container: list[bool] = [False]
        critical_err_container: list[str] = [""]

        def on_done(had_errors: bool, critical_err: str = "") -> None:
            had_errors_container[0]  = had_errors
            critical_err_container[0] = critical_err
            self._on_progress_bar_visible(False)
            if critical_err:
                self._on_progress_msg(f"critical:{critical_err}", ft.Colors.RED_400)
            elif had_errors:
                self._on_progress_msg("done_errors", ft.Colors.RED_400)
            else:
                self._on_progress_msg("done_ok", ft.Colors.GREEN_400)
            self._btn_mode = "check"
            self._on_btn_state("check")

        await self._tools.update_all(
            proxy_url=proxy_url,
            yt_download_url=self._state.url_yt_download,
            ffmpeg_download_url=self._state.url_ffmpeg_download,
            on_yt_status=on_yt_status,
            on_ff_status=on_ff_status,
            on_progress=on_progress,
            on_done=on_done,
        )

        if not had_errors_container[0] and not critical_err_container[0]:
            await self.check_tools()


# ── Вспомогательная функция ────────────────────────────────────────────────────

def _classify_version(loc: str, rem: str) -> str:
    """Определить статус версии инструмента по двум строкам.
    Использует sentinel-константы из tools_manager — не строковый поиск."""
    if loc == TOOL_VERSION_MISSING:
        return "missing"
    if loc == TOOL_VERSION_CALL_ERROR or rem in (TOOL_VERSION_REMOTE_ERR, TOOL_VERSION_UNKNOWN):
        return "error"
    if loc == rem or rem in loc or loc in rem:
        return "ok"
    return "outdated"
