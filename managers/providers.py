"""
providers.py — протоколы и реализации провайдеров инструментов.

DownloadProvider — протокол одного загрузчика (yt-dlp, aria2c, …).
  Один экземпляр = одна загрузка. DownloadManager создаёт через фабрику.

Добавить новый провайдер:
  1. Реализовать все методы протокола (проще — наследовать _SubprocessProvider).
  2. Добавить класс в реестр PROVIDERS внизу этого файла.
  Больше ничего менять не нужно: DownloadManager, дропдаун выбора загрузчика
  и auto-режим подхватывают реестр автоматически.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shlex
import shutil
import subprocess
from typing import Callable, ClassVar, Protocol, runtime_checkable

from app_logging import get_logger
from config import safe_str, magnet_btih, THUMBNAIL_TIMEOUT, THUMBNAIL_SOCK_TIMEOUT
from managers.snapshot import DownloadSnapshot


# ── Протокол ──────────────────────────────────────────────────────────────────

@runtime_checkable
class DownloadProvider(Protocol):
    """Контракт одного загрузчика. DownloadManager работает только с этим интерфейсом."""

    # Ключ в реестре провайдеров и метка источника в событиях/логах/БД.
    SOURCE_NAME: ClassVar[str]
    # Умеет ли провайдер pause/resume (kill процесса + докачка с --continue).
    SUPPORTS_PAUSE: ClassVar[bool]

    def resolve_exe(self) -> str:
        """Вернуть путь к исполняемому файлу или пустую строку если не найден."""
        ...

    def build_command(self, exe: str, snapshot: DownloadSnapshot) -> list[str]:
        """Собрать аргументы командной строки для запуска."""
        ...

    def cancel(self) -> None:
        """Остановить текущий процесс."""
        ...

    def temp_dir(self) -> str:
        """Временная папка текущей загрузки ('' если провайдер её не использует)."""
        ...

    async def run(self, cmd_args: list[str],
                  on_line: Callable[[str], None],
                  on_finish: Callable[[int], None]) -> None:
        """Запустить процесс, вызывать on_line на каждую строку вывода,
        on_finish с кодом возврата по завершении."""
        ...

    def parse_progress(self, line: str) -> float | None:
        """Распарсить строку вывода и вернуть прогресс 0.0–1.0 или None.
        Может быть @classmethod у провайдеров без состояния парсинга."""
        ...

    def format_status(self, line: str) -> str:
        """Превратить сырую строку прогресса в человекочитаемый статус для UI."""
        ...

    @classmethod
    def is_valid_url(cls, url: str) -> bool:
        """Проверить что URL подходит для этого провайдера."""
        ...

    @classmethod
    def post_processing_tags(cls) -> list[str]:
        """Теги строк постобработки для отображения в UI."""
        ...


# ── Общая база: запуск/останов внешнего процесса ──────────────────────────────

class _SubprocessProvider:
    """
    Базовая реализация для провайдеров, гоняющих внешний CLI-процесс.

    Инкапсулирует общее: хранение AppPaths, расширение exe, запуск процесса с
    построчным чтением stdout и кросс-платформенную отмену (taskkill /T на
    Windows, killpg на POSIX). PATH дополняется tools_dir/app_dir, чтобы процесс
    находил соседние бинарники (ffmpeg для yt-dlp и т.п.).

    Подклассы реализуют специфику: resolve_exe / build_command / parse_progress /
    is_valid_url / post_processing_tags + объявляют SOURCE_NAME.
    """

    SUPPORTS_PAUSE = False   # умеет ли провайдер pause/resume (kill + докачка)

    def __init__(self, paths) -> None:
        self._paths = paths   # AppPaths — единый источник путей
        self._ext   = ".exe" if os.name == "nt" else ""
        self._proc  = None

    def temp_dir(self) -> str:
        """По умолчанию провайдер качает сразу в папку назначения — temp-папки нет."""
        return ""

    @classmethod
    def format_status(cls, line: str) -> str:
        """По умолчанию — строка как есть. Подклассы переопределяют под свой формат."""
        return line.strip()

    def cancel(self) -> None:
        if not self._proc or self._proc.returncode is not None:
            return
        try:
            if os.name == "nt":
                # taskkill /T убивает процесс и все его дочерние (ffmpeg/aria2c и др.)
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
            # новая сессия = отдельная группа процессов; killpg убьёт процесс + детей разом
            **({} if os.name == "nt" else {"start_new_session": True}),
        )

        # Делим поток и по \n, и по \r: aria2c обновляет строку прогресса возвратом
        # каретки (\r), не переводом строки, поэтому readline() склеивал бы апдейты
        # в один блоб. \r/\n — однобайтовые в UTF-8 и не встречаются внутри
        # многобайтовых символов, поэтому режем на уровне байтов, а декодируем сегменты.
        buf = b""
        while True:
            chunk = await self._proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk
            segments = re.split(rb"[\r\n]", buf)
            buf = segments.pop()        # последний сегмент может быть неполным
            for seg in segments:
                text = seg.decode("utf-8", errors="replace").strip()
                if text:
                    on_line(text)
        tail = buf.decode("utf-8", errors="replace").strip()
        if tail:
            on_line(tail)

        await self._proc.wait()
        on_finish(self._proc.returncode)
        self._proc = None


# ── Реализация: yt-dlp ────────────────────────────────────────────────────────

class YtDlpProvider(_SubprocessProvider):
    """
    Провайдер загрузок на базе yt-dlp.
    Один экземпляр = одна загрузка.
    """

    SOURCE_NAME = "yt-dlp"
    _POST_TAGS = ["[Merger]", "[Metadata]", "[Thumbnails]", "[ExtractAudio]", "[Modify]"]

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
            # Пресет качества — ПОСЛЕ extra_args: последний -f переопределяет
            # формат, остальные флаги extra_args продолжают действовать.
            quality = safe_str(s.quality_args).strip()
            if quality:
                try:
                    args.extend(shlex.split(quality))
                except ValueError:
                    args.extend(quality.split())
            # Субтитры — только для видео (в аудиофайл их не вшить).
            subs = safe_str(s.subtitles_args).strip()
            if subs:
                try:
                    args.extend(shlex.split(subs))
                except ValueError:
                    args.extend(subs.split())

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
    def format_status(cls, line: str) -> str:
        return line.replace("[download]", "").strip()

    @classmethod
    def is_valid_url(cls, url: str) -> bool:
        return bool(url.strip())

    @classmethod
    def post_processing_tags(cls) -> list[str]:
        return cls._POST_TAGS

    async def fetch_thumbnail(self, exe: str, url: str, proxy_url: str | None = None,
                              connect_timeout: float = THUMBNAIL_SOCK_TIMEOUT,
                              read_timeout: float = THUMBNAIL_TIMEOUT,
                              meta_timeout: float = 20.0) -> tuple:
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
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=meta_timeout)
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

            timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout,
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


# ── Реализация: aria2c ────────────────────────────────────────────────────────

class Aria2cProvider(_SubprocessProvider):
    """
    Самостоятельный загрузчик прямых ссылок (HTTP/HTTPS/FTP/SFTP/magnet/metalink)
    на базе aria2c. В отличие от yt-dlp, не извлекает медиа со страниц — качает
    ровно то, на что указывает URL. Один экземпляр = одна загрузка.
    """

    SOURCE_NAME = "aria2c"
    SUPPORTS_PAUSE = True    # pause = kill процесс, resume = перезапуск с --continue
    _SCHEMES = ("http://", "https://", "ftp://", "sftp://", "magnet:", "metalink:")
    _FILE_EXTS = (".torrent", ".metalink")   # локальные файлы-задания aria2c
    # Расширения «прямых файлов» — в auto-режиме такие ссылки уходят в aria2c
    # (а ссылки на страницы без расширения — в yt-dlp).
    _DIRECT_EXTS = (
        ".torrent", ".metalink",
        ".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".zst",
        ".iso", ".img", ".dmg", ".exe", ".msi", ".deb", ".rpm", ".pkg", ".apk", ".bin",
        ".pdf", ".epub", ".mobi", ".djvu",
        ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".m4v", ".flv",
        ".mp3", ".flac", ".wav", ".m4a", ".ogg", ".opus", ".aac",
    )
    _PROGRESS_RE = re.compile(r"\((\d+)%\)")
    _SIZE_RE     = re.compile(r"(\S+)/(\S+)\(\d+%\)")   # "166MiB/378MiB(44%)"
    _DL_RE       = re.compile(r"DL:([^\s\]]+)")
    _ETA_RE      = re.compile(r"ETA:([^\s\]]+)")
    _GID_RE      = re.compile(r"\[#(\w+)")

    def __init__(self, paths) -> None:
        super().__init__(paths)
        # У magnet первая под-загрузка — это метаданные (.torrent): свой GID,
        # доходит до 100% на ~десятках КиБ. Реальный контент идёт под СЛЕДУЮЩИМ
        # GID. Чтобы бар не прыгал 100%→0%, прогресс метаданных подавляем.
        self._is_magnet = False
        self._gids: list[str] = []
        # aria2 пишет сразу в финальные имена. Чтобы папка загрузки не засорялась
        # недокачанным, качаем во временную <download>/.part/<id>, а по успеху
        # переносим содержимое в саму папку загрузки.
        self._part_dir  = ""
        self._final_dir = ""

    # ── DownloadProvider protocol ─────────────────────────────────────────────

    def temp_dir(self) -> str:
        """Временная папка <download>/.part/<id> текущей загрузки ('' для seed)."""
        return self._part_dir

    def resolve_exe(self) -> str:
        # Приоритет — наша tools_dir; фолбэк — aria2c, установленный в системе (PATH).
        path = os.path.join(self._paths.tools_dir, f"aria2c{self._ext}")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        return shutil.which("aria2c") or ""

    def build_command(self, exe: str, snapshot: DownloadSnapshot) -> list[str]:
        s    = snapshot
        self._is_magnet = safe_str(s.url).strip().lower().startswith("magnet:")
        self._gids = []   # сброс на каждый запуск: важно для resume (иначе фаза
                          # метаданных magnet не подавится — _gids уже был ≥2)

        # Режим РАЗДАЧИ: файлы уже в папке загрузки (без .part, без перемещения),
        # aria2 проверит их и начнёт сидировать (флаги из конфига, seed_args).
        if s.seed:
            self._final_dir = ""
            self._part_dir  = ""
            args = [exe, *shlex.split(safe_str(s.aria2_seed_args))]
            if safe_str(s.download_path):
                args.append(f"--dir={safe_str(s.download_path)}")
            if s.proxy_enabled and safe_str(s.proxy_address).strip():
                args.append(f"--all-proxy={safe_str(s.proxy_address).strip()}")
            args.append(s.url)
            return args

        # Фиксированные флаги aria2c берём из конфига (snapshot.aria2_args), а не
        # из кода. Их назначение важно для логики (summary-interval=0 — парсинг
        # прогресса, auto-save-interval=1 — pause/resume, continue/seed-time).
        args = [exe, *shlex.split(safe_str(s.aria2_args))]

        # Качаем во временную подпапку <part_dirname>/<id>; финал — папка загрузки.
        # id = SHA-256(url)[:16] (64 бита): детерминирован, поэтому повторное
        # добавление той же ссылки попадает в ту же папку → aria2 докачивает с
        # --continue. Разные ссылки практически не сталкиваются (коллизия ~n²/2⁶⁵).
        self._final_dir = safe_str(s.download_path)
        part_id = hashlib.sha256(safe_str(s.url).encode("utf-8")).hexdigest()[:16]
        part_dirname = safe_str(s.aria2_part_dirname) or ".part"
        self._part_dir  = (os.path.join(self._final_dir, part_dirname, part_id)
                           if self._final_dir else "")
        dl_dir = self._part_dir or self._final_dir
        if dl_dir:
            args.append(f"--dir={dl_dir}")

        # aria2c понимает http/https/ftp прокси (SOCKS не поддерживается).
        if s.proxy_enabled and safe_str(s.proxy_address).strip():
            args.append(f"--all-proxy={safe_str(s.proxy_address).strip()}")

        args.append(s.url)
        return args

    async def run(self, cmd_args: list[str],
                  on_line: Callable[[str], None],
                  on_finish: Callable[[int], None]) -> None:
        """Запуск aria2c во временную папку + перенос результата по успеху.

        Перехватываем код возврата базового run(): при rc==0 переносим
        содержимое .part/<id> в папку загрузки; провал переноса → код ошибки.
        """
        if self._part_dir:
            os.makedirs(self._part_dir, exist_ok=True)

        captured: dict[str, int] = {}
        await super().run(cmd_args, on_line, lambda rc: captured.__setitem__("rc", rc))
        rc = captured.get("rc", 1)

        if rc == 0 and self._part_dir and self._part_dir != self._final_dir:
            try:
                self._move_to_final()
            except Exception:
                get_logger(self.SOURCE_NAME).exception("Failed to move from .part to download dir")
                on_finish(1)
                return

        on_finish(rc)

    def _move_to_final(self) -> None:
        """Перенести готовые файлы из .part/<id> в папку загрузки.

        Остаточные .aria2 (контрольные) пропускаем; существующий приёмник
        перезаписываем (политика --allow-overwrite). В конце убираем временную
        подпапку и, если опустела, родительский .part."""
        os.makedirs(self._final_dir, exist_ok=True)
        for name in os.listdir(self._part_dir):
            if name.endswith(".aria2"):
                continue
            src = os.path.join(self._part_dir, name)
            dst = os.path.join(self._final_dir, name)
            if os.path.exists(dst):
                shutil.rmtree(dst, ignore_errors=True) if os.path.isdir(dst) else os.remove(dst)
            shutil.move(src, dst)
        shutil.rmtree(self._part_dir, ignore_errors=True)
        try:
            os.rmdir(os.path.dirname(self._part_dir))   # .part — только если пуста
        except OSError:
            pass

    @classmethod
    def clean_temp_dirs(cls, download_dir: str, exclude: "set[str] | None" = None,
                        part_dirname: str = ".part") -> tuple[int, int]:
        """Удалить временные подпапки <download_dir>/<part_dirname> (незавершённые/
        отложенные докачки). exclude — абсолютные пути активных загрузок, их пропускаем.

        Возвращает (число удалённых папок, освобождено байт). Имя temp-подпапки берётся
        из конфига (Aria2cConfig.part_dirname). Очистка только ручная (эта функция).
        """
        exclude = {os.path.abspath(p) for p in (exclude or set())}
        root = os.path.join(safe_str(download_dir), safe_str(part_dirname) or ".part")
        if not safe_str(download_dir) or not os.path.isdir(root):
            return (0, 0)

        removed = freed = 0
        for name in os.listdir(root):
            sub = os.path.join(root, name)
            if not os.path.isdir(sub) or os.path.abspath(sub) in exclude:
                continue
            size = _dir_size(sub)
            shutil.rmtree(sub, ignore_errors=True)
            if not os.path.exists(sub):
                removed += 1
                freed += size
        try:
            os.rmdir(root)   # убрать сам .part, если опустел
        except OSError:
            pass
        return (removed, freed)

    @classmethod
    def _is_real_progress(cls, line: str) -> bool:
        """Истинная строка прогресса контента — не сидинг и не служебная фаза.

        У magnet есть фаза скачивания метаданных и фаза сидинга — их проценты
        не относятся к прогрессу файла, иначе бар скачет на 100% и застревает.
        """
        if "SEED" in line:                 # фаза раздачи — игнорируем
            return False
        if "[#" not in line:               # не строка-сводка aria2 по загрузке
            return False
        return cls._PROGRESS_RE.search(line) is not None

    def parse_progress(self, line: str) -> float | None:
        # Строка прогресса вида: [#7d2e8c 4.5MiB/10MiB(45%) CN:5 DL:2.3MiB ETA:2s]
        if not self._is_real_progress(line):
            return None
        # magnet: пока не появился ВТОРОЙ GID, идёт фаза метаданных — её 100%
        # к прогрессу файла не относится, поэтому подавляем.
        if self._is_magnet:
            m = self._GID_RE.search(line)
            gid = m.group(1) if m else ""
            if gid and gid not in self._gids:
                self._gids.append(gid)
            if len(self._gids) < 2:
                return None
        try:
            return min(int(self._PROGRESS_RE.search(line).group(1)) / 100.0, 1.0)
        except (ValueError, AttributeError):
            return None

    @classmethod
    def format_status(cls, line: str) -> str:
        # Строка деталей под баром (процент отдельно показывает _pct_text):
        # "166MiB/378MiB  •  2.3MiB/s  •  ETA 2s" из сырой сводки aria2.
        size = cls._SIZE_RE.search(line)
        dl   = cls._DL_RE.search(line)
        eta  = cls._ETA_RE.search(line)
        parts = []
        if size: parts.append(f"{size.group(1)}/{size.group(2)}")
        if dl:   parts.append(f"{dl.group(1)}/s")
        if eta:  parts.append(f"ETA {eta.group(1)}")
        return "  •  ".join(parts)

    @classmethod
    def is_valid_url(cls, url: str) -> bool:
        # Схема (http/ftp/magnet/…) ИЛИ локальный файл-задание (.torrent/.metalink).
        u = url.strip().lower()
        return u.startswith(cls._SCHEMES) or u.endswith(cls._FILE_EXTS)

    @classmethod
    def claims_url(cls, url: str) -> bool:
        """Auto-режим: True если ссылка ведёт на ФАЙЛ/торрент (→ aria2c), иначе это
        страница для извлечения (→ yt-dlp). magnet/metalink и пути с файловым
        расширением — наши; query/fragment отбрасываем перед проверкой расширения."""
        u = url.strip().lower()
        if u.startswith(("magnet:", "metalink:")):
            return True
        path = u.split("?", 1)[0].split("#", 1)[0]
        return path.endswith(cls._DIRECT_EXTS)

    @classmethod
    def post_processing_tags(cls) -> list[str]:
        return []


# ── Реестр провайдеров — единственный источник истины ────────────────────────
#
# Ключ = SOURCE_NAME провайдера; он же ключ provider_factories в DownloadManager,
# значение дропдауна выбора загрузчика в UI и поле source в событиях/БД.
# Добавить провайдер = реализовать класс + строка здесь; UI и менеджер
# подхватывают его автоматически.

PROVIDERS: dict[str, type] = {
    YtDlpProvider.SOURCE_NAME:  YtDlpProvider,
    Aria2cProvider.SOURCE_NAME: Aria2cProvider,
}

DEFAULT_PROVIDER = YtDlpProvider.SOURCE_NAME


def provider_factories(paths) -> dict[str, Callable[[], DownloadProvider]]:
    """Фабрики провайдеров для DownloadManager (один экземпляр = одна загрузка)."""
    return {key: (lambda cls=cls: cls(paths)) for key, cls in PROVIDERS.items()}


def resolve_provider_for_url(url: str) -> str:
    """Auto-режим: ссылка на файл/торрент → aria2c, страница для извлечения → yt-dlp."""
    return (Aria2cProvider.SOURCE_NAME if Aria2cProvider.claims_url(url)
            else DEFAULT_PROVIDER)


def extract_download_urls(text: str) -> list:
    """Строки-ссылки из произвольного текста (буфер обмена): схема загрузки
    (http/https/ftp/sftp/magnet/metalink) либо файл-задание (.torrent/.metalink).
    Произвольный текст, числа, обрывки документов — отбрасываются."""
    from config import parse_url_lines
    return [u for u in parse_url_lines(text) if Aria2cProvider.is_valid_url(u)]


def _bdecode(data: bytes, i: int = 0):
    """Минимальный bencode-декодер (int/str/list/dict). Возвращает (значение, next_i)."""
    t = data[i:i + 1]
    if t == b"i":                                  # integer: i<num>e
        e = data.index(b"e", i)
        return int(data[i + 1:e]), e + 1
    if t == b"l":                                  # list: l...e
        i += 1; out = []
        while data[i:i + 1] != b"e":
            v, i = _bdecode(data, i); out.append(v)
        return out, i + 1
    if t == b"d":                                  # dict: d(key val)...e
        i += 1; out = {}
        while data[i:i + 1] != b"e":
            k, i = _bdecode(data, i)
            v, i = _bdecode(data, i)
            out[k] = v
        return out, i + 1
    colon = data.index(b":", i)                    # string: <len>:<bytes>
    n = int(data[i:colon]); start = colon + 1
    return data[start:start + n], start + n


def torrent_name(path: str) -> str:
    """Настоящее имя содержимого из .torrent (info.name) — оно в метаданных торрента
    и не зависит от того, как назван сам .torrent-файл. '' если прочитать не удалось."""
    try:
        with open(path, "rb") as f:
            meta, _ = _bdecode(f.read())
        info = meta.get(b"info", {}) if isinstance(meta, dict) else {}
        name = info.get(b"name.utf-8") or info.get(b"name")
        if isinstance(name, bytes):
            return name.decode("utf-8", "replace").strip()
    except Exception:
        get_logger("aria2c").warning("Failed to read torrent name: %s", path, exc_info=True)
    return ""


def torrent_infohash(path: str) -> str:
    """btih (v1) из .torrent: SHA-1 от ИСХОДНЫХ байтов словаря info (не перекодируем —
    иначе хеш разойдётся с реальным). Совпадает с btih из magnet того же контента.
    '' если прочитать не удалось. (v2-торренты с SHA-256 не покрываем — редкость.)"""
    try:
        with open(path, "rb") as f:
            data = f.read()
        if data[:1] != b"d":
            return ""
        i = 1
        while i < len(data) and data[i:i + 1] != b"e":
            key, i = _bdecode(data, i)
            start = i
            _val, i = _bdecode(data, i)       # сдвигает i на конец значения
            if key == b"info":
                import hashlib
                return hashlib.sha1(data[start:i]).hexdigest()
    except Exception:
        get_logger("aria2c").warning("Failed to compute torrent infohash: %s", path, exc_info=True)
    return ""


def content_hash(url: str) -> str:
    """Единый ключ контента для дедупликации (нижний регистр hex), '' если неприменимо:
    btih у magnet (из самой ссылки), infohash у локального .torrent. У http/yt-dlp хеша нет."""
    u = safe_str(url).strip()
    low = u.lower()
    if low.startswith("magnet:"):
        return magnet_btih(u)
    if low.endswith(".torrent"):
        return torrent_infohash(u)
    return ""


def _dir_size(path: str) -> int:
    """Суммарный размер файлов в каталоге (рекурсивно), байт."""
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total
