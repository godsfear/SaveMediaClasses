"""
managers/tool_registry.py — конкретные инструменты и реестр по умолчанию.

Здесь — вся специфика yt-dlp и ffmpeg. Движок (ToolsManager) её не знает.

Чтобы добавить инструмент:
  1. Реализовать подкласс BaseTool в этом файле (parse_version /
     fetch_remote_version / install + default_config с секцией binaries).
  2. Дописать его в DEFAULT_TOOLS.
  Метод binaries() общий (в BaseTool) — он строится из cfg.binaries, поэтому
  переопределять его не нужно. Дефолтный конфиг объявляется прямо в инструменте
  (default_config) и автоматически попадает в default_tools_config() —
  отдельной правки в config.py не требуется.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from typing import TYPE_CHECKING, Dict

from app_logging import get_logger
from config import (
    safe_str,
    YT_DLP_CHUNK_SIZE, FFMPEG_CHUNK_SIZE, ARIA2_CHUNK_SIZE,
    DEFAULT_YT_API_URL, DEFAULT_YT_DOWNLOAD_URL,
    DEFAULT_FFMPEG_VERSION_URL, DEFAULT_FFMPEG_DOWNLOAD_URL,
    DEFAULT_ARIA2_VERSION_URL, DEFAULT_ARIA2_DOWNLOAD_URL,
    ToolConfig, YtDlpConfig, Aria2cConfig, BinaryDef, YtDlpParameters,
)
from managers.tool_specs import (
    BaseTool, InstallContext, ManualInstallRequired, ToolBinary,
    TOOL_VERSION_UNKNOWN, stream_to_file, extract_zip_members,
)

if TYPE_CHECKING:
    import httpx
    from state import AppState

_log = get_logger("tools")
_UA = {"User-Agent": "Mozilla/5.0"}


# ── yt-dlp ────────────────────────────────────────────────────────────────────

class YtDlpTool(BaseTool):
    """Один self-contained бинарник, скачиваемый напрямую с GitHub Releases."""

    name = "yt-dlp"
    _DATE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}")

    def default_config(self) -> ToolConfig:
        return YtDlpConfig(
            version_url  = DEFAULT_YT_API_URL,
            download_url = DEFAULT_YT_DOWNLOAD_URL,
            chunk_size   = YT_DLP_CHUNK_SIZE,
            binaries     = {
                self.name: BinaryDef(filename="yt-dlp", version_flag="--version",
                                     is_primary=True),
            },
            parameters   = YtDlpParameters(),
        )

    def missing_runtime(self) -> bool:
        """
        На Windows скачивается self-contained yt-dlp.exe — рантайм не нужен.
        На Linux/macOS используется generic-сборка, которой нужен системный Python 3
        (self-contained сборки _linux/_macos мы не качаем). Если Python нет —
        бинарник не запустится, поэтому предупреждаем пользователя.
        """
        if os.name == "nt":
            return False
        return not (shutil.which("python3") or shutil.which("python"))

    def parse_version(self, binary: ToolBinary, output: str) -> str:
        lines = output.splitlines()
        if not lines:
            return ""
        first_token = safe_str(lines[0].split()[0]) if lines[0].split() else ""
        if first_token and self._DATE_RE.match(first_token):
            return first_token
        return safe_str(lines[0])

    async def fetch_remote_version(self, client: "httpx.AsyncClient", url: str) -> str:
        res = await client.get(url, headers=_UA)
        tag = res.json().get("tag_name")
        if not tag:
            return TOOL_VERSION_UNKNOWN
        return safe_str(tag).lstrip("v")

    async def install(self, ctx: InstallContext) -> None:
        primary = self.primary_binary(ctx.state)
        dest = os.path.join(ctx.tools_dir, f"{primary.filename}{ctx.ext}")
        await stream_to_file(ctx.client, ctx.download_url, dest, ctx.on_progress, ctx.chunk_size)
        if os.name != "nt":
            os.chmod(dest, 0o755)


# ── ffmpeg-комплект (ffmpeg + ffplay + ffprobe) ──────────────────────────────

class FfmpegTool(BaseTool):
    """
    Один логический инструмент, поставляющий три бинарника одним zip-архивом.
    Авто-установка только на Windows; на остальных ОС — подсказка пакетного менеджера.
    """

    name = "ffmpeg"
    _VERSION_RE = re.compile(r"version\s+([0-9.]+)", re.IGNORECASE)
    _FALLBACK_RE = re.compile(r"([0-9.]+)")

    def default_config(self) -> ToolConfig:
        return ToolConfig(
            version_url  = DEFAULT_FFMPEG_VERSION_URL,
            download_url = DEFAULT_FFMPEG_DOWNLOAD_URL,
            chunk_size   = FFMPEG_CHUNK_SIZE,
            binaries     = {
                self.name: BinaryDef(filename="ffmpeg",  version_flag="-version",
                                     is_primary=True),
                "ffplay":  BinaryDef(filename="ffplay",  version_flag="-version"),
                "ffprobe": BinaryDef(filename="ffprobe", version_flag="-version"),
            },
        )

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

    async def fetch_remote_version(self, client: "httpx.AsyncClient", url: str) -> str:
        res = await client.get(url, headers=_UA)
        return res.text.strip()

    async def install(self, ctx: InstallContext) -> None:
        if os.name != "nt":
            raise ManualInstallRequired(self._manual_hint())

        archive_members = {
            f"{b.filename}.exe" for b in self.binaries(ctx.state)
        }

        zip_path = os.path.join(ctx.tools_dir, "ffmpeg_temp.zip")
        try:
            await stream_to_file(ctx.client, ctx.download_url, zip_path, ctx.on_progress, ctx.chunk_size)
            ctx.on_progress(None)  # индетерминированный — идёт распаковка
            found = await asyncio.to_thread(
                extract_zip_members, zip_path, ctx.tools_dir, archive_members
            )
            if found == 0:
                raise RuntimeError("FFmpeg EXE files not found in archive")
        finally:
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except Exception:
                _log.exception("Failed to remove temporary FFmpeg archive")

    @staticmethod
    def _manual_hint() -> str:
        import sys
        if sys.platform == "darwin":
            return "brew install ffmpeg"
        return ("apt: sudo apt install ffmpeg  "
                "•  dnf: sudo dnf install ffmpeg  "
                "•  pacman: sudo pacman -S ffmpeg")


# ── aria2c (внешний загрузчик yt-dlp) ────────────────────────────────────────

class Aria2cTool(BaseTool):
    """
    Один бинарник aria2c. Релизы — на GitHub, в zip-архиве сборки под Windows
    (aria2-X.Y.Z-win-64bit-buildN.zip → внутри папки лежит aria2c.exe).
    Авто-установка только на Windows; на остальных ОС — подсказка пакетного менеджера.

    И версия, и установка опираются на releases/latest API: имя ассета содержит
    версию, поэтому прямого «latest»-URL на zip нет — нужный ассет ищется в JSON.
    """

    name = "aria2c"
    _TAG_RE     = re.compile(r"(\d+\.\d+(?:\.\d+)?)")
    _VERSION_RE = re.compile(r"version\s+([0-9.]+)", re.IGNORECASE)

    def default_config(self) -> ToolConfig:
        return Aria2cConfig(
            version_url  = DEFAULT_ARIA2_VERSION_URL,
            download_url = DEFAULT_ARIA2_DOWNLOAD_URL,
            chunk_size   = ARIA2_CHUNK_SIZE,
            binaries     = {
                self.name: BinaryDef(filename="aria2c", version_flag="--version",
                                     is_primary=True),
            },
        )

    def parse_version(self, binary: ToolBinary, output: str) -> str:
        # Первая строка вида "aria2 version 1.37.0".
        lines = output.splitlines()
        if not lines:
            return ""
        first = safe_str(lines[0])
        m = self._VERSION_RE.search(first) or self._TAG_RE.search(first)
        return safe_str(m.group(1)) if m else ""

    async def fetch_remote_version(self, client: "httpx.AsyncClient", url: str) -> str:
        res = await client.get(url, headers=_UA)
        tag = safe_str(res.json().get("tag_name"))  # "release-1.37.0"
        if not tag:
            return TOOL_VERSION_UNKNOWN
        m = self._TAG_RE.search(tag)
        return safe_str(m.group(1)) if m else TOOL_VERSION_UNKNOWN

    async def install(self, ctx: InstallContext) -> None:
        if os.name != "nt":
            raise ManualInstallRequired(self._manual_hint())

        # download_url указывает на releases/latest API — находим win-64bit zip.
        res = await ctx.client.get(ctx.download_url, headers=_UA)
        assets = res.json().get("assets", [])
        asset = next(
            (a for a in assets
             if "win-64bit" in safe_str(a.get("name"))
             and safe_str(a.get("name")).endswith(".zip")),
            None,
        )
        if not asset or not asset.get("browser_download_url"):
            raise RuntimeError("aria2c Windows build not found in release assets")

        primary = self.primary_binary(ctx.state)
        member = f"{primary.filename}.exe".lower()  # aria2c.exe внутри папки сборки

        zip_path = os.path.join(ctx.tools_dir, "aria2_temp.zip")
        try:
            await stream_to_file(ctx.client, asset["browser_download_url"],
                                 zip_path, ctx.on_progress, ctx.chunk_size)
            ctx.on_progress(None)  # индетерминированный — идёт распаковка
            found = await asyncio.to_thread(
                extract_zip_members, zip_path, ctx.tools_dir, {member}
            )
            if found == 0:
                raise RuntimeError("aria2c.exe not found in archive")
        finally:
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except Exception:
                _log.exception("Failed to remove temporary aria2 archive")

    @staticmethod
    def _manual_hint() -> str:
        import sys
        if sys.platform == "darwin":
            return "brew install aria2"
        return ("apt: sudo apt install aria2  "
                "•  dnf: sudo dnf install aria2  "
                "•  pacman: sudo pacman -S aria2")


# ── Реестр по умолчанию ───────────────────────────────────────────────────────

def build_default_tools() -> list[BaseTool]:
    """Список инструментов приложения. Порядок = порядок отображения в настройках."""
    return [YtDlpTool(), FfmpegTool(), Aria2cTool()]


DEFAULT_TOOLS: list[BaseTool] = build_default_tools()


def default_tools_config() -> Dict[str, ToolConfig]:
    """
    Дефолтная конфигурация всех инструментов — собирается из самих инструментов.
    Единый источник истины: правится только default_config() конкретного инструмента.
    """
    return {tool.name: tool.default_config() for tool in DEFAULT_TOOLS}
