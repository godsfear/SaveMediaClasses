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
import subprocess
from typing import Callable, Protocol, runtime_checkable

from app_logging import get_logger
from config import safe_str, THUMBNAIL_TIMEOUT, THUMBNAIL_SOCK_TIMEOUT
from managers.download_manager import DownloadSnapshot
from paths import AppPaths


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

    def __init__(self) -> None:
        self._ext       = ".exe" if os.name == "nt" else ""
        self._proc      = None

    # ── DownloadProvider protocol ─────────────────────────────────────────────

    def resolve_exe(self) -> str:
        path = os.path.join(AppPaths.tools_dir(), f"yt-dlp{self._ext}")
        return path if os.path.exists(path) and os.path.getsize(path) > 0 else ""

    def build_command(self, exe: str, snapshot: DownloadSnapshot) -> list[str]:
        s    = snapshot
        args = [exe]

        if s.proxy_enabled and safe_str(s.proxy_address).strip():
            args.extend(["--proxy", safe_str(s.proxy_address).strip()])

        if s.cookies_enabled and s.cookies_browser != "none":
            args.extend(["--cookies-from-browser", safe_str(s.cookies_browser)])

        args.append("--yes-playlist" if s.playlist_enabled else "--no-playlist")

        if s.embed_metadata:
            args.extend(["--embed-metadata", "--embed-thumbnail"])

        if s.audio_only:
            args.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
        else:
            raw = safe_str(s.yt_dlp_args).strip()
            if raw:
                try:
                    args.extend(shlex.split(raw))
                except ValueError:
                    args.extend(raw.split())

        is_pl  = "list=" in s.url.lower() or "playlist" in s.url.lower()
        t_name = "%(title)s.%(ext)s" if s.clean_titles else "%(title)s [%(id)s].%(ext)s"
        t_path = (
            os.path.join("%(playlist_title)s", "%(playlist_index)s - " + t_name)
            if s.playlist_enabled and is_pl else t_name
        )
        if s.save_to_source:  t_path = os.path.join("%(extractor_key)s", t_path)
        if s.download_path:   t_path = os.path.join(s.download_path, t_path)

        args.extend(["-o", t_path, "--newline", s.url])
        return args

    def cancel(self) -> None:
        if self._proc and self._proc.returncode is None:
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
        env["PATH"] = f"{AppPaths.tools_dir()}{sep}{AppPaths.app_dir()}{sep}{env.get('PATH', '')}"

        self._proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            startupinfo=startup,
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
        return url.startswith("http://") or url.startswith("https://")

    @classmethod
    def post_processing_tags(cls) -> list[str]:
        return cls._POST_TAGS

    async def fetch_thumbnail(self, exe: str, url: str) -> tuple:
        """
        Получить thumbnail как JPEG-байты и метаданные из yt-dlp:
          1. --dump-single-json --flat-playlist → метаданные верхнего уровня.
             Для плейлиста: _type="playlist", entries — плоский список без деталей.
             Для видео:     _type="video", thumbnails есть сразу.
          2. Thumbnail берём из самого объекта (видео) или первого entries (плейлист).
          3. urllib скачивает байты превью.
        Возвращает (bytes, meta_dict).
        """
        import json as _json
        import urllib.request

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

            # Скачиваем байты в потоке — не блокируем event loop
            def _download() -> bytes:
                req = urllib.request.Request(
                    thumb_url,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(req, timeout=THUMBNAIL_SOCK_TIMEOUT) as resp:
                    return resp.read()

            raw = await asyncio.wait_for(
                asyncio.to_thread(_download),
                timeout=THUMBNAIL_TIMEOUT,
            )
            return (raw if raw else b""), data

        except Exception:
            get_logger(self.SOURCE_NAME).warning("Failed to fetch thumbnail metadata", exc_info=True)
            return b"", {}
