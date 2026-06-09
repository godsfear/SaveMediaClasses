"""
providers.py — протоколы и реализации провайдеров инструментов.

DownloadProvider — протокол одного загрузчика (yt-dlp, aria2c, …).
  Один экземпляр = одна загрузка. DownloadManager создаёт через фабрику.

Добавить новый провайдер:
  1. Реализовать все методы протокола.
  2. Передать фабрику в DownloadManager при создании в app.py.
  Больше ничего менять не нужно.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import subprocess
from typing import Callable, Protocol, runtime_checkable

from app_logging import get_logger
from config import safe_str, THUMBNAIL_TIMEOUT, THUMBNAIL_SOCK_TIMEOUT
from managers.download_manager import DownloadSnapshot


# ── Протокол ──────────────────────────────────────────────────────────────────

@runtime_checkable
class DownloadProvider(Protocol):
    """Контракт одного загрузчика. DownloadManager работает только с этим интерфейсом."""

    def resolve_exe(self) -> str:
        """Вернуть путь к исполняемому файлу или пустую строку если не найден."""
        ...

    def build_command(self, exe: str, snapshot: DownloadSnapshot) -> list[str]:
        """Собрать аргументы командной строки для запуска."""
        ...

    def cancel(self) -> None:
        """Остановить текущий процесс."""
        ...

    async def run(self, cmd_args: list[str],
                  on_line: Callable[[str], None],
                  on_finish: Callable[[int], None]) -> None:
        """Запустить процесс, вызывать on_line на каждую строку вывода,
        on_finish с кодом возврата по завершении."""
        ...

    @classmethod
    def parse_progress(cls, line: str) -> float | None:
        """Распарсить строку вывода и вернуть прогресс 0.0–1.0 или None."""
        ...

    @classmethod
    def is_valid_url(cls, url: str) -> bool:
        """Проверить что URL подходит для этого провайдера."""
        ...

    @classmethod
    def post_processing_tags(cls) -> list[str]:
        """Теги строк постобработки для отображения в UI."""
        ...


# ── Реализация: yt-dlp ────────────────────────────────────────────────────────

class YtDlpProvider:
    """
    Провайдер загрузок на базе yt-dlp.
    Один экземпляр = одна загрузка.
    """

    SOURCE_NAME = "yt-dlp"
    _POST_TAGS = ["[Merger]", "[Metadata]", "[Thumbnails]", "[ExtractAudio]", "[Modify]"]

    def __init__(self, paths) -> None:
        self._paths     = paths   # AppPaths — единый источник путей
        self._ext       = ".exe" if os.name == "nt" else ""
        self._proc      = None

    # ── DownloadProvider protocol ─────────────────────────────────────────────

    def resolve_exe(self) -> str:
        # Приоритет — наша tools_dir; фолбэк — yt-dlp, установленный в системе (PATH).
        path = os.path.join(self._paths.tools_dir, f"yt-dlp{self._ext}")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        return shutil.which("yt-dlp") or ""

    def build_command(self, exe: str, snapshot: DownloadSnapshot) -> list[str]:
        s    = snapshot
        args = [exe]

        if s.proxy_enabled and safe_str(s.proxy_address).strip():
            args.extend(["--proxy", safe_str(s.proxy_address).strip()])

        if s.cookies_enabled and s.cookies_browser != "none":
            args.extend([s.cookies_flag, safe_str(s.cookies_browser)])

        args.append(s.playlist_flag_on if s.playlist_enabled else s.playlist_flag_off)

        if s.embed_metadata and s.metadata_flags:
            try:
                args.extend(shlex.split(s.metadata_flags))
            except ValueError:
                args.extend(s.metadata_flags.split())

        if s.audio_only:
            if s.audio_flags:
                try:
                    args.extend(shlex.split(s.audio_flags))
                except ValueError:
                    args.extend(s.audio_flags.split())
        else:
            raw = safe_str(s.yt_dlp_args).strip()
            if raw:
                try:
                    args.extend(shlex.split(raw))
                except ValueError:
                    args.extend(raw.split())

        is_pl  = "list=" in s.url.lower() or "playlist" in s.url.lower()
        t_name = s.clean_title_template if s.clean_titles else s.title_id_template
        t_path = (
            os.path.join(s.playlist_dir_template, s.playlist_idx_prefix + t_name)
            if s.playlist_enabled and is_pl else t_name
        )
        if s.save_to_source:  t_path = os.path.join(s.source_dir_template, t_path)
        if s.download_path:   t_path = os.path.join(s.download_path, t_path)

        args.extend(["-o", t_path, "--newline", s.url])
        return args

    def cancel(self) -> None:
        if not self._proc or self._proc.returncode is not None:
            return
        try:
            if os.name == "nt":
                # taskkill /T убивает yt-dlp и все его дочерние процессы (ffmpeg и др.)
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self._proc.pid)],
                    capture_output=True,
                )
            else:
                import signal
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
        except Exception:
            try:
                self._proc.terminate()
            except Exception:
                pass

    async def run(self, cmd_args: list[str],
                  on_line: Callable[[str], None],
                  on_finish: Callable[[int], None]) -> None:
        startup = None
        if os.name == "nt":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        env = os.environ.copy()
        sep = ";" if os.name == "nt" else ":"
        env["PATH"] = f"{self._paths.tools_dir}{sep}{self._paths.app_dir}{sep}{env.get('PATH', '')}"

        self._proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            startupinfo=startup,
            # новая сессия = отдельная группа процессов; killpg убьёт yt-dlp + ffmpeg разом
            **({} if os.name == "nt" else {"start_new_session": True}),
        )
        while True:
            raw = await self._proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                on_line(line)

        await self._proc.wait()
        on_finish(self._proc.returncode)
        self._proc = None

    @classmethod
    def parse_progress(cls, line: str) -> float | None:
        if "[download]" in line and "%" in line:
            m = re.search(r"([0-9.]+)%", line)
            if m:
                try:
                    return float(m.group(1)) / 100.0
                except ValueError:
                    pass
        return None

    @classmethod
    def is_valid_url(cls, url: str) -> bool:
        return bool(url.strip())

    @classmethod
    def post_processing_tags(cls) -> list[str]:
        return cls._POST_TAGS

    async def fetch_thumbnail(self, exe: str, url: str, proxy_url: str | None = None) -> tuple:
        """
        Получить thumbnail как JPEG-байты и метаданные из yt-dlp:
          1. --dump-single-json --flat-playlist → метаданные верхнего уровня.
             Для плейлиста: _type="playlist", entries — плоский список без деталей.
             Для видео:     _type="video", thumbnails есть сразу.
          2. Thumbnail берём из самого объекта (видео) или первого entries (плейлист).
          3. httpx скачивает байты превью через proxy_url (если задан).
        Возвращает (bytes, meta_dict).
        """
        import json as _json
        import httpx

        try:
            startup = None
            if os.name == "nt":
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            proc = await asyncio.create_subprocess_exec(
                exe, "--dump-single-json", "--no-playlist", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                startupinfo=startup,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            except asyncio.TimeoutError:
                proc.kill()
                return b"", {}

            if proc.returncode != 0:
                return b"", {}

            data = _json.loads(stdout.decode("utf-8", errors="replace"))

            # Берём лучший thumbnail URL
            thumbnails = data.get("thumbnails") or []
            thumb_url = thumbnails[-1].get("url", "") if thumbnails else ""
            if not thumb_url:
                thumb_url = data.get("thumbnail", "")

            # Добавляем признак плейлиста по URL — _type из --no-playlist не несёт этой инфы
            if "list=" in url.lower() or "playlist" in url.lower():
                data["_is_playlist"] = True

            if not thumb_url:
                return b"", data

            timeout = httpx.Timeout(connect=THUMBNAIL_SOCK_TIMEOUT, read=THUMBNAIL_TIMEOUT,
                                    write=5.0, pool=5.0)
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0"},
                follow_redirects=True,
            ) as client:
                resp = await client.get(thumb_url)
                raw = resp.content

            return (raw if raw else b""), data

        except Exception:
            get_logger(self.SOURCE_NAME).warning("Failed to fetch thumbnail metadata", exc_info=True)
            return b"", {}
