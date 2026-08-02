"""Реестр внешних инструментов и спецификация Deno."""

import os

from config import DEFAULT_FFMPEG_DOWNLOAD_URL
from managers.tool_registry import DEFAULT_TOOLS, DenoTool
from managers.package_managers import UvToolAdapter, WingetAdapter


def test_default_registry_contains_deno():
    assert [tool.name for tool in DEFAULT_TOOLS] == [
        "yt-dlp", "deno", "ffmpeg", "aria2c",
    ]


def test_default_ffmpeg_download_uses_current_essentials_build():
    assert DEFAULT_FFMPEG_DOWNLOAD_URL == (
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    )


def test_version_probes_are_declarative_argv():
    probes = {
        tool.name: tool.primary_binary(None).version_probe.args
        for tool in DEFAULT_TOOLS
    }
    assert probes == {
        "yt-dlp": ("--version",),
        "deno": ("--version",),
        "ffmpeg": ("-version",),
        "aria2c": ("--version",),
    }


def test_deno_version_and_self_update_command():
    tool = DenoTool()
    binary = tool.binaries(None)[0]
    assert tool.parse_version(
        binary,
        "Deno 2.9.4 (stable, release, x86_64-pc-windows-msvc)\n",
    ) == "2.9.4"
    assert tool.self_update_command(None, "deno.exe") == ["deno.exe", "upgrade"]


def test_deno_release_asset_matches_platform():
    name = DenoTool._asset_name()
    assert name.startswith("deno-") and name.endswith(".zip")
    assert ("windows" in name) is (os.name == "nt")


def test_winget_upgrade_uses_detected_package_id_without_tool_hardcode():
    adapter = WingetAdapter()
    command = adapter.upgrade_command("BtbN.FFmpeg.GPL.8.1")
    assert command[:5] == [
        "winget", "upgrade", "--id", "BtbN.FFmpeg.GPL.8.1", "--exact",
    ]


def test_winget_check_proxy_is_rendered_from_optional_config_args():
    assert WingetAdapter().check_command("http://127.0.0.1:8080")[-2:] == [
        "--proxy", "http://127.0.0.1:8080",
    ]


def test_uv_tool_upgrade_uses_detected_package_name():
    adapter = UvToolAdapter()
    assert adapter.check_command(None) == []
    assert adapter.upgrade_command("yt-dlp") == [
        "uv", "tool", "upgrade", "yt-dlp",
    ]


def test_winget_available_version_parser_is_locale_independent():
    output = """
Имя                         ИД                    Версия  Доступно  Источник
-------------------------------------------------------------------------
FFmpeg GPL nightly          BtbN.FFmpeg.GPL.8.1  8.1.1   8.1.2     winget
"""
    assert WingetAdapter().parse_available_version(
        output, "BtbN.FFmpeg.GPL.8.1",
    ) == "8.1.2"
    assert WingetAdapter().parse_available_version(
        "Не найдены установленные пакеты", "BtbN.FFmpeg.GPL.8.1",
    ) == ""
