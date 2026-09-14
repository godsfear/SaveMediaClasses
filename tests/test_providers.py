"""Тесты провайдеров: парсинг прогресса, сборка команд, реестр, торрент-утилиты."""

import asyncio
import hashlib
import os
from types import SimpleNamespace

import pytest

import managers.providers as providers_module
from managers.providers import (
    PROVIDERS, DEFAULT_PROVIDER, provider_factories, resolve_provider_for_url,
    YtDlpProvider, Aria2cProvider,
    content_hash, torrent_name, torrent_infohash, _bdecode, _decode_cli_output,
)
from managers.snapshot import DownloadSnapshot
from managers.tool_resolver import ToolLocation, ToolOrigin
from state import AppState


@pytest.fixture
def paths():
    return SimpleNamespace(tools_dir="C:/tools", app_dir="C:/app")


def snap(url: str, **overrides) -> DownloadSnapshot:
    base = DownloadSnapshot.from_state(AppState(), url)
    import dataclasses
    return dataclasses.replace(base, **overrides) if overrides else base


# ── Реестр ────────────────────────────────────────────────────────────────────

def test_registry_keys_match_source_names():
    assert set(PROVIDERS) == {"yt-dlp", "aria2c"}
    for key, cls in PROVIDERS.items():
        assert cls.SOURCE_NAME == key
    assert DEFAULT_PROVIDER in PROVIDERS


def test_provider_factories_create_fresh_instances(paths):
    facs = provider_factories(paths)
    a, b = facs["aria2c"](), facs["aria2c"]()
    assert a is not b                       # один экземпляр = одна загрузка


@pytest.mark.parametrize("url,expected", [
    ("magnet:?xt=urn:btih:abc",        "aria2c"),
    ("https://ex.com/file.iso",        "aria2c"),
    ("https://ex.com/file.zip?sig=1",  "aria2c"),   # query отбрасывается
    ("C:/dir/file.torrent",            "aria2c"),
    ("https://youtube.com/watch?v=1",  "yt-dlp"),
    ("https://ex.com/page",            "yt-dlp"),
])
def test_resolve_provider_for_url(url, expected):
    assert resolve_provider_for_url(url) == expected


# ── yt-dlp ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("line,expected", [
    ("[download]  37.5% of 10MiB at 2MiB/s",  0.375),
    ("[download] 100.0% of ~5MiB",            1.0),
    ("[Merger] Merging formats",              None),
    ("random text 50%",                       None),   # без [download]
])
def test_ytdlp_parse_progress(line, expected):
    assert YtDlpProvider.parse_progress(line) == expected


def test_ytdlp_format_status_strips_tag():
    assert YtDlpProvider.format_status("[download]  37.5% of 10MiB") == "37.5% of 10MiB"


def test_ytdlp_recognizes_youtube_authentication_failure(paths):
    output = (
        "ERROR: [youtube] x: Sign in to confirm you’re not a bot. "
        "Use --cookies-from-browser or --cookies for the authentication."
    )
    assert YtDlpProvider(paths).failure_reason(output) == "youtube_auth_required"


def test_ytdlp_recognizes_mojibake_authentication_failure(paths):
    output = "ERROR: Sign in to confirm you�re not a bot"
    assert YtDlpProvider(paths).failure_reason(output) == "youtube_auth_required"


def test_cli_output_falls_back_from_utf8_to_windows_codepage():
    assert _decode_cli_output(b"you\x92re") == "you’re"


def test_ytdlp_build_command_basic(paths):
    p = YtDlpProvider(paths)
    s = snap("https://youtu.be/x")
    cmd = p.build_command("yt-dlp.exe", s)
    assert cmd[0] == "yt-dlp.exe"
    assert cmd[-1] == "https://youtu.be/x"
    assert "--newline" in cmd
    assert "--no-playlist" in cmd           # плейлист выключен по умолчанию
    assert "--proxy" not in cmd             # прокси выключен


def test_ytdlp_build_command_proxy_cookies_audio(paths):
    p = YtDlpProvider(paths)
    s = snap("https://youtu.be/x",
             proxy_enabled=True, proxy_address="socks5://127.0.0.1:1080",
             cookies_enabled=True, cookies_browser="firefox",
             audio_only=True)
    cmd = p.build_command("yt-dlp.exe", s)
    assert ["--proxy", "socks5://127.0.0.1:1080"] == cmd[1:3]
    assert "--cookies-from-browser" in cmd and "firefox" in cmd
    assert "-x" in cmd                       # audio_flags вместо extra_args
    assert "bestvideo+bestaudio/best" not in cmd


def test_ytdlp_quality_preset_appended_after_extra_args(paths):
    """Пресет качества идёт ПОСЛЕ extra_args — его -f переопределяет формат."""
    p = YtDlpProvider(paths)
    s = snap("https://youtu.be/x",
             yt_dlp_args="-f bestvideo+bestaudio/best --merge-output-format mp4",
             quality_args="-f bestvideo[height<=1080]+bestaudio/best[height<=1080]")
    cmd = p.build_command("yt-dlp.exe", s)
    f_positions = [i for i, a in enumerate(cmd) if a == "-f"]
    assert len(f_positions) == 2
    assert cmd[f_positions[-1] + 1].startswith("bestvideo[height<=1080]")  # последний -f — пресет
    assert "--merge-output-format" in cmd                                  # extra_args действуют


def test_ytdlp_best_preserves_custom_format(paths):
    """Пресет "best" (пустые args) не перебивает пользовательский -f из extra_args."""
    p = YtDlpProvider(paths)
    s = snap("https://youtu.be/x", yt_dlp_args="-f mycustom", quality_args="")
    cmd = p.build_command("yt-dlp.exe", s)
    assert cmd.count("-f") == 1
    assert cmd[cmd.index("-f") + 1] == "mycustom"


def test_ytdlp_default_command_has_single_format_source(paths):
    """С дефолтными настройками формат не задаётся вовсе (yt-dlp сам берёт best)."""
    p = YtDlpProvider(paths)
    cmd = p.build_command("yt-dlp.exe", snap("https://youtu.be/x"))
    assert "-f" not in cmd
    assert "--merge-output-format" in cmd


def test_ytdlp_quality_ignored_in_audio_mode(paths):
    p = YtDlpProvider(paths)
    s = snap("https://youtu.be/x", audio_only=True,
             quality_args="-f bestvideo[height<=1080]")
    cmd = p.build_command("yt-dlp.exe", s)
    assert not any("height<=1080" in a for a in cmd)
    assert "-x" in cmd


def test_ytdlp_subtitles_in_video_mode_only(paths):
    p = YtDlpProvider(paths)
    subs = "--embed-subs --sub-langs ru.*"
    cmd = p.build_command("yt-dlp.exe", snap("https://youtu.be/x", subtitles_args=subs))
    assert "--embed-subs" in cmd and "ru.*" in cmd
    # В аудио-режиме субтитры не передаются
    cmd_audio = p.build_command(
        "yt-dlp.exe", snap("https://youtu.be/x", audio_only=True, subtitles_args=subs))
    assert "--embed-subs" not in cmd_audio


def test_ytdlp_output_template_respects_download_path(paths):
    p = YtDlpProvider(paths)
    s = snap("https://youtu.be/x", download_path="C:/dl", clean_titles=True)
    cmd = p.build_command("yt-dlp.exe", s)
    template = cmd[cmd.index("-o") + 1]
    assert template == os.path.join("C:/dl", "%(title)s.%(ext)s")


class FakeResolver:
    """resolve/system без файловой системы; managed — выбранные fallback-копии."""

    def __init__(self, managed=(), system=()):
        self._managed, self._system = set(managed), set(system)

    def resolve(self, name):
        if name in self._managed:
            return ToolLocation(f"C:/tools/{name}.exe", ToolOrigin.MANAGED)
        return self.system(name)

    def system(self, name):
        if name in self._system:
            return ToolLocation(f"C:/sys/{name}.exe", ToolOrigin.SYSTEM)
        return ToolLocation()

    def process_env(self):
        return {}


def test_ytdlp_passes_managed_fallbacks_shadowed_by_system_path(paths):
    """PATH нашёл бы устаревшие системные ffmpeg/deno — пути передаются явно."""
    resolver = FakeResolver(managed={"ffmpeg", "deno"}, system={"ffmpeg", "deno"})
    cmd = YtDlpProvider(paths, resolver).build_command("yt-dlp.exe", snap("https://youtu.be/x"))
    assert cmd[cmd.index("--ffmpeg-location") + 1] == "C:/tools/ffmpeg.exe"
    assert cmd[cmd.index("--js-runtimes") + 1] == "deno:C:/tools/deno.exe"


@pytest.mark.parametrize("resolver", [
    FakeResolver(system={"ffmpeg", "deno"}),    # системные актуальны
    FakeResolver(managed={"ffmpeg", "deno"}),   # системных нет — PATH найдёт tools
])
def test_ytdlp_leaves_tool_lookup_to_path_when_it_matches(paths, resolver):
    cmd = YtDlpProvider(paths, resolver).build_command("yt-dlp.exe", snap("https://youtu.be/x"))
    assert "--ffmpeg-location" not in cmd and "--js-runtimes" not in cmd


def test_ytdlp_metadata_request_uses_download_proxy_and_cookies(paths, monkeypatch):
    seen = []

    async def fake_exec(*argv, **kwargs):
        seen.append(argv)
        raise OSError("stop after argv")    # fetch_thumbnail сбой не пробрасывает

    monkeypatch.setattr(providers_module.asyncio, "create_subprocess_exec", fake_exec)
    s = snap("https://youtu.be/x", proxy_enabled=True, proxy_address="http://proxy:3128",
             cookies_enabled=True, cookies_browser="firefox")

    result = asyncio.run(YtDlpProvider(paths, FakeResolver()).fetch_thumbnail("yt-dlp.exe", s))

    argv = seen[0]
    assert result == (b"", {})
    assert argv[argv.index("--proxy") + 1] == "http://proxy:3128"
    assert argv[argv.index("--cookies-from-browser") + 1] == "firefox"
    assert argv[-1] == "https://youtu.be/x"


def test_cancel_during_process_start_still_kills_process(paths, monkeypatch):
    """pause/cancel, пришедшие пока процесс создаётся (_proc ещё пуст), не теряются."""
    provider = YtDlpProvider(paths, FakeResolver())
    kills = []

    async def eof(_size):
        return b""

    class FakeProc:
        pid, returncode = 4242, None
        stdout = SimpleNamespace(read=eof)

        async def wait(self):
            self.returncode = 1

    async def fake_exec(*argv, **kwargs):
        provider.cancel()                   # убивать ещё нечего
        return FakeProc()

    monkeypatch.setattr(providers_module.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(providers_module.subprocess, "run", lambda args, **kw: kills.append(args))
    monkeypatch.setattr(providers_module.os, "getpgid", lambda pid: pid, raising=False)
    monkeypatch.setattr(providers_module.os, "killpg", lambda pgid, sig: kills.append(pgid),
                        raising=False)

    asyncio.run(provider.run(["yt-dlp.exe"], lambda line: None, lambda rc: None))

    assert len(kills) == 1


# ── aria2c ────────────────────────────────────────────────────────────────────

def test_aria2_parse_progress_plain(paths):
    p = Aria2cProvider(paths)
    p.build_command("aria2c.exe", snap("https://ex.com/f.zip", download_path="C:/dl"))
    assert p.parse_progress("[#7d2e8c 4.5MiB/10MiB(45%) CN:5 DL:2.3MiB ETA:2s]") == 0.45
    assert p.parse_progress("[#7d2e8c SEED(0.0) CN:2]") is None       # сидинг
    assert p.parse_progress("plain notice line") is None              # не сводка


def test_aria2_magnet_metadata_phase_suppressed(paths):
    p = Aria2cProvider(paths)
    p.build_command("aria2c.exe", snap("magnet:?xt=urn:btih:abc", download_path="C:/dl"))
    # Первый GID — метаданные: его 100% подавляется
    assert p.parse_progress("[#aaaa11 15KiB/15KiB(100%)]") is None
    # Второй GID — контент: прогресс идёт
    assert p.parse_progress("[#bbbb22 1MiB/10MiB(10%)]") == 0.10


def test_aria2_build_command_uses_part_dir(paths):
    p = Aria2cProvider(paths)
    url = "https://ex.com/f.zip"
    cmd = p.build_command("aria2c.exe", snap(url, download_path="C:/dl"))
    part_id = hashlib.sha256(url.encode()).hexdigest()[:16]
    assert p.temp_dir() == os.path.join("C:/dl", ".part", part_id)
    assert f"--dir={p.temp_dir()}" in cmd


@pytest.mark.parametrize("url,expected", [
    ("magnet:?xt=urn:btih:abc",      True),    # хеши кусков есть в метаданных
    ("C:/dir/file.torrent",          True),
    ("C:/dir/file.metalink",         True),
    ("https://ex.com/f.zip",         False),   # у http контрольных сумм нет
])
def test_aria2_check_integrity_only_for_hashed_content(paths, url, expected):
    """Брошенная торрент-загрузка без .aria2 сверяется по хешам, а не качается
    заново; http-ссылкам флаг не добавляется (он там не имеет эффекта)."""
    p = Aria2cProvider(paths)
    cmd = p.build_command("aria2c.exe", snap(url, download_path="C:/dl"))
    assert ("--check-integrity=true" in cmd) is expected


def test_aria2_seed_mode_no_part_dir(paths):
    p = Aria2cProvider(paths)
    cmd = p.build_command("aria2c.exe",
                          snap("magnet:?xt=urn:btih:abc", download_path="C:/dl", seed=True))
    assert p.temp_dir() == ""                       # раздача идёт из самой папки
    assert "--dir=C:/dl" in cmd
    assert any("--check-integrity=true" in a for a in cmd)


def test_aria2_format_status():
    line = "[#7d2e8c 166MiB/378MiB(44%) CN:5 DL:2.3MiB ETA:2s]"
    assert Aria2cProvider.format_status(line) == "166MiB/378MiB  •  2.3MiB/s  •  ETA 2s"


@pytest.mark.parametrize("url,valid", [
    ("https://ex.com/f.zip", True),
    ("magnet:?xt=urn:btih:a", True),
    ("C:/dir/file.torrent",   True),
    ("not-a-url",             False),
])
def test_aria2_is_valid_url(url, valid):
    assert Aria2cProvider.is_valid_url(url) is valid


# ── Финальный путь файла ──────────────────────────────────────────────────────

def test_ytdlp_observe_line_tracks_final_path(paths):
    p = YtDlpProvider(paths)
    assert p.final_path() == ""
    p.observe_line(r"[download] Destination: C:\dl\video.f137.mp4")
    p.observe_line("[download]  45.0% of 10MiB")              # прогресс не путает
    p.observe_line(r'[Merger] Merging formats into "C:\dl\video.mp4"')
    assert p.final_path() == r"C:\dl\video.mp4"               # последняя фаза побеждает


def test_ytdlp_observe_line_audio_and_existing(paths):
    p = YtDlpProvider(paths)
    p.observe_line(r"[ExtractAudio] Destination: C:\dl\song.mp3")
    assert p.final_path() == r"C:\dl\song.mp3"
    p2 = YtDlpProvider(paths)
    p2.observe_line(r"[download] C:\dl\old.mp4 has already been downloaded")
    assert p2.final_path() == r"C:\dl\old.mp4"


def test_aria2_move_to_final_sets_path(paths, tmp_path):
    p = Aria2cProvider(paths)
    part  = tmp_path / "part"; part.mkdir()
    final = tmp_path / "dl";   final.mkdir()
    (part / "movie.mkv").write_bytes(b"data")
    (part / "movie.mkv.aria2").write_bytes(b"ctrl")           # контрольный пропускается
    p._part_dir, p._final_dir = str(part), str(final)
    p._move_to_final()
    assert p.final_path() == str(final / "movie.mkv")
    assert (final / "movie.mkv").exists()
    assert not (final / "movie.mkv.aria2").exists()


def test_aria2_move_multiple_files_points_to_dir(paths, tmp_path):
    p = Aria2cProvider(paths)
    part  = tmp_path / "part"; part.mkdir()
    final = tmp_path / "dl";   final.mkdir()
    (part / "a.bin").write_bytes(b"1")
    (part / "b.bin").write_bytes(b"2")
    p._part_dir, p._final_dir = str(part), str(final)
    p._move_to_final()
    assert p.final_path() == str(final)                       # несколько → папка


@pytest.mark.parametrize("name,container", [
    ("Shared", "Shared (1)"),         # торрент с корневой папкой
    ("movie.mkv", "movie (1)"),       # однофайловый торрент
])
def test_aria2_name_conflict_keeps_user_data_and_seedable_layout(
    paths, tmp_path, name, container,
):
    """Занятое имя: чужие данные целы, результат — в «name (1)/» под исходным именем,
    и раздача (aria2 ищет контент по имени из торрента) смотрит именно туда."""
    part, final = tmp_path / "part", tmp_path / "dl"
    rel = name if "." in name else f"{name}/file.bin"
    for root, payload in ((final, b"user"), (part, b"torrent")):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(payload)
    p = Aria2cProvider(paths)
    p._part_dir, p._final_dir = str(part), str(final)

    p._move_to_final()

    assert (final / rel).read_bytes() == b"user"
    assert (final / container / rel).read_bytes() == b"torrent"
    assert p.final_path() == str(final / container / name)
    assert Aria2cProvider.seed_dir(str(final), p.final_path()) == str(final / container)


def test_aria2_seed_dir_without_conflict_is_download_dir(tmp_path):
    final = str(tmp_path / "dl")
    assert Aria2cProvider.seed_dir(final, os.path.join(final, "movie.mkv")) == final
    assert Aria2cProvider.seed_dir(final, "") == final          # старые записи без file_path


@pytest.mark.parametrize("escape", ["..", "absolute"])
def test_aria2_clean_temp_never_leaves_download_dir(tmp_path, escape):
    """Имя служебной папки из конфига не уводит удаление за пределы <download>."""
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    sibling = tmp_path / "0123456789abcdef"     # имя как у задания, но вне папки
    sibling.mkdir()
    part_dirname = ".." if escape == ".." else str(tmp_path)

    assert Aria2cProvider.clean_temp_dirs(str(downloads), part_dirname=part_dirname) == (0, 0)
    assert downloads.exists() and sibling.exists()


def test_aria2_clean_temp_removes_only_inactive_job_dirs(tmp_path):
    part = tmp_path / ".part"
    job, active, foreign = part / "0123456789abcdef", part / "fedcba9876543210", part / "notes"
    for folder in (job, active, foreign):
        folder.mkdir(parents=True)
    (job / "chunk.bin").write_bytes(b"12345")

    assert Aria2cProvider.clean_temp_dirs(str(tmp_path), exclude={str(active)}) == (1, 5)
    assert not job.exists() and active.exists() and foreign.exists()


# ── Торрент-утилиты ───────────────────────────────────────────────────────────

def test_bdecode_roundtrip():
    data = b"d4:infod4:name3:foo6:lengthi42ee4:listl1:a1:bee"
    decoded, _ = _bdecode(data)
    assert decoded[b"info"][b"name"] == b"foo"
    assert decoded[b"info"][b"length"] == 42
    assert decoded[b"list"] == [b"a", b"b"]


def test_torrent_name_and_infohash(tmp_path):
    info = b"d4:name8:My Moviee"
    torrent = b"d4:info" + info + b"e"
    path = tmp_path / "x.torrent"
    path.write_bytes(torrent)
    assert torrent_name(str(path)) == "My Movie"
    assert torrent_infohash(str(path)) == hashlib.sha1(info).hexdigest()


def test_content_hash_dispatch(tmp_path):
    assert content_hash("magnet:?xt=urn:btih:DEAD") == "dead"
    assert content_hash("https://ex.com/page") == ""
    info = b"d4:name1:xe"
    path = tmp_path / "y.torrent"
    path.write_bytes(b"d4:info" + info + b"e")
    # btih локального .torrent совпадает с алгоритмом infohash
    assert content_hash(str(path)) == hashlib.sha1(info).hexdigest()
