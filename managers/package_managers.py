"""Исполнение декларативных манифестов системных пакетных менеджеров."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from config.tooling import PackageManagerDef, ToolingConfig


class PackageManagerAdapter(Protocol):
    name: str

    def check_command(self, proxy_url: str | None) -> list[str]: ...

    def upgrade_command(self, package_id: str) -> list[str]: ...

    def parse_available_version(self, output: str, package_id: str) -> str: ...


def _parse_no_version(output: str, package_id: str) -> str:
    return ""


def _parse_winget_table(output: str, package_id: str) -> str:
    """Разобрать локализованную таблицу winget по стабильному package ID."""
    expected = package_id.casefold()
    for line in output.splitlines():
        tokens = line.split()
        folded = [token.casefold() for token in tokens]
        if expected not in folded:
            continue
        index = folded.index(expected)
        # После ID: installed, available, source.
        if len(tokens) >= index + 4:
            return tokens[index + 2]
    return ""


_VERSION_PARSERS: Mapping[str, Callable[[str, str], str]] = {
    "none": _parse_no_version,
    "winget_table": _parse_winget_table,
}


@dataclass
class ManifestPackageManagerAdapter:
    """Общий адаптер: команды берутся из PackageManagerDef, не из Python-кода."""

    name: str
    manifest: PackageManagerDef

    def check_command(self, proxy_url: str | None) -> list[str]:
        if not self.manifest.check.args:
            return []
        return self.manifest.check.render(
            self.manifest.executable,
            {"proxy_url": proxy_url or ""},
        )

    def upgrade_command(self, package_id: str) -> list[str]:
        if not self.manifest.upgrade.args or not package_id:
            return []
        return self.manifest.upgrade.render(
            self.manifest.executable,
            {"package_id": package_id},
        )

    def parse_available_version(self, output: str, package_id: str) -> str:
        parser = _VERSION_PARSERS.get(self.manifest.version_parser)
        return parser(output, package_id) if parser is not None else ""


class WingetAdapter(ManifestPackageManagerAdapter):
    """Совместимый фасад для тестов и прямого использования."""

    def __init__(self, manifest: PackageManagerDef | None = None) -> None:
        default = ToolingConfig().package_managers["winget"]
        super().__init__("winget", manifest or default)


class UvToolAdapter(ManifestPackageManagerAdapter):
    """Совместимый фасад для uv tool."""

    def __init__(self, manifest: PackageManagerDef | None = None) -> None:
        default = ToolingConfig().package_managers["uv"]
        super().__init__("uv", manifest or default)


def package_manager_for(
    name: str,
    manifests: Mapping[str, PackageManagerDef] | None = None,
) -> PackageManagerAdapter | None:
    source = manifests if manifests is not None else ToolingConfig().package_managers
    manifest = source.get(name)
    if manifest is None or not manifest.executable:
        return None
    return ManifestPackageManagerAdapter(name, manifest)
