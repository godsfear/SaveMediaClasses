"""
paths.py — единый источник путей приложения.

AppPaths — неизменяемый инстанс, создаётся ОДИН раз в композиционном корне
(Services.create) через AppPaths.detect() и раздаётся объектам через DI (svc.paths).

Правило: никто не вычисляет пути сам и не дёргает статические методы — все
берут готовый инстанс из Services. Это даёт единственный источник истины
и тестируемость (в тестах можно подставить AppPaths(app_dir=tmp_path)).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    """Все пути приложения, производные от app_dir."""

    app_dir: Path

    # ── Фабрика ───────────────────────────────────────────────────────────────

    @classmethod
    def detect(cls) -> "AppPaths":
        """Определить корневую папку: рядом с .exe (frozen) или рядом с исходниками."""
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            base = Path(__file__).resolve().parent
        return cls(app_dir=base)

    # ── Производные пути ──────────────────────────────────────────────────────

    @property
    def config_file(self) -> Path:
        return self.app_dir / "config.json"

    @property
    def db_file(self) -> Path:
        return self.app_dir / "savemedia.db"

    @property
    def log_file(self) -> Path:
        return self.app_dir / "savemedia.log"

    @property
    def tools_dir(self) -> Path:
        return self.app_dir / "tools"

    @property
    def locale_dir(self) -> Path:
        return self.app_dir / "locale"

    @property
    def assets_dir(self) -> Path:
        return self.app_dir

    @property
    def app_icon(self) -> Path:
        return self.app_dir / "SaveMedia.png"

    @property
    def pyproject(self) -> Path:
        return self.app_dir / "pyproject.toml"
