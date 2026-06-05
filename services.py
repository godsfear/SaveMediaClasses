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
from pathlib import Path
from typing import Any, Callable

from app_logging import configure_logging
from events import EventBus
from managers.config_manager import ConfigManager
from managers.download_manager import DownloadManager
from managers.download_repository import DownloadRepository
from managers.tools_manager import ToolsManager
from paths import AppPaths
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
    def db_path(self) -> Path:
        return AppPaths.db_file()

    @property
    def log_path(self) -> Path:
        return AppPaths.log_file()

    @property
    def config_path(self) -> Path:
        return AppPaths.config_file()

    # ── Фабричный метод ───────────────────────────────────────────────────────

    @staticmethod
    def create(
        base_dir: str,
        safe_update: Callable[[], None],
        task_runner: Callable[..., Any],
    ) -> "Services":
        """Собирает все зависимости в правильном порядке.
        task_runner — планировщик coroutine (в app.py: page.run_task)."""
        from managers.providers import YtDlpProvider

        tools_dir  = AppPaths.tools_dir()
        os.makedirs(tools_dir, exist_ok=True)
        configure_logging(AppPaths.config_file())

        bus        = EventBus()
        config_mgr = ConfigManager(os.path.join(base_dir, "config.json"))
        tools      = ToolsManager(base_dir, tools_dir)
        state = config_mgr.load()
        db_path = AppPaths.db_file()
        db      = DownloadRepository(db_path=db_path, bus=bus)
        dm      = DownloadManager(
            provider_factory=lambda: YtDlpProvider(base_dir, tools_dir),
            log_path=AppPaths.log_file(),
            bus=bus,
            task_runner=task_runner,
            db=db,
        )

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
