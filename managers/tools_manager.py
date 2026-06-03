import asyncio
import os
import re
import subprocess
import zipfile
from typing import Callable, Optional

# ── Sentinel-константы статусов версий (не для отображения) ──────────────────
# Используются в бизнес-логике; перевод на язык UI происходит в settings_screen.
TOOL_VERSION_MISSING    = ""         # бинарник не найден (falsy → UI подставит перевод)
TOOL_VERSION_CALL_ERROR = "\x00CALL"  # ошибка вызова --version
TOOL_VERSION_REMOTE_ERR = "\x00NET"   # сетевая ошибка при запросе удалённой версии
TOOL_VERSION_UNKNOWN    = "\x00UNK"   # ответ API не содержит поля с версией

import httpx

from app_logging import get_logger
from config import safe_str, safe_int

# ── Типизированные алиасы коллбэков ──────────────────────────────────────────
# check_all
OnLocalVersion = Callable[[str, str], None]        # (tool_name, local_version)
OnRemoteDone   = Callable[[str, str, str], None]   # (tool_name, local, remote)

# update_all
OnToolStatus = Callable[[str, str], None]          # (status_code, detail)  code: "downloading"|"ok"|"error"
OnProgress   = Callable[[Optional[float]], None]   # pct 0.0–1.0, или None = индетерминированный
OnDone       = Callable[..., None]                 # (had_errors: bool, critical_err: str = "")


class ToolsManager:

    def __init__(self, base_dir: str, tools_dir: str) -> None:
        self.base_dir  = base_dir
        self.tools_dir = tools_dir
        self.yt_needs_update     = False
        self.ffmpeg_needs_update = False
        self._ext = ".exe" if os.name == "nt" else ""
        self._log = get_logger("tools")

    def resolve_tool_path(self, filename: str) -> str:
        p_tools = os.path.join(self.tools_dir, filename)
        return p_tools if os.path.exists(p_tools) else ""

    # Оригинальная get_local_tool_version
    async def get_local_tool_version(self, tool_path: str, tool_name: str) -> str:
        if not tool_path or not os.path.exists(tool_path):
            return TOOL_VERSION_MISSING
        try:
            proc_startup = None
            if os.name == "nt":
                proc_startup = subprocess.STARTUPINFO()
                proc_startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            proc = await asyncio.create_subprocess_exec(
                tool_path,
                "--version" if tool_name == "yt-dlp" else "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                startupinfo=proc_startup
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            output = stdout_bytes.decode('utf-8', errors='replace').strip()

            if tool_name == "yt-dlp":
                lines = output.splitlines()
                if lines:
                    fw = safe_str(lines[0].split()[0])
                    if re.match(r"^\d{4}\.\d{2}\.\d{2}", fw):
                        return fw
                    return safe_str(lines[0])
            else:
                lines = output.splitlines()
                if lines:
                    fl = safe_str(lines[0])
                    match = re.search(r"version\s+([0-9.]+)", fl, re.IGNORECASE) or re.search(r"([0-9.]+)", fl)
                    if match:
                        return safe_str(match.group(1))
                    return safe_str(fl.split()[0])
            return TOOL_VERSION_CALL_ERROR
        except Exception:
            self._log.exception("Failed to get local version for %s", tool_name)
            return TOOL_VERSION_CALL_ERROR

    # Оригинальная check_tools
    async def check_all(self, yt_api_url: str, ffmpeg_version_url: str, proxy_url: str | None,
                        on_local_version: OnLocalVersion,
                        on_remote_done:   OnRemoteDone) -> None:
        self.yt_needs_update     = False
        self.ffmpeg_needs_update = False

        tools_map = {
            f"yt-dlp{self._ext}":  ("yt-dlp",  ),
            f"ffmpeg{self._ext}":  ("ffmpeg",   ),
            f"ffplay{self._ext}":  ("ffplay",   ),
            f"ffprobe{self._ext}": ("ffprobe",  ),
        }

        local_versions = {}
        for filename, (name,) in tools_map.items():
            path = self.resolve_tool_path(filename)
            ver  = await self.get_local_tool_version(path, name)
            local_versions[name] = ver
            on_local_version(name, ver)

        timeout = httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            try:
                res = await asyncio.wait_for(
                    client.get(yt_api_url, headers={"User-Agent": "Mozilla/5.0"}),
                    timeout=8.0
                )
                remote_yt = safe_str(res.json().get("tag_name", TOOL_VERSION_UNKNOWN)).lstrip('v')
            except Exception:
                self._log.warning("Failed to get remote yt-dlp version", exc_info=True)
                remote_yt = TOOL_VERSION_REMOTE_ERR
            try:
                res = await asyncio.wait_for(
                    client.get(ffmpeg_version_url, headers={"User-Agent": "Mozilla/5.0"}),
                    timeout=8.0
                )
                remote_ff = res.text.strip()
            except Exception:
                self._log.warning("Failed to get remote FFmpeg version", exc_info=True)
                remote_ff = TOOL_VERSION_REMOTE_ERR

        for filename, (name,) in tools_map.items():
            loc = local_versions.get(name, TOOL_VERSION_MISSING)
            rem = remote_yt if name == "yt-dlp" else remote_ff
            on_remote_done(name, loc, rem)

            is_equal = (loc == rem) or (
                loc not in (TOOL_VERSION_CALL_ERROR, TOOL_VERSION_MISSING)
                and rem not in (TOOL_VERSION_REMOTE_ERR, TOOL_VERSION_UNKNOWN)
                and (rem in loc or loc in rem)
            )

            if loc == TOOL_VERSION_MISSING:
                if rem not in (TOOL_VERSION_REMOTE_ERR, TOOL_VERSION_UNKNOWN):
                    if name == "yt-dlp":   self.yt_needs_update     = True
                    elif name == "ffmpeg": self.ffmpeg_needs_update = True
            elif loc == TOOL_VERSION_CALL_ERROR or rem in (TOOL_VERSION_REMOTE_ERR, TOOL_VERSION_UNKNOWN):
                pass  # AMBER — не обновляем
            elif not is_equal:
                if name == "yt-dlp":   self.yt_needs_update     = True
                elif name == "ffmpeg": self.ffmpeg_needs_update = True

    # Оригинальная update_tools — единый клиент на весь блок
    async def update_all(self, proxy_url: str | None, yt_download_url: str, ffmpeg_download_url: str,
                         on_yt_status: OnToolStatus,
                         on_ff_status: OnToolStatus,
                         on_progress:  OnProgress,
                         on_done:      OnDone) -> None:
        ext = self._ext
        had_errors = False

        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=30.0, follow_redirects=True) as client:

                # ── yt-dlp ────────────────────────────────────────────────────
                if self.yt_needs_update:
                    on_yt_status("downloading", "")
                    final_path = os.path.join(self.tools_dir, f"yt-dlp{ext}")
                    temp_path  = final_path + ".part"
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        downloaded = 0
                        async with client.stream("GET", yt_download_url) as res:
                            res.raise_for_status()
                            total_size = safe_int(res.headers.get("content-length", "0"))
                            with open(temp_path, "wb") as f:
                                async for chunk in res.aiter_bytes(chunk_size=8192):
                                    if not chunk:
                                        continue
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if total_size > 0:
                                        pct = min(int(downloaded * 100 / total_size), 100)
                                        on_progress(pct / 100)

                        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                            raise RuntimeError("yt-dlp downloaded as empty file")

                        os.replace(temp_path, final_path)
                        if os.name != "nt":
                            os.chmod(final_path, 0o755)
                        on_yt_status("ok", "")
                    except Exception as err:
                        had_errors = True
                        self._log.exception("Failed to update yt-dlp")
                        on_yt_status("error", str(err))
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception:
                            self._log.exception("Failed to remove temporary yt-dlp file")

                # ── ffmpeg ────────────────────────────────────────────────────
                if self.ffmpeg_needs_update and os.name == "nt":
                    on_ff_status("downloading", "")
                    zip_path = os.path.join(self.tools_dir, "ffmpeg_temp.zip")
                    temp_zip = zip_path + ".part"
                    try:
                        if os.path.exists(temp_zip):
                            os.remove(temp_zip)
                        downloaded = 0
                        async with client.stream("GET", ffmpeg_download_url) as res:
                            res.raise_for_status()
                            total_size = safe_int(res.headers.get("content-length", "0"))
                            with open(temp_zip, "wb") as f:
                                async for chunk in res.aiter_bytes(chunk_size=16384):
                                    if not chunk:
                                        continue
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if total_size > 0:
                                        pct = min(int(downloaded * 100 / total_size), 100)
                                        on_progress(pct / 100)

                        if not os.path.exists(temp_zip) or os.path.getsize(temp_zip) == 0:
                            raise RuntimeError("FFmpeg archive is empty")

                        os.replace(temp_zip, zip_path)
                        on_progress(None)  # индетерминированный — идёт распаковка

                        def extract_zip():
                            found_files = 0
                            with zipfile.ZipFile(zip_path, "r") as zf:
                                for member in zf.namelist():
                                    name = os.path.basename(member).lower()
                                    if name in ["ffmpeg.exe", "ffplay.exe", "ffprobe.exe"]:
                                        target = os.path.join(self.tools_dir, name)
                                        with zf.open(member) as src, open(target, "wb") as dst:
                                            dst.write(src.read())
                                        found_files += 1
                            if os.path.exists(zip_path):
                                os.remove(zip_path)
                            if found_files == 0:
                                raise RuntimeError("FFmpeg EXE files not found in archive")

                        await asyncio.to_thread(extract_zip)
                        on_ff_status("ok", "")
                    except Exception as err:
                        had_errors = True
                        self._log.exception("Failed to update FFmpeg")
                        on_ff_status("error", str(err))
                        try:
                            if os.path.exists(temp_zip): os.remove(temp_zip)
                            if os.path.exists(zip_path): os.remove(zip_path)
                        except Exception:
                            self._log.exception("Failed to remove temporary FFmpeg files")

            on_done(had_errors)

        except Exception as err:
            self._log.exception("Critical tools update failure")
            on_done(had_errors=True, critical_err=str(err))
