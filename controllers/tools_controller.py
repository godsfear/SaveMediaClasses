"""
controllers/tools_controller.py — оркестрация проверки и обновления инструментов.

Ответственность:
  - check_tools()  : запустить проверку версий по реестру инструментов
  - _update_tools(): запустить установку/обновление

Контроллер НЕ знает про конкретные инструменты (их список — в tool_registry)
и про UI (всё наружу — через EventBus).
Сравнение версий не дублируется: статус приходит готовым из движка.

Роль в слоях: это АДАПТЕР между bus-агностичным движком (ToolsManager, общается
колбэками-портом) и шиной приложения. Здесь колбэки on_local/on_remote/on_status/
on_progress/on_done транслируются в типизированные события (ToolVersionRemoteEvent,
ToolInstallStatusEvent и т.д.), на которые подписан UI. Подробнее о контракте и
конвенции по менеджерам — в docstring managers/tools_manager.py.
"""

from __future__ import annotations

from typing import Literal

import flet as ft

from config import VersionState
from events import (
    ToolsCheckedEvent,
    ToolVersionLocalEvent, ToolVersionRemoteEvent,
    ToolButtonStateEvent,
    ToolProgressEvent, ToolProgressMessageEvent,
    ToolInstallStatusEvent,
)
from managers.tool_registry import DEFAULT_TOOLS
from services import Services


class ToolsController:

    def __init__(self, svc: Services) -> None:
        self._tools = svc.tools
        self._state = svc.state
        self._bus   = svc.bus
        self._specs = DEFAULT_TOOLS
        self._btn_mode: Literal["check", "update"] = "check"

    @property
    def btn_mode(self) -> Literal["check", "update"]:
        return self._btn_mode

    async def handle_button_click(self) -> None:
        """Роутер клика по кнопке Check/Update. Игнорирует клик пока идёт операция."""
        if self._tools.is_checking:
            return
        if self._btn_mode == "update":
            await self._update_tools()
        else:
            await self.check_tools()

    async def check_tools(self) -> None:
        """Проверить локальные и удалённые версии всех инструментов из реестра."""
        if self._tools.is_checking:
            return

        self._bus.emit(ToolButtonStateEvent("checking"))
        self._bus.emit(ToolProgressMessageEvent("checking", ft.Colors.GREEN_400))

        def on_local(binary: str, local: str) -> None:
            self._bus.emit(ToolVersionLocalEvent(binary, local))

        def on_remote(binary: str, loc: str, rem: str, status: str) -> None:
            # Runtime-версии живут отдельно от конфига, ключ — имя бинарника.
            # Никакого разбора primary/secondary: структура единообразна.
            self._state.tool_versions[binary] = VersionState(
                current=loc, latest=rem, status=status
            )
            self._bus.emit(ToolVersionRemoteEvent(binary, loc, rem, status))

        proxy_url = self._proxy_url()
        await self._tools.check_all(
            self._specs, self._state, proxy_url,
            on_local_version=on_local,
            on_remote_done=on_remote,
        )

        needs = self._tools.needs_update
        if needs:
            self._btn_mode = "update"
            self._bus.emit(ToolButtonStateEvent("update"))
            self._bus.emit(ToolProgressMessageEvent("updates", ft.Colors.ORANGE_400))
        else:
            self._btn_mode = "check"
            self._bus.emit(ToolButtonStateEvent("check"))
            self._bus.emit(ToolProgressMessageEvent("ok", ft.Colors.GREEN_400))

        self._bus.emit(ToolsCheckedEvent(needs_update=needs))

    # ── Обновление ────────────────────────────────────────────────────────────

    async def _update_tools(self) -> None:
        self._bus.emit(ToolButtonStateEvent("updating"))
        self._bus.emit(ToolProgressEvent(0.0, True))
        self._bus.emit(ToolProgressMessageEvent("prep", ft.Colors.GREEN_400))

        had_errors_box:   list[bool] = [False]
        critical_err_box: list[str]  = [""]

        def on_status(tool_name: str, code: str, detail: str) -> None:
            self._bus.emit(ToolInstallStatusEvent(tool_name, code, detail))

        def on_progress(pct: float | None) -> None:
            self._bus.emit(ToolProgressEvent(pct, True))

        def on_done(had_errors: bool, critical_err: str = "") -> None:
            had_errors_box[0]   = had_errors
            critical_err_box[0] = critical_err
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
            self._specs, self._state, self._proxy_url(),
            on_status=on_status,
            on_progress=on_progress,
            on_done=on_done,
        )

        if not had_errors_box[0] and not critical_err_box[0]:
            await self.check_tools()

    # ── Утилиты ───────────────────────────────────────────────────────────────

    def _proxy_url(self) -> str | None:
        return self._state.proxy_address.strip() if self._state.proxy_enabled else None
