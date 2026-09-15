"""Самообновление SaveMedia: разбор релиза, сравнение версий, распаковка, скрипт установки."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from managers.app_updater import (
    ASSET_NAME, EXE_NAME, build_install_script, can_self_update, extract_app,
    is_newer, parse_release,
)


def test_parse_release_picks_windows_asset_and_strips_v():
    rel = parse_release({
        "tag_name": "v1.2.0", "html_url": "https://github.com/x/releases/tag/v1.2.0",
        "assets": [{"name": "other.zip", "browser_download_url": "https://x/other.zip"},
                   {"name": ASSET_NAME, "browser_download_url": "https://x/win.zip"}],
    })
    assert (rel.version, rel.asset_url) == ("1.2.0", "https://x/win.zip")
    assert parse_release({"tag_name": "v1.2.0", "assets": []}).asset_url == ""
    assert parse_release({}) is None


@pytest.mark.parametrize("current,latest,expected", [
    ("1.0.0", "1.0.1", True),
    ("1.0.0", "1.0.0", False),
    ("1.2.0", "1.1.9", False),     # локальная сборка новее релиза — не откатываем
    ("", "1.0.1", False),          # версия неизвестна — не предлагаем
])
def test_is_newer(current, latest, expected):
    assert is_newer(current, latest) is expected


def test_extract_app_finds_exe_inside_release_folder(tmp_path):
    zip_path = tmp_path / ASSET_NAME
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(f"SaveMedia/{EXE_NAME}", b"exe")
        zf.writestr("SaveMedia/app/main.pyc", b"code")
    assert extract_app(zip_path, tmp_path / "new") == tmp_path / "new" / "SaveMedia"

    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(broken, "w") as zf:
        zf.writestr("readme.txt", b"")
    with pytest.raises(RuntimeError):
        extract_app(broken, tmp_path / "broken")


def test_self_update_needs_windows_build_folder(tmp_path):
    paths = SimpleNamespace(app_dir=tmp_path, _dir_writable=lambda path: True)
    assert not can_self_update(paths)              # запуск из исходников: exe рядом нет
    (tmp_path / EXE_NAME).write_bytes(b"exe")
    assert can_self_update(paths) is (sys.platform == "win32")


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell + robocopy")
def test_install_script_updates_program_and_keeps_user_data(tmp_path):
    """Настоящий прогон скрипта: ждёт выхода процесса, копирует поверх, не трогает
    данные пользователя и лишние файлы, убирает временную папку, запускает exe."""
    install = tmp_path / "Мои программы" / "SaveMedia"   # кириллица и пробел в пути
    work = tmp_path / "update"
    new = work / "new" / "SaveMedia"
    harmless_exe = Path(os.environ["SystemRoot"]) / "System32" / "whoami.exe"
    for root in (install, new):
        (root / "app").mkdir(parents=True)
        shutil.copy(harmless_exe, root / EXE_NAME)
    (install / "app" / "main.pyc").write_bytes(b"old")
    (new / "app" / "main.pyc").write_bytes(b"new")
    # Тот же размер и время записи (точно, до наносекунд): robocopy считает такие
    # файлы Same/Modified и пропускает (так падал CI) — установка обязана перезаписать.
    old_stat = (install / "app" / "main.pyc").stat()
    os.utime(new / "app" / "main.pyc", ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    (install / "config.json").write_bytes(b"user config")
    (install / "savemedia.db").write_bytes(b"user db")
    (new / "config.json").write_bytes(b"default config")     # окажись дефолт в архиве
    (install / "tools").mkdir()
    (install / "tools" / "yt-dlp.exe").write_bytes(b"user tool")
    (install / "old-only.dll").write_bytes(b"stale")           # лишнее не удаляется

    app = subprocess.Popen(["powershell", "-NoProfile", "-Command", "Start-Sleep -Milliseconds 800"])
    script = tmp_path / "install.ps1"
    script.write_text(build_install_script(new, install, app.pid, work, tmp_path / "update.log"),
                      encoding="utf-8-sig")
    done = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script)],
        capture_output=True, text=True, timeout=120,
    )

    assert done.returncode == 0, done.stderr
    assert app.poll() is not None                              # дождался выхода приложения
    log_file = tmp_path / "update.log"                         # Out-File в PowerShell 5.1 — UTF-16
    log = log_file.read_text(encoding="utf-16", errors="replace") if log_file.exists() else ""
    assert (install / "app" / "main.pyc").read_bytes() == b"new", log
    assert (install / "config.json").read_bytes() == b"user config"
    assert (install / "savemedia.db").read_bytes() == b"user db"
    assert (install / "tools" / "yt-dlp.exe").read_bytes() == b"user tool"
    assert (install / "old-only.dll").exists()
    assert not work.exists()


def test_installer_and_relaunched_app_get_clean_environment(tmp_path, monkeypatch):
    """Перезапущенный exe наследует окружение установщика. Хост flet берёт
    FLET_DART_BRIDGE_PORT из унаследованного окружения — с портом закрытого
    приложения окно новой версии не появлялось."""
    import managers.app_updater as app_updater
    launched = {}
    monkeypatch.setenv("FLET_DART_BRIDGE_PORT", "12345")
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", "C:/old-app-data")
    monkeypatch.setenv("PYTHONHOME", "C:/embedded-python")
    monkeypatch.setenv("SAVEMEDIA_TEST_KEEP", "1")
    monkeypatch.setattr(app_updater.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(app_updater.subprocess, "Popen",
                        lambda args, **kwargs: launched.update(kwargs))

    app_updater.start_install(tmp_path / "new", tmp_path / "install")

    names = {name.upper() for name in launched["env"]}
    assert "SAVEMEDIA_TEST_KEEP" in names and "PATH" in names
    assert not any(name.startswith("FLET_") or name == "PYTHONHOME" for name in names)
