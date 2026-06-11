"""Тесты DownloadSnapshot: реконструкция из params, сборка из state, иммутабельность."""

import dataclasses

import pytest

from managers.snapshot import DownloadSnapshot
from state import AppState


def test_from_state_defaults():
    st = AppState()
    snap = DownloadSnapshot.from_state(st, "https://youtu.be/x")
    assert snap.url == "https://youtu.be/x"
    assert snap.download_path == st.download_path
    assert snap.playlist_flag_on == "--yes-playlist"
    assert snap.playlist_flag_off == "--no-playlist"
    # Флаги aria2c протекают из конфига инструмента
    assert "--continue=true" in snap.aria2_args
    assert snap.aria2_part_dirname == ".part"
    assert snap.seed is False


def test_from_state_resolves_quality_args():
    st = AppState()
    assert DownloadSnapshot.from_state(st, "https://x").quality_args == ""   # best
    st.ytdlp.parameters.quality.value = "1080p"
    snap = DownloadSnapshot.from_state(st, "https://x")
    assert "height<=1080" in snap.quality_args


def test_from_state_resolves_subtitles_args():
    st = AppState()
    assert DownloadSnapshot.from_state(st, "https://x").subtitles_args == ""   # off
    st.ytdlp.parameters.subtitles.value = "ru"
    assert "--sub-langs ru.*" in DownloadSnapshot.from_state(st, "https://x").subtitles_args
    st.ytdlp.parameters.subtitles.value = "auto"
    st.language = "ru"
    snap = DownloadSnapshot.from_state(st, "https://x")
    assert "--write-auto-subs" in snap.subtitles_args and "ru.*" in snap.subtitles_args


def test_from_params_filters_unknown_keys():
    snap = DownloadSnapshot.from_params(
        "magnet:?xt=urn:btih:abc",
        {"download_path": "C:/dl", "bogus_key": 1, "url": "should-be-ignored"},
    )
    assert snap.url == "magnet:?xt=urn:btih:abc"   # url из аргумента, не из params
    assert snap.download_path == "C:/dl"
    assert not hasattr(snap, "bogus_key")


def test_from_params_fills_required_defaults():
    snap = DownloadSnapshot.from_params("https://x", {})
    assert snap.proxy_enabled is False
    assert snap.cookies_browser == "none"
    assert snap.yt_dlp_args == ""


def test_snapshot_is_frozen():
    snap = DownloadSnapshot.from_params("https://x", {})
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.url = "other"     # type: ignore[misc]


def test_roundtrip_through_asdict():
    """Цикл from_state → asdict (как пишет БД) → from_params сохраняет параметры."""
    st = AppState()
    original = DownloadSnapshot.from_state(st, "https://x")
    params = dataclasses.asdict(original)
    params.pop("url")
    restored = DownloadSnapshot.from_params("https://x", params)
    assert restored == original
