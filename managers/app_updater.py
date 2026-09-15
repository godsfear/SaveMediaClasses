"""
managers/app_updater.py — проверка новой версии SaveMedia на GitHub и самообновление.

CI публикует сборку в GitHub Releases как SaveMedia_win64.zip (внутри — папка
SaveMedia/ с SaveMedia.exe). Самообновление — только для Windows-сборки в
записываемой папке:
  1. скачать архив релиза и распаковать во временную папку;
  2. запустить PowerShell-скрипт: он ждёт выхода приложения, копирует новые
     файлы поверх папки программы и запускает exe заново;
  3. закрыть приложение.
Копирование — robocopy /E: в папке программы ничего не удаляется, а данные
пользователя (config.json, база, лог, tools/) исключены явно. В остальных случаях
(запуск из исходников, папка только на чтение) UI открывает страницу релиза.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx

from config import safe_str
from managers.tool_specs import STATUS_OUTDATED, classify_version, stream_to_file

RELEASES_API = "https://api.github.com/repos/godsfear/SaveMediaClasses/releases/latest"
ASSET_NAME   = "SaveMedia_win64.zip"   # имя архива в .github/workflows/build-windows.yml
EXE_NAME     = "SaveMedia.exe"
# Данные портативной папки (paths.py): не перезаписываются, даже окажись они в архиве.
_KEEP_FILES = ("config.json", "savemedia.db", "savemedia.db-wal", "savemedia.db-shm",
               "savemedia.log*")
_KEEP_DIRS  = ("tools",)


@dataclass(frozen=True)
class AppRelease:
    version:   str          # "1.0.1" — без префикса v
    page_url:  str          # страница релиза на GitHub
    asset_url: str = ""     # прямая ссылка на SaveMedia_win64.zip ('' — архива нет)


def current_version(paths) -> str:
    """Версия из pyproject.toml — единый источник: из него же flet build берёт
    версию exe, а CI подставляет туда номер из тега релиза. '' если не прочитать."""
    try:
        import tomllib
        with open(paths.pyproject, "rb") as f:
            return safe_str(tomllib.load(f)["project"]["version"])
    except Exception:
        return ""


def parse_release(data: dict) -> AppRelease | None:
    """Ответ GitHub releases/latest → AppRelease; None, если тега нет."""
    tag = safe_str(data.get("tag_name")).strip()
    if not tag:
        return None
    asset = next((a for a in data.get("assets") or [] if a.get("name") == ASSET_NAME), {})
    return AppRelease(version=tag.lstrip("vV"), page_url=safe_str(data.get("html_url")),
                      asset_url=safe_str(asset.get("browser_download_url")))


def is_newer(current: str, latest: str) -> bool:
    """Релиз новее установленной версии. Неизвестная текущая — не предлагаем."""
    return bool(current) and classify_version(current, latest) == STATUS_OUTDATED


async def fetch_latest(proxy_url: str | None, timeout: float) -> AppRelease | None:
    """Последний релиз с GitHub. Сетевые ошибки пробрасываются вызывающему."""
    async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout,
                                 follow_redirects=True) as client:
        res = await client.get(RELEASES_API, headers={
            "User-Agent": "SaveMedia", "Accept": "application/vnd.github+json"})
        res.raise_for_status()
        return parse_release(res.json())


def can_self_update(paths) -> bool:
    """Обновление на месте возможно: Windows-сборка (exe в app_dir), папка записываемая."""
    app_dir = Path(paths.app_dir)
    return (sys.platform == "win32" and (app_dir / EXE_NAME).is_file()
            and paths._dir_writable(app_dir))


def _work_dir() -> Path:
    return Path(tempfile.gettempdir()) / "SaveMedia-update"


async def download_release(release: AppRelease, proxy_url: str | None, timeout: float,
                           on_progress: Callable[[Optional[float]], None]) -> Path:
    """Скачать архив релиза и распаковать во временную папку.
    Возвращает папку с новым SaveMedia.exe."""
    work = _work_dir()
    shutil.rmtree(work, ignore_errors=True)   # остатки прошлой неудачной попытки
    work.mkdir(parents=True)
    zip_path = work / ASSET_NAME
    async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout,
                                 follow_redirects=True) as client:
        await stream_to_file(client, release.asset_url, str(zip_path), on_progress,
                             chunk_size=65_536)
    on_progress(None)   # распаковка — индетерминированный прогресс
    return await asyncio.to_thread(extract_app, zip_path, work / "new")


def extract_app(zip_path: Path, dest: Path) -> Path:
    """Распаковать архив и найти папку приложения (в архиве релиза — SaveMedia/)."""
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)   # extractall отбрасывает абсолютные пути и '..'
    for exe in (dest / EXE_NAME, *dest.glob(f"*/{EXE_NAME}")):
        if exe.is_file():
            return exe.parent
    raise RuntimeError(f"{EXE_NAME} not found in {zip_path.name}")


def build_install_script(new_dir: Path, install_dir: Path, pid: int,
                         work_dir: Path, log_path: Path) -> str:
    """PowerShell-скрипт установки: дождаться выхода приложения, скопировать новые
    файлы поверх и запустить exe. Пути — в одинарных кавычках (кавычки удваиваются)."""
    def q(path) -> str:
        return "'" + str(path).replace("'", "''") + "'"
    return (
        "$ErrorActionPreference = 'Stop'\n"
        "# exe и DLL заняты, пока приложение работает. Ждём по дескриптору процесса:\n"
        "# после выхода его PID может достаться чужому процессу.\n"
        f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue\n"
        "if ($p -and -not $p.WaitForExit(60000)) { $p.Kill(); $p.WaitForExit(10000) | Out-Null }\n"
        "# Время записи новых файлов — «сейчас»: файл с тем же размером и временем robocopy\n"
        "# относит к Same/Modified и пропускает, а /IM (Modified) есть не во всех Windows.\n"
        "$now = Get-Date\n"
        f"Get-ChildItem -LiteralPath {q(new_dir)} -Recurse -File -ErrorAction SilentlyContinue |"
        " ForEach-Object { try { $_.LastWriteTime = $now } catch {} }\n"
        "# /E — копировать поверх, ничего не удаляя; данные пользователя исключены явно.\n"
        f"robocopy {q(new_dir)} {q(install_dir)} /E /IS /IT /R:10 /W:1 /NP /NFL /NDL"
        f" /XD {' '.join(_KEEP_DIRS)} /XF {' '.join(_KEEP_FILES)}"
        f" | Out-File -LiteralPath {q(log_path)}\n"
        "if ($LASTEXITCODE -lt 8) {\n"
        f"    Remove-Item -LiteralPath {q(work_dir)} -Recurse -Force -ErrorAction SilentlyContinue\n"
        "}\n"
        f"Start-Process -FilePath {q(install_dir / EXE_NAME)} -WorkingDirectory {q(install_dir)}\n"
        "exit 0\n"
    )


def start_install(new_dir: Path, install_dir: Path) -> None:
    """Запустить установщик отдельным скрытым процессом: он переживёт выход
    приложения и дождётся его. Лог robocopy — %TEMP%\\SaveMedia-update.log."""
    temp = Path(tempfile.gettempdir())
    script = build_install_script(new_dir, Path(install_dir), os.getpid(),
                                  _work_dir(), temp / "SaveMedia-update.log")
    path = temp / "SaveMedia-update.ps1"
    path.write_text(script, encoding="utf-8-sig")   # BOM: PowerShell 5.1 иначе читает как ANSI
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(path)],
        creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                       | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True,
    )
