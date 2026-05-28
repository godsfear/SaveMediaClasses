"""
services.py — контейнер зависимостей приложения.

Services создаётся один раз в app.py и передаётся в экраны.
Добавление новой зависимости: поле в Services — подписи экранов не меняются.

Что входит:
  Инфраструктура  — bus, config_mgr, tools, dm
  Состояние       — state (изменяемый dataclass, это нормально)
  Окружение       — base_dir, tools_dir, safe_update

Что НЕ входит:
  page            — Flet-специфика, остаётся параметром экранов
  UI-виджеты      — не сервисы
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from events import EventBus
from managers.config_manager import ConfigManager
from managers.download_manager import DownloadManager
from managers.download_repository import DownloadRepository
from managers.tools_manager import ToolsManager
from state import AppState


@dataclass
class Services:
    # ── Окружение ─────────────────────────────────────────────────────────────
    base_dir:    str
    tools_dir:   str
    safe_update: Callable[[], None]

    # ── Инфраструктура ────────────────────────────────────────────────────────
    bus:        EventBus
    config_mgr: ConfigManager
    tools:      ToolsManager
    dm:         DownloadManager

    # ── Персистентность ──────────────────────────────────────────────────────
    db: DownloadRepository

    # ── Состояние приложения ──────────────────────────────────────────────────
    state: AppState

    # ── Вспомогательные свойства ──────────────────────────────────────────────

    @property
    def db_path(self) -> str:
        return os.path.join(self.base_dir, "savemedia.db")

    @property
    def log_path(self) -> str:
        return os.path.join(self.base_dir, "savemedia.log")

    @property
    def config_path(self) -> str:
        return os.path.join(self.base_dir, "config.json")

    def save_config(self, page) -> None:
        """Снять актуальные значения окна и сохранить state в JSON.
        page передаётся для чтения текущей геометрии окна."""
        w, h, l, t = page.window.width, page.window.height, page.window.left, page.window.top
        if w and w > 10:    self.state.window.width  = int(w)
        if h and h > 10:    self.state.window.height = int(h)
        if l is not None:   self.state.window.left   = int(l)
        if t is not None:   self.state.window.top    = int(t)
        self.config_mgr.save(self.state)

    # ── Фабричный метод ───────────────────────────────────────────────────────

    @staticmethod
    def create(base_dir: str, safe_update: Callable[[], None]) -> "Services":
        """Собирает все зависимости в правильном порядке."""
        from managers.providers import YtDlpProvider

        tools_dir  = os.path.join(base_dir, "tools")
        os.makedirs(tools_dir, exist_ok=True)

        bus        = EventBus()
        config_mgr = ConfigManager(os.path.join(base_dir, "config.json"))
        tools      = ToolsManager(base_dir, tools_dir)
        dm         = DownloadManager(
            provider_factory=lambda: YtDlpProvider(base_dir, tools_dir),
            log_path=os.path.join(base_dir, "savemedia.log"),
            bus=bus,
        )
        state = config_mgr.load()
        db_path = os.path.join(base_dir, "savemedia.db")
        db      = DownloadRepository(db_path=db_path, bus=bus)

        return Services(
            base_dir=base_dir,
            tools_dir=tools_dir,
            safe_update=safe_update,
            bus=bus,
            config_mgr=config_mgr,
            tools=tools,
            dm=dm,
            db=db,
            state=state,
        )
