"""
managers/tool_registry.py — конкретные инструменты и реестр по умолчанию.

Здесь — вся специфика yt-dlp и ffmpeg. Движок (ToolsManager) её не знает.

Чтобы добавить инструмент:
  1. Реализовать ToolSpec в этом файле.
  2. Добавить дефолтный ToolConfig в config.default_tools_config().
  3. Дописать в DEFAULT_TOOLS.
Параметры нового инструмента (URL, chunk_size, filename, version_flag)
задаются в конфиге и доступны через state.tools[name].
"""

from __future__ import annotations

import asyncio
import os
import re
import zipfile
from typing import TYPE_CHECKING

from app_logging import get_logger
from config import safe_str, YT_DLP_CHUNK_SIZE, FFMPEG_CHUNK_SIZE, ToolConfig
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
    _DATE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}")

    def binaries(self, state: "AppState") -> list[ToolBinary]:
        tc = state.tools.get(self.name, ToolConfig())
        return [ToolBinary(name=self.name,
                           filename=tc.filename or self.name,
                           version_flag=tc.version_flag or "--version",
                           is_primary=True)]

    def parse_version(self, binary: ToolBinary, output: str) -> str:
        lines = output.splitlines()
        if not lines:
            return ""
        first_token = safe_str(lines[0].split()[0]) if lines[0].split() else ""
        if first_token and self._DATE_RE.match(first_token):
            return first_token
        return safe_str(lines[0])

    def version_url(self, state: "AppState") -> str:
        return state.tools.get("yt-dlp", ToolConfig()).version_url

    def download_url(self, state: "AppState") -> str:
        return state.tools.get("yt-dlp", ToolConfig()).download_url

    def chunk_size(self, state: "AppState") -> int:
        return state.tools.get("yt-dlp", ToolConfig(chunk_size=YT_DLP_CHUNK_SIZE)).chunk_size

    async def fetch_remote_version(self, client: "httpx.AsyncClient", url: str) -> str:
        res = await client.get(url, headers=_UA)
        tag = res.json().get("tag_name")
        if not tag:
            return TOOL_VERSION_UNKNOWN
        return safe_str(tag).lstrip("v")

    async def install(self, ctx: InstallContext) -> None:
        tc = ctx.state.tools.get(self.name, ToolConfig()) if ctx.state else ToolConfig()
        filename = tc.filename or self.name
        dest = os.path.join(ctx.tools_dir, f"{filename}{ctx.ext}")
        await stream_to_file(ctx.client, ctx.download_url, dest, ctx.on_progress, ctx.chunk_size)
        if os.name != "nt":
            os.chmod(dest, 0o755)


# ── ffmpeg-комплект (ffmpeg + ffplay + ffprobe) ──────────────────────────────

class FfmpegTool:
    """
    Один логический инструмент, поставляющий три бинарника одним zip-архивом.
    Авто-установка только на Windows; на остальных ОС — подсказка пакетного менеджера.
    """

    name = "ffmpeg"
    _VERSION_RE = re.compile(r"version\s+([0-9.]+)", re.IGNORECASE)
    _FALLBACK_RE = re.compile(r"([0-9.]+)")

    def binaries(self, state: "AppState") -> list[ToolBinary]:
        tc = state.tools.get(self.name, ToolConfig())
        result = [ToolBinary(name=self.name,
                             filename=tc.filename or self.name,
                             version_flag=tc.version_flag or "-version",
                             is_primary=True)]
        for bin_name, bi in tc.binaries.items():
            result.append(ToolBinary(name=bin_name,
                                     filename=bi.filename or bin_name,
                                     version_flag=bi.version_flag or "-version"))
        return result

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
        return state.tools.get("ffmpeg", ToolConfig()).version_url

    def download_url(self, state: "AppState") -> str:
        return state.tools.get("ffmpeg", ToolConfig()).download_url

    def chunk_size(self, state: "AppState") -> int:
        return state.tools.get("ffmpeg", ToolConfig(chunk_size=FFMPEG_CHUNK_SIZE)).chunk_size

    async def fetch_remote_version(self, client: "httpx.AsyncClient", url: str) -> str:
        res = await client.get(url, headers=_UA)
        return res.text.strip()

    async def install(self, ctx: InstallContext) -> None:
        if os.name != "nt":
            raise ManualInstallRequired(self._manual_hint())

        tc = ctx.state.tools.get(self.name, ToolConfig()) if ctx.state else ToolConfig()
        archive_members = (
            {f"{tc.filename or self.name}.exe"} |
            {f"{bi.filename or name}.exe" for name, bi in tc.binaries.items()}
        )

        zip_path = os.path.join(ctx.tools_dir, "ffmpeg_temp.zip")
        try:
            await stream_to_file(ctx.client, ctx.download_url, zip_path, ctx.on_progress, ctx.chunk_size)
            ctx.on_progress(None)  # индетерминированный — идёт распаковка
            await asyncio.to_thread(self._extract, zip_path, ctx.tools_dir, archive_members)
        finally:
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except Exception:
                _log.exception("Failed to remove temporary FFmpeg archive")

    def _extract(self, zip_path: str, tools_dir: str, archive_members: set[str]) -> None:
        found = 0
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                base = os.path.basename(member).lower()
                if base in archive_members:
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
