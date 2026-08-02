"""Политика выбора системных и управляемых внешних инструментов."""

import os
from types import SimpleNamespace

import pytest

import managers.tool_resolver as resolver_module
from config import InstallationDetector
from managers.tool_resolver import ToolOrigin, ToolResolver


def _paths(tmp_path):
    tools = tmp_path / "tools"
    app = tmp_path / "app"
    tools.mkdir()
    app.mkdir()
    return SimpleNamespace(tools_dir=tools, app_dir=app)


def test_system_binary_has_priority_over_managed(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    managed = paths.tools_dir / ("deno.exe" if os.name == "nt" else "deno")
    managed.write_bytes(b"managed")
    system = str(tmp_path / "system" / managed.name)
    monkeypatch.setenv("PATH", str(tmp_path / "system"))
    monkeypatch.setattr(
        resolver_module.shutil, "which",
        lambda name, path=None: system if name == "deno" else None,
    )

    location = ToolResolver(paths).resolve("deno")

    assert location.origin == ToolOrigin.SYSTEM
    assert location.path == system


def test_managed_binary_is_fallback_and_can_be_explicitly_preferred(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    filename = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"
    managed = paths.tools_dir / filename
    managed.write_bytes(b"managed")
    system = str(tmp_path / "system" / filename)
    monkeypatch.setattr(resolver_module.shutil, "which", lambda *a, **k: system)
    resolver = ToolResolver(paths)

    assert resolver.resolve("yt-dlp").origin == ToolOrigin.SYSTEM
    resolver.prefer_managed("yt-dlp")
    assert resolver.resolve("yt-dlp") == resolver.managed("yt-dlp")


def test_child_path_keeps_system_before_managed(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    system_dir = str(tmp_path / "system")
    monkeypatch.setenv("PATH", system_dir)

    entries = ToolResolver(paths).process_env()["PATH"].split(os.pathsep)

    assert entries[0] == system_dir
    assert entries.index(str(paths.tools_dir)) > 0
    assert entries.index(str(paths.app_dir)) > entries.index(str(paths.tools_dir))


def test_child_env_does_not_leak_embedded_python_runtime(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    monkeypatch.setenv("PYTHONHOME", str(tmp_path / "embedded-python"))
    monkeypatch.setenv("PythonPath", str(tmp_path / "embedded-packages"))
    monkeypatch.setenv("PYTHONNOUSERSITE", "1")
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / ".venv"))

    env = ToolResolver(paths).process_env()
    keys = {name.casefold() for name in env}

    assert "pythonhome" not in keys
    assert "pythonpath" not in keys
    assert "pythonnousersite" not in keys
    assert "virtual_env" not in keys


@pytest.mark.parametrize("package_id,binary", [
    ("DenoLand.Deno", "deno.exe"),
    ("Gyan.FFmpeg", "ffmpeg.exe"),
    ("BtbN.FFmpeg.GPL.8.1", "ffmpeg.exe"),
    ("yt-dlp.FFmpeg", "ffprobe.exe"),
])
def test_winget_link_is_identified_as_package_managed(
    tmp_path, monkeypatch, package_id, binary,
):
    paths = _paths(tmp_path)
    link = rf"C:\Users\tester\AppData\Local\Microsoft\WinGet\Links\{binary}"
    packages = r"C:\Users\tester\AppData\Local\Microsoft\WinGet\Packages"
    target = (packages + "\\" + package_id
              + rf"_Microsoft.Winget.Source_8wekyb3d8bbwe\{binary}")
    monkeypatch.setattr(resolver_module.shutil, "which", lambda *a, **k: link)
    monkeypatch.setattr(resolver_module.os.path, "realpath", lambda path: target)

    location = ToolResolver(paths).system(os.path.splitext(binary)[0])

    assert location.origin == ToolOrigin.SYSTEM
    assert location.manager == "winget"
    assert location.package_id == package_id


def test_uv_tool_launcher_is_identified_by_bin_directory(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    uv_bin = tmp_path / "uv-bin"
    executable = uv_bin / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp")
    monkeypatch.setenv("UV_TOOL_BIN_DIR", str(uv_bin))
    monkeypatch.setattr(
        resolver_module.shutil, "which", lambda *a, **k: str(executable),
    )

    location = ToolResolver(paths).system("yt-dlp")

    assert location.origin == ToolOrigin.SYSTEM
    assert location.manager == "uv"
    assert location.package_id == "yt-dlp"


def test_custom_bin_directory_detector_is_used_without_resolver_changes(
    tmp_path, monkeypatch,
):
    paths = _paths(tmp_path)
    custom_bin = tmp_path / "custom-bin"
    executable = custom_bin / ("deno.exe" if os.name == "nt" else "deno")
    monkeypatch.setattr(
        resolver_module.shutil, "which", lambda *a, **k: str(executable),
    )
    resolver = ToolResolver(paths, {
        "portable": InstallationDetector(
            kind="bin_directory",
            default_bin_dir=str(custom_bin),
        ),
    })

    location = resolver.system("deno")

    assert location.manager == "portable"
    assert location.package_id == "deno"
