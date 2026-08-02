"""Декларативная конфигурация запуска и обнаружения внешних инструментов.

Здесь находятся только данные и их безопасная валидация. Выполнение процессов,
разбор вывода и работа с файловой системой остаются в managers/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from string import Formatter
from typing import Any, Dict, Iterable, Mapping

from config.utils import safe_str


def _copy_optional_args(value: Mapping[str, Iterable[str]]) -> Dict[str, tuple[str, ...]]:
    return {name: tuple(args) for name, args in value.items()}


@dataclass
class CommandSpec:
    """Аргументы процесса без shell-строки.

    ``args`` передаются как отдельные элементы argv. ``optional_args`` добавляет
    группу только когда одноимённое значение контекста непустое. Поддерживаются
    исключительно простые allowlisted-плейсхолдеры вида ``{package_id}``.
    """

    args: tuple[str, ...] = ()
    optional_args: Dict[str, tuple[str, ...]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"args": list(self.args)}
        if self.optional_args:
            result["optional_args"] = {
                name: list(args) for name, args in self.optional_args.items()
            }
        return result

    def clone(self) -> "CommandSpec":
        return CommandSpec(tuple(self.args), _copy_optional_args(self.optional_args))

    def is_valid(self, allowed_placeholders: set[str], *, allow_empty: bool = True) -> bool:
        if not allow_empty and not self.args:
            return False
        if any(not isinstance(arg, str) or not arg for arg in self.args):
            return False
        if any(name not in allowed_placeholders for name in self.optional_args):
            return False
        tokens = [*self.args]
        for args in self.optional_args.values():
            if any(not isinstance(arg, str) or not arg for arg in args):
                return False
            tokens.extend(args)
        try:
            for token in tokens:
                for _, name, format_spec, conversion in Formatter().parse(token):
                    if name is None:
                        continue
                    if (name not in allowed_placeholders
                            or bool(format_spec) or conversion is not None):
                        return False
        except ValueError:
            return False
        return True

    def render(self, executable: str, values: Mapping[str, str] | None = None) -> list[str]:
        """Собрать argv; executable всегда передаётся отдельно от конфигурации."""
        context = dict(values or {})

        def expand(items: Iterable[str]) -> list[str]:
            return [item.format_map(context) for item in items]

        command = [executable, *expand(self.args)]
        for name, args in self.optional_args.items():
            if context.get(name):
                command.extend(expand(args))
        return command

    @staticmethod
    def from_dict(
        d: Dict[str, Any],
        defaults: "CommandSpec | None" = None,
        *,
        allowed_placeholders: set[str] | None = None,
        allow_empty: bool = True,
    ) -> "CommandSpec":
        fallback = (defaults or CommandSpec()).clone()
        allowed = allowed_placeholders or set()

        raw_args = d.get("args", fallback.args)
        if not isinstance(raw_args, (list, tuple)) or not all(
            isinstance(item, str) for item in raw_args
        ):
            return fallback

        if "optional_args" not in d:
            optional = _copy_optional_args(fallback.optional_args)
        else:
            raw_optional = d.get("optional_args")
            if not isinstance(raw_optional, dict):
                return fallback
            optional = {}
            for name, items in raw_optional.items():
                if (not isinstance(name, str)
                        or not isinstance(items, (list, tuple))
                        or not all(isinstance(item, str) for item in items)):
                    return fallback
                optional[name] = tuple(items)

        candidate = CommandSpec(tuple(raw_args), optional)
        return candidate if candidate.is_valid(
            allowed, allow_empty=allow_empty,
        ) else fallback


@dataclass
class PackageManagerDef:
    """CLI-манифест пакетного менеджера."""

    executable: str = ""
    check: CommandSpec = field(default_factory=CommandSpec)
    upgrade: CommandSpec = field(default_factory=CommandSpec)
    version_parser: str = "none"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executable": self.executable,
            "check": self.check.to_dict(),
            "upgrade": self.upgrade.to_dict(),
            "version_parser": self.version_parser,
        }

    @staticmethod
    def from_dict(
        d: Dict[str, Any], defaults: "PackageManagerDef | None" = None,
    ) -> "PackageManagerDef":
        fallback = defaults or PackageManagerDef()
        executable = safe_str(d.get("executable")) or fallback.executable
        parser = safe_str(d.get("version_parser")) or fallback.version_parser
        raw_check = d.get("check", {})
        raw_upgrade = d.get("upgrade", {})
        return PackageManagerDef(
            executable=executable,
            check=CommandSpec.from_dict(
                raw_check if isinstance(raw_check, dict) else {},
                fallback.check,
                allowed_placeholders={"proxy_url"},
            ),
            upgrade=CommandSpec.from_dict(
                raw_upgrade if isinstance(raw_upgrade, dict) else {},
                fallback.upgrade,
                allowed_placeholders={"package_id"},
            ),
            version_parser=parser,
        )


@dataclass
class InstallationDetector:
    """Параметры одной стратегии определения происхождения executable."""

    kind: str = ""
    path_fragment: str = ""
    target_marker: str = ""
    bin_env_var: str = ""
    default_bin_dir: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "kind": self.kind,
            "path_fragment": self.path_fragment,
            "target_marker": self.target_marker,
            "bin_env_var": self.bin_env_var,
            "default_bin_dir": self.default_bin_dir,
        }

    @staticmethod
    def from_dict(
        d: Dict[str, Any], defaults: "InstallationDetector | None" = None,
    ) -> "InstallationDetector":
        fallback = defaults or InstallationDetector()
        return InstallationDetector(
            kind=safe_str(d.get("kind")) or fallback.kind,
            path_fragment=(safe_str(d.get("path_fragment"))
                           or fallback.path_fragment),
            target_marker=(safe_str(d.get("target_marker"))
                           or fallback.target_marker),
            bin_env_var=(safe_str(d.get("bin_env_var"))
                         or fallback.bin_env_var),
            default_bin_dir=(safe_str(d.get("default_bin_dir"))
                             or fallback.default_bin_dir),
        )


def _default_package_managers() -> Dict[str, PackageManagerDef]:
    return {
        "winget": PackageManagerDef(
            executable="winget",
            check=CommandSpec(
                args=(
                    "list", "--upgrade-available", "--include-unknown",
                    "--accept-source-agreements", "--disable-interactivity",
                ),
                optional_args={"proxy_url": ("--proxy", "{proxy_url}")},
            ),
            upgrade=CommandSpec(args=(
                "upgrade", "--id", "{package_id}", "--exact", "--silent",
                "--accept-package-agreements", "--accept-source-agreements",
                "--disable-interactivity",
            )),
            version_parser="winget_table",
        ),
        "uv": PackageManagerDef(
            executable="uv",
            check=CommandSpec(),
            upgrade=CommandSpec(args=("tool", "upgrade", "{package_id}")),
            version_parser="none",
        ),
    }


def _default_detectors() -> Dict[str, InstallationDetector]:
    return {
        "winget": InstallationDetector(
            kind="resolved_link_parent",
            path_fragment="/microsoft/winget/links/",
            target_marker="_Microsoft.Winget.Source_",
        ),
        "uv": InstallationDetector(
            kind="bin_directory",
            bin_env_var="UV_TOOL_BIN_DIR",
            default_bin_dir="~/.local/bin",
        ),
    }


@dataclass
class ToolingConfig:
    """Корневая конфигурация способов системной установки инструментов."""

    package_managers: Dict[str, PackageManagerDef] = field(
        default_factory=_default_package_managers
    )
    detectors: Dict[str, InstallationDetector] = field(default_factory=_default_detectors)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_managers": {
                name: manifest.to_dict()
                for name, manifest in self.package_managers.items()
            },
            "detectors": {
                name: detector.to_dict() for name, detector in self.detectors.items()
            },
        }

    @staticmethod
    def from_dict(
        d: Dict[str, Any], defaults: "ToolingConfig | None" = None,
    ) -> "ToolingConfig":
        fallback = defaults or ToolingConfig()
        managers = {
            name: PackageManagerDef.from_dict({}, manifest)
            for name, manifest in fallback.package_managers.items()
        }
        raw_managers = d.get("package_managers", {})
        if isinstance(raw_managers, dict):
            for name, raw in raw_managers.items():
                if isinstance(name, str) and isinstance(raw, dict):
                    default = fallback.package_managers.get(
                        name, PackageManagerDef(executable=name)
                    )
                    managers[name] = PackageManagerDef.from_dict(raw, default)

        detectors = {
            name: InstallationDetector.from_dict({}, detector)
            for name, detector in fallback.detectors.items()
        }
        raw_detectors = d.get("detectors", {})
        if isinstance(raw_detectors, dict):
            for name, raw in raw_detectors.items():
                if isinstance(name, str) and isinstance(raw, dict):
                    default = fallback.detectors.get(name, InstallationDetector())
                    detectors[name] = InstallationDetector.from_dict(raw, default)

        return ToolingConfig(package_managers=managers, detectors=detectors)

