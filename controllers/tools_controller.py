"""
controllers/tools_controller.py — бизнес-логика проверки и обновления инструментов.

Ответственность:
  - check_tools()  : опрос локальных и удалённых версий
  - _update_tools(): скачивание/установка yt-dlp и ffmpeg

Результаты операций передаются через EventBus — контроллер не знает об UI.
"""

from __future__ import annotations

from typing import Literal

import flet as ft

from events import (
    ToolsCheckedEvent,
    ToolVersionLocalEvent, ToolVersionRemoteEvent,
    ToolButtonStateEvent,
    ToolProgressEvent, ToolProgressMessageEvent,
    ToolInstallStatusEvent,
)
from state import ToolVersionInfo
from managers.tools_manager import (
    TOOL_VERSION_MISSING, TOOL_VERSION_CALL_ERROR,
    TOOL_VERSION_REMOTE_ERR, TOOL_VERSION_UNKNOWN,
)
from services import Services


class ToolsController:

    def __init__(self, svc: Services) -> None:
        self._tools    = svc.tools
        self._state    = svc.state
        self._bus      = svc.bus
        self._btn_mode: Literal["check", "update"] = "check"

    @property
    def btn_mode(self) -> Literal["check", "update"]:
        return self._btn_mode

    async def handle_button_click(self) -> None:
        """Роутер клика по кнопке Check/Update.
        Игнорирует повторный клик пока предыдущая операция не завершена."""
        if self._tools.is_checking:
            return
        if self._btn_mode == "update":
            await self._update_tools()
        else:
            self._bus.emit(ToolButtonStateEvent("checking"))
            await self.check_tools()

    async def check_tools(self) -> None:
        """Проверить локальные и удалённые версии инструментов."""
        self._bus.emit(ToolProgressMessageEvent("checking", ft.Colors.GREEN_400))

        def on_local_version(name: str, local: str) -> None:
            self._bus.emit(ToolVersionLocalEvent(name, local))

        def on_remote_done(name: str, loc: str, rem: str) -> None:
            status = _classify_version(loc, rem)
            self._state.tool_versions[name] = ToolVersionInfo(current=loc, latest=rem, status=status)
            self._bus.emit(ToolVersionRemoteEvent(name, loc, rem, status))

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
            self._bus.emit(ToolButtonStateEvent("update"))
            self._bus.emit(ToolProgressMessageEvent("updates", ft.Colors.ORANGE_400))
        else:
            self._btn_mode = "check"
            self._bus.emit(ToolButtonStateEvent("check"))
            self._bus.emit(ToolProgressMessageEvent("ok", ft.Colors.GREEN_400))

        self._bus.emit(ToolsCheckedEvent(needs_update=needs))

    # ── Внутренняя логика обновления ──────────────────────────────────────────

    async def _update_tools(self) -> None:
        """Скачать и установить yt-dlp и/или ffmpeg."""
        self._bus.emit(ToolButtonStateEvent("updating"))
        self._bus.emit(ToolProgressEvent(0.0, True))
        self._bus.emit(ToolProgressMessageEvent("prep", ft.Colors.GREEN_400))

        proxy_url = self._state.proxy_address.strip() if self._state.proxy_enabled else None

        def on_yt_status(code: str, detail: str) -> None:
            self._bus.emit(ToolInstallStatusEvent("yt-dlp", code, detail))

        def on_ff_status(code: str, detail: str) -> None:
            self._bus.emit(ToolInstallStatusEvent("ffmpeg", code, detail))

        def on_progress(pct: float | None) -> None:
            self._bus.emit(ToolProgressEvent(pct, True))

        had_errors_container: list[bool] = [False]
        critical_err_container: list[str] = [""]

        def on_done(had_errors: bool, critical_err: str = "") -> None:
            had_errors_container[0]   = had_errors
            critical_err_container[0] = critical_err
            self._bus.emit(ToolProgressEvent(None, False))
            if critical_err:
                self._bus.emit(ToolProgressMessageEvent(f"critical:{critical_err}", ft.Colors.RED_400))
            elif had_errors:
                self._bus.emit(ToolProgressMessageEvent("done_errors", ft.Colors.RED_400))
            else:
                self._bus.emit(ToolProgressMessageEvent("done_ok", ft.Colors.GREEN_400))
            self._btn_mode = "check"
            self._bus.emit(ToolButtonStateEvent("check"))

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
    """Определить статус версии инструмента по двум строкам."""
    if loc == TOOL_VERSION_MISSING:
        return "missing"
    if loc == TOOL_VERSION_CALL_ERROR or rem in (TOOL_VERSION_REMOTE_ERR, TOOL_VERSION_UNKNOWN):
        return "error"
    if loc == rem or rem in loc or loc in rem:
        return "ok"
    return "outdated"
