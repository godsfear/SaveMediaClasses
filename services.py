"""
services.py — контейнер зависимостей приложения.

Services создаётся один раз в app.py и передаётся в экраны.
Добавление новой зависимости: поле в Services — подписи экранов не меняются.

Что входит:
  Инфраструктура  — bus, config_mgr, tools, dm
  Состояние       — state (изменяемый dataclass, это нормально)
  Окружение       — paths (единый источник путей), safe_update

Что НЕ входит:
  page            — Flet-специфика, остаётся параметром экранов
  UI-виджеты      — не сервисы
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from app_logging import configure_logging
from events import EventBus
from i18l import Locale
from managers.config_manager import ConfigManager
from managers.download_manager import DownloadManager
from managers.download_repository import DownloadRepository
from managers.tools_manager import ToolsManager
from paths import AppPaths
from state import AppState


@dataclass
class Services:
    # ── Окружение ─────────────────────────────────────────────────────────────
    paths:       AppPaths
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

    # ── Фабричный метод ───────────────────────────────────────────────────────

    @staticmethod
    def create(
        safe_update: Callable[[], None],
        task_runner: Callable[..., Any],
    ) -> "Services":
        """Собирает все зависимости в правильном порядке.
        task_runner — планировщик coroutine (в app.py: page.run_task)."""
        from managers.providers import YtDlpProvider

        # Единый источник путей — создаётся первым и раздаётся всем остальным.
        paths = AppPaths.detect()
        Locale.configure(paths)

        os.makedirs(paths.tools_dir, exist_ok=True)
        configure_logging(paths.log_file)

        bus        = EventBus()
        config_mgr = ConfigManager(paths.config_file)
        tools      = ToolsManager(paths)
        state      = config_mgr.load()
        db         = DownloadRepository(db_path=paths.db_file, bus=bus)
        dm         = DownloadManager(
            provider_factory=lambda: YtDlpProvider(paths),
            log_path=paths.log_file,
            bus=bus,
            task_runner=task_runner,
            db=db,
        )

        return Services(
            paths=paths,
            safe_update=safe_update,
            bus=bus,
            config_mgr=config_mgr,
            tools=tools,
            dm=dm,
            db=db,
            state=state,
        )
