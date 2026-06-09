"""
paths.py — единый источник путей приложения.

AppPaths — неизменяемый инстанс, создаётся ОДИН раз в композиционном корне
(Services.create) через AppPaths.detect() и раздаётся объектам через DI (svc.paths).

Правило: никто не вычисляет пути сам и не дёргает статические методы — все
берут готовый инстанс из Services. Это даёт единственный источник истины
и тестируемость (в тестах можно подставить AppPaths(app_dir=tmp_path)).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "savemediaclasses"


@dataclass(frozen=True)
class AppPaths:
    """Все пути приложения, производные от app_dir.

    app_dir  — корень рядом с .exe/исходниками (портативный режим, ресурсы только
               на чтение: locale, иконка).
    data_dir — записываемая база для скачиваемых инструментов. Совпадает с app_dir,
               когда тот доступен для записи (портативный режим), иначе — папка в
               профиле пользователя (Linux/macOS, либо Windows в Program Files).
               None означает «вывести из app_dir» (поведение по умолчанию в тестах).
    """

    app_dir: Path
    data_dir: Path | None = None

    # ── Фабрика ───────────────────────────────────────────────────────────────

    @classmethod
    def detect(cls) -> "AppPaths":
        """Определить корневую папку: рядом с .exe (frozen) или рядом с исходниками.

        data_dir выбирается так: если app_dir доступен для записи — используем его
        (портативный режим). Иначе уходим в пользовательский data-dir, чтобы
        установка инструментов работала там, где папка программы только на чтение.
        """
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            base = Path(__file__).resolve().parent
        data = base if cls._dir_writable(base) else cls.user_data_dir()
        return cls(app_dir=base, data_dir=data)

    # ── Пользовательский data-dir (фолбэк, когда app_dir только на чтение) ─────

    @staticmethod
    def user_data_dir() -> Path:
        """Папка в профиле пользователя по конвенции платформы."""
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
            return Path(base) / APP_NAME
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / APP_NAME
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
        return Path(base) / APP_NAME

    @staticmethod
    def _dir_writable(path: Path) -> bool:
        """Можно ли создавать/писать файлы внутри path (создаёт его при необходимости)."""
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.touch()
            probe.unlink()
            return True
        except Exception:
            return False

    # ── Производные пути ──────────────────────────────────────────────────────

    @property
    def _writable_base(self) -> Path:
        """База для файлов, в которые приложение пишет (config/db/log/tools).

        Совпадает с app_dir в портативном режиме; в профиле пользователя, если
        app_dir только на чтение (Linux/macOS, Windows в Program Files).
        """
        return self.data_dir or self.app_dir

    @property
    def config_file(self) -> Path:
        return self._writable_base / "config.json"

    @property
    def db_file(self) -> Path:
        return self._writable_base / "savemedia.db"

    @property
    def log_file(self) -> Path:
        return self._writable_base / "savemedia.log"

    @property
    def tools_dir(self) -> Path:
        """Записываемая папка для скачиваемых инструментов (data_dir, фолбэк — app_dir)."""
        return self._writable_base / "tools"

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
