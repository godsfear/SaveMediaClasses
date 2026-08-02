"""Единая политика поиска внешних исполняемых файлов.

Системная установка всегда имеет приоритет. Управляемая приложением копия из
``tools`` используется только как fallback. Временное предпочтение managed-
копии включается менеджером инструментов, если системная версия устарела и не
смогла обновиться.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from config.tooling import InstallationDetector, ToolingConfig


# Встроенный Python Flet/Serious Python выставляет эти переменные process-wide.
# Передавать их внешнему Python/PyPI launcher (например, yt-dlp.exe) нельзя:
# тот начнёт искать stdlib и пакеты внутри bundle приложения.
_EMBEDDED_PYTHON_ENV = {
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONNOUSERSITE",
    "PYTHONINSPECT",
    "PYTHONEXECUTABLE",
    "PYTHONSAFEPATH",
    "__PYVENV_LAUNCHER__",
    "VIRTUAL_ENV",
}


class ToolOrigin(str, Enum):
    SYSTEM = "system"
    MANAGED = "managed"
    MISSING = "missing"


@dataclass(frozen=True)
class ToolLocation:
    path: str = ""
    origin: ToolOrigin = ToolOrigin.MISSING
    manager: str = ""   # "winget" / "uv" для package-managed executable
    package_id: str = ""

    @property
    def found(self) -> bool:
        return bool(self.path)


class ToolResolver:
    """Ищет инструменты и формирует PATH дочерних процессов по одной политике."""

    def __init__(
        self,
        paths,
        detectors: Mapping[str, InstallationDetector] | None = None,
    ) -> None:
        self._paths = paths
        self._ext = ".exe" if os.name == "nt" else ""
        self._managed_overrides: set[str] = set()
        self.configure(detectors or ToolingConfig().detectors)

    def configure(self, detectors: Mapping[str, InstallationDetector]) -> None:
        """Заменить декларативные правила определения package manager."""
        self._detectors = dict(detectors)

    def managed_path(self, filename: str) -> str:
        return os.path.join(str(self._paths.tools_dir), f"{filename}{self._ext}")

    def managed(self, filename: str) -> ToolLocation:
        path = self.managed_path(filename)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return ToolLocation(path, ToolOrigin.MANAGED)
        return ToolLocation()

    def system(self, filename: str) -> ToolLocation:
        # Не считаем tools/app частью системы, даже если пользователь ранее
        # добавил их в PATH: иначе источник инструмента определялся бы неверно.
        search_path = os.pathsep.join(self._system_path_entries())
        path = shutil.which(filename, path=search_path)
        if not path:
            return ToolLocation()
        manager, package_id = self._package_details(path)
        return ToolLocation(path, ToolOrigin.SYSTEM, manager, package_id)

    def resolve(self, filename: str) -> ToolLocation:
        if filename in self._managed_overrides:
            managed = self.managed(filename)
            if managed.found:
                return managed
            self._managed_overrides.discard(filename)
        system = self.system(filename)
        return system if system.found else self.managed(filename)

    def prefer_managed(self, filename: str, enabled: bool = True) -> None:
        if enabled:
            self._managed_overrides.add(filename)
        else:
            self._managed_overrides.discard(filename)

    def process_env(self) -> dict[str, str]:
        """Окружение для CLI: исходный системный PATH первым, fallback-папки после."""
        env = os.environ.copy()
        # Windows environment keys регистронезависимы. Удаляем по casefold,
        # чтобы очистка была корректной и при нестандартном написании ключей.
        embedded = {name.casefold() for name in _EMBEDDED_PYTHON_ENV}
        for name in list(env):
            if name.casefold() in embedded:
                env.pop(name, None)
        entries = list(self._system_path_entries())
        known = {self._path_key(path) for path in entries}
        for extra in (str(self._paths.tools_dir), str(self._paths.app_dir)):
            if extra and self._path_key(extra) not in known:
                entries.append(extra)
                known.add(self._path_key(extra))
        env["PATH"] = os.pathsep.join(entries)
        return env

    def _system_path_entries(self) -> list[str]:
        excluded = {
            self._path_key(str(self._paths.tools_dir)),
            self._path_key(str(self._paths.app_dir)),
        }
        return [
            entry for entry in os.environ.get("PATH", "").split(os.pathsep)
            if entry and self._path_key(entry) not in excluded
        ]

    @staticmethod
    def _path_key(path: str) -> str:
        return os.path.normcase(os.path.abspath(os.path.expandvars(path.strip('"'))))

    def _package_details(self, path: str) -> tuple[str, str]:
        strategies = {
            "resolved_link_parent": self._detect_resolved_link_parent,
            "bin_directory": self._detect_bin_directory,
        }
        for manager, detector in self._detectors.items():
            strategy = strategies.get(detector.kind)
            package_id = strategy(path, detector) if strategy is not None else ""
            if package_id:
                return manager, package_id
        return "", ""

    @staticmethod
    def _detect_resolved_link_parent(path: str, detector: InstallationDetector) -> str:
        """ID пакета берётся из имени родителя цели launcher/symlink."""
        normalized = os.path.abspath(path).replace("\\", "/").casefold()
        fragment = detector.path_fragment.replace("\\", "/").casefold()
        if not fragment or fragment not in normalized or not detector.target_marker:
            return ""

        target = os.path.realpath(path).replace("\\", "/")
        parts = target.rstrip("/").split("/")
        if len(parts) < 2:
            return ""
        package_dir = parts[-2]
        marker_index = package_dir.casefold().find(detector.target_marker.casefold())
        return package_dir[:marker_index] if marker_index > 0 else ""

    @staticmethod
    def _detect_bin_directory(path: str, detector: InstallationDetector) -> str:
        """Executable в настроенной bin-папке; package ID равен имени launcher."""
        configured = os.environ.get(detector.bin_env_var) if detector.bin_env_var else ""
        bin_dir = configured or detector.default_bin_dir
        if not bin_dir:
            return ""
        bin_dir = os.path.expanduser(os.path.expandvars(bin_dir))
        actual = os.path.normcase(os.path.dirname(os.path.abspath(path)))
        expected = os.path.normcase(os.path.abspath(bin_dir))
        if actual != expected:
            return ""
        return os.path.splitext(os.path.basename(path))[0]
