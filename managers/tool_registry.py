"""
managers/tool_registry.py — конкретные инструменты и реестр по умолчанию.

Здесь — вся специфика yt-dlp и ffmpeg. Движок (ToolsManager) её не знает.

Чтобы добавить инструмент: реализовать ToolSpec и дописать в DEFAULT_TOOLS.
Если инструмент тоже лежит на GitHub Releases — наследуйте логику YtDlpTool
или вынесите общий GitHub-резолвер; новых полей в AppState при этом не требуется,
URL можно вернуть константой из version_url()/download_url().
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import zipfile
from typing import TYPE_CHECKING

from app_logging import get_logger
from config import safe_str, YT_DLP_CHUNK_SIZE, FFMPEG_CHUNK_SIZE
from managers.tool_specs import (
    InstallContext, ManualInstallRequired, ToolBinary,
    TOOL_VERSION_UNKNOWN, stream_to_file,
)

if TYPE_CHECKING:
    import httpx
    from state import AppState

_log = get_logger("tools")
_UA = {"User-Agent": "Mozilla/5.0"}


# ── yt-dlp ────────────────────────────────────────────────────────────────────

class YtDlpTool:
    """Один self-contained бинарник, скачиваемый напрямую с GitHub Releases."""

    name = "yt-dlp"
    _CHUNK = YT_DLP_CHUNK_SIZE
    _DATE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}")

    def binaries(self) -> list[ToolBinary]:
        return [ToolBinary(name="yt-dlp", filename="yt-dlp",
                           version_flag="--version", is_primary=True)]

    def parse_version(self, binary: ToolBinary, output: str) -> str:
        lines = output.splitlines()
        if not lines:
            return ""
        first_token = safe_str(lines[0].split()[0]) if lines[0].split() else ""
        if first_token and self._DATE_RE.match(first_token):
            return first_token
        return safe_str(lines[0])

    def version_url(self, state: "AppState") -> str:
        return state.url_yt_api

    def download_url(self, state: "AppState") -> str:
        return state.url_yt_download

    async def fetch_remote_version(self, client: "httpx.AsyncClient", url: str) -> str:
        res = await client.get(url, headers=_UA)
        tag = res.json().get("tag_name")
        if not tag:
            return TOOL_VERSION_UNKNOWN
        return safe_str(tag).lstrip("v")

    async def install(self, ctx: InstallContext) -> None:
        dest = os.path.join(ctx.tools_dir, f"yt-dlp{ctx.ext}")
        await stream_to_file(ctx.client, ctx.download_url, dest, ctx.on_progress, self._CHUNK)
        if os.name != "nt":
            os.chmod(dest, 0o755)


# ── ffmpeg-комплект (ffmpeg + ffplay + ffprobe) ──────────────────────────────

class FfmpegTool:
    """
    Один логический инструмент, поставляющий три бинарника одним zip-архивом.
    Авто-установка только на Windows; на остальных ОС — подсказка пакетного менеджера.
    """

    name = "ffmpeg"
    _CHUNK = FFMPEG_CHUNK_SIZE
    _ARCHIVE_MEMBERS = {"ffmpeg.exe", "ffplay.exe", "ffprobe.exe"}
    _VERSION_RE = re.compile(r"version\s+([0-9.]+)", re.IGNORECASE)
    _FALLBACK_RE = re.compile(r"([0-9.]+)")

    def binaries(self) -> list[ToolBinary]:
        return [
            ToolBinary(name="ffmpeg",  filename="ffmpeg",  version_flag="-version", is_primary=True),
            ToolBinary(name="ffplay",  filename="ffplay",  version_flag="-version"),
            ToolBinary(name="ffprobe", filename="ffprobe", version_flag="-version"),
        ]

    def parse_version(self, binary: ToolBinary, output: str) -> str:
        lines = output.splitlines()
        if not lines:
            return ""
        first = safe_str(lines[0])
        m = self._VERSION_RE.search(first) or self._FALLBACK_RE.search(first)
        if m:
            return safe_str(m.group(1))
        parts = first.split()
        return safe_str(parts[0]) if parts else ""

    def version_url(self, state: "AppState") -> str:
        return state.url_ffmpeg_version

    def download_url(self, state: "AppState") -> str:
        return state.url_ffmpeg_download

    async def fetch_remote_version(self, client: "httpx.AsyncClient", url: str) -> str:
        res = await client.get(url, headers=_UA)
        return res.text.strip()

    async def install(self, ctx: InstallContext) -> None:
        if os.name != "nt":
            raise ManualInstallRequired(self._manual_hint())

        zip_path = os.path.join(ctx.tools_dir, "ffmpeg_temp.zip")
        try:
            await stream_to_file(ctx.client, ctx.download_url, zip_path, ctx.on_progress, self._CHUNK)
            ctx.on_progress(None)  # индетерминированный — идёт распаковка
            await asyncio.to_thread(self._extract, zip_path, ctx.tools_dir)
        finally:
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except Exception:
                _log.exception("Failed to remove temporary FFmpeg archive")

    def _extract(self, zip_path: str, tools_dir: str) -> None:
        found = 0
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                base = os.path.basename(member).lower()
                if base in self._ARCHIVE_MEMBERS:
                    target = os.path.join(tools_dir, base)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    found += 1
        if found == 0:
            raise RuntimeError("FFmpeg EXE files not found in archive")

    @staticmethod
    def _manual_hint() -> str:
        import sys
        if sys.platform == "darwin":
            return "brew install ffmpeg"
        return ("apt: sudo apt install ffmpeg  "
                "•  dnf: sudo dnf install ffmpeg  "
                "•  pacman: sudo pacman -S ffmpeg")


# ── Реестр по умолчанию ───────────────────────────────────────────────────────

def build_default_tools() -> list:
    """Список инструментов приложения. Порядок = порядок отображения в настройках."""
    return [YtDlpTool(), FfmpegTool()]


DEFAULT_TOOLS = build_default_tools()
