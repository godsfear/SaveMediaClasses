import asyncio
import os
import re
import subprocess
import zipfile

import httpx

from config import safe_str, safe_int


class ToolsManager:

    def __init__(self, base_dir: str, tools_dir: str) -> None:
        self.base_dir  = base_dir
        self.tools_dir = tools_dir
        self.yt_needs_update     = False
        self.ffmpeg_needs_update = False
        self._ext = ".exe" if os.name == "nt" else ""

    def resolve_tool_path(self, filename: str) -> str:
        p_tools = os.path.join(self.tools_dir, filename)
        return p_tools if os.path.exists(p_tools) else ""

    # Оригинальная get_local_tool_version
    async def get_local_tool_version(self, tool_path: str, tool_name: str) -> str:
        if not tool_path or not os.path.exists(tool_path):
            return "Отсутствует"
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
            return "[Не определена]"
        except Exception:
            return "[Ошибка вызова]"

    # Оригинальная check_tools
    async def check_all(self, yt_api_url: str, ffmpeg_version_url: str, proxy_url: str | None,
                        on_local_version, on_remote_done) -> None:
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

        async with httpx.AsyncClient(proxy=proxy_url, timeout=5.0) as client:
            try:
                res = await client.get(yt_api_url, headers={"User-Agent": "Mozilla/5.0"})
                remote_yt = safe_str(res.json().get("tag_name", "Неизвестно")).lstrip('v')
            except Exception:
                remote_yt = "[Ошибка]"
            try:
                res = await client.get(ffmpeg_version_url, headers={"User-Agent": "Mozilla/5.0"})
                remote_ff = res.text.strip()
            except Exception:
                remote_ff = "[Ошибка]"

        for filename, (name,) in tools_map.items():
            loc = local_versions.get(name, "Отсутствует")
            rem = remote_yt if name == "yt-dlp" else remote_ff
            on_remote_done(name, loc, rem)

            is_equal = (loc == rem) or (
                "[" not in rem and "[" not in loc
                and "Ошибка" not in rem and "Отсутствует" not in loc
                and (rem in loc or loc in rem)
            )

            if "Отсутствует" in loc:
                if "Ошибка" not in rem and rem != "[Ошибка]":
                    if name == "yt-dlp":   self.yt_needs_update     = True
                    elif name == "ffmpeg": self.ffmpeg_needs_update = True
            elif "[" in loc or "Ошибка" in rem or "[" in rem:
                pass  # AMBER — не обновляем
            elif not is_equal:
                if name == "yt-dlp":   self.yt_needs_update     = True
                elif name == "ffmpeg": self.ffmpeg_needs_update = True

    # Оригинальная update_tools — единый клиент на весь блок
    async def update_all(self, proxy_url: str | None, yt_download_url: str, ffmpeg_download_url: str,
                         on_yt_status, on_ff_status, on_progress, on_done) -> None:
        ext = self._ext
        had_errors = False

        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=30.0, follow_redirects=True) as client:

                # ── yt-dlp ────────────────────────────────────────────────────
                if self.yt_needs_update:
                    on_yt_status("yt-dlp: Скачивание релиза...", "orange")
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
                                        on_progress(f"Загрузка yt-dlp: {pct}%", pct / 100)

                        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                            raise RuntimeError("yt-dlp скачан пустым файлом")

                        os.replace(temp_path, final_path)
                        if os.name != "nt":
                            os.chmod(final_path, 0o755)
                        on_yt_status("yt-dlp: Обновление завершено", "ok")
                    except Exception as err:
                        had_errors = True
                        on_yt_status(f"yt-dlp: Ошибка ({err})", "error")
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception:
                            pass

                # ── ffmpeg ────────────────────────────────────────────────────
                if self.ffmpeg_needs_update and os.name == "nt":
                    on_ff_status("ffmpeg: Скачивание пакета...", "orange")
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
                                        on_progress(f"Загрузка FFmpeg: {pct}%", pct / 100)

                        if not os.path.exists(temp_zip) or os.path.getsize(temp_zip) == 0:
                            raise RuntimeError("Архив FFmpeg пуст")

                        os.replace(temp_zip, zip_path)
                        on_progress("Архив получен. Распаковка...", None)

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
                                raise RuntimeError("EXE файлы FFmpeg не найдены")

                        await asyncio.to_thread(extract_zip)
                        on_ff_status("ffmpeg: Обновление завершено", "ok")
                    except Exception as err:
                        had_errors = True
                        on_ff_status(f"ffmpeg: Ошибка ({err})", "error")
                        try:
                            if os.path.exists(temp_zip): os.remove(temp_zip)
                            if os.path.exists(zip_path): os.remove(zip_path)
                        except Exception:
                            pass

            on_done(had_errors)

        except Exception as err:
            on_done(had_errors=True, critical_err=str(err))
