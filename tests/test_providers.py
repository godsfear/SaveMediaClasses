"""Тесты провайдеров: парсинг прогресса, сборка команд, реестр, торрент-утилиты."""

import hashlib
import os
from types import SimpleNamespace

import pytest

from managers.providers import (
    PROVIDERS, DEFAULT_PROVIDER, provider_factories, resolve_provider_for_url,
    YtDlpProvider, Aria2cProvider,
    content_hash, torrent_name, torrent_infohash, _bdecode,
)
from managers.snapshot import DownloadSnapshot
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


def test_ytdlp_output_template_respects_download_path(paths):
    p = YtDlpProvider(paths)
    s = snap("https://youtu.be/x", download_path="C:/dl", clean_titles=True)
    cmd = p.build_command("yt-dlp.exe", s)
    template = cmd[cmd.index("-o") + 1]
    assert template == os.path.join("C:/dl", "%(title)s.%(ext)s")


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
