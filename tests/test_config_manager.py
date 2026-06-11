"""Тесты ConfigManager: roundtrip save/load и мягкие миграции старых форматов."""

import json

import pytest

from config import NamedTheme, ThemeConfig, VersionState, WindowConfig
from managers.config_manager import ConfigManager
from state import AppState


@pytest.fixture(autouse=True)
def fixed_screen(monkeypatch):
    """Геометрия окна не должна зависеть от реального монитора машины CI."""
    monkeypatch.setattr(WindowConfig, "_get_screen_metrics",
                        staticmethod(lambda: (1920, 1080)))


@pytest.fixture
def mgr(tmp_path):
    return ConfigManager(str(tmp_path / "config.json"))


def test_load_missing_file_returns_defaults(mgr):
    state = mgr.load()
    assert state.download_tool == "auto"
    assert state.theme_mode == "dark"
    assert "yt-dlp" in state.tools and "aria2c" in state.tools


def test_save_load_roundtrip(mgr):
    state = AppState()
    state.download_path = "C:/custom"
    state.proxy_enabled = True
    state.download_tool = "aria2c"
    state.max_parallel  = 8
    state.theme_mode = "light"
    state.theme_light.accent_color = "123456"
    state.saved_themes["mine"] = NamedTheme(mode="light",
                                            config=ThemeConfig(bg_color="ABCDEF"))
    state.tool_versions["yt-dlp"] = VersionState(current="2025.01.01",
                                                 latest="2025.06.01", status="outdated")
    state.timeouts.thumbnail_meta = 44.0
    state.ytdlp.parameters.audio_only.state = True
    state.ytdlp.parameters.quality.value = "720p"
    state.ytdlp.parameters.subtitles.value = "auto"

    mgr.save(state)
    restored = mgr.load()

    assert restored.download_path == "C:/custom"
    assert restored.proxy_enabled is True
    assert restored.download_tool == "aria2c"
    assert restored.max_parallel == 8
    assert restored.theme_mode == "light"
    assert restored.theme_light.accent_color == "123456"
    assert restored.saved_themes["mine"].config.bg_color == "ABCDEF"
    assert restored.tool_versions["yt-dlp"].status == "outdated"
    assert restored.timeouts.thumbnail_meta == 44.0
    assert restored.ytdlp.parameters.audio_only.state is True
    assert restored.ytdlp.parameters.quality.value == "720p"
    assert restored.ytdlp.parameters.subtitles.value == "auto"


def test_max_parallel_clamped_on_load(mgr):
    _write(mgr, {"settings": {"max_parallel": 9999}})
    assert mgr.load().max_parallel == 50          # MAX_PARALLEL_CEILING
    _write(mgr, {"settings": {"max_parallel": 0}})
    assert mgr.load().max_parallel == 1
    _write(mgr, {"settings": {"max_parallel": "junk"}})
    assert mgr.load().max_parallel == 5           # дефолт


def test_corrupt_file_falls_back_to_defaults(mgr):
    with open(mgr.config_file, "w", encoding="utf-8") as f:
        f.write("{not json!!!")
    state = mgr.load()
    assert state.theme_mode == "dark"


def _write(mgr, data: dict) -> None:
    with open(mgr.config_file, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_legacy_single_theme_becomes_dark(mgr):
    """Старейший формат: "theme" = одна палитра → тёмная."""
    _write(mgr, {"theme": {"accent_color": "FF0000"}})
    state = mgr.load()
    assert state.theme_dark.accent_color == "FF0000"
    assert state.theme_mode == "dark"
    # Светлая достроена из дефолтов
    assert state.theme_light == ThemeConfig.light_default()


def test_transitional_theme_keys_in_root(mgr):
    _write(mgr, {
        "theme_mode": "light",
        "theme_dark": {"accent_color": "111111"},
        "theme_light": {"accent_color": "222222"},
        "saved_themes": {"x": {"mode": "light", "colors": {"bg_color": "EEEEEE"}}},
    })
    state = mgr.load()
    assert state.theme_mode == "light"
    assert state.theme_dark.accent_color == "111111"
    assert state.theme_light.accent_color == "222222"
    assert state.saved_themes["x"].config.bg_color == "EEEEEE"


def test_legacy_tool_versions_migrated_from_tools_section(mgr):
    """Старый формат: версии лежали внутри tools.* — собираются в tool_versions."""
    _write(mgr, {
        "tools": {
            "yt-dlp": {"current": "2024.1.1", "latest": "2024.2.2", "status": "outdated"},
            "ffmpeg": {"binaries": {
                "ffprobe": {"current": "7.0", "latest": "7.1", "status": "outdated"},
            }},
        },
    })
    state = mgr.load()
    assert state.tool_versions["yt-dlp"].current == "2024.1.1"
    assert state.tool_versions["ffprobe"].latest == "7.1"


def test_user_tool_overrides_survive_defaults_merge(mgr):
    """Пользовательский URL сохраняется, отсутствующие бинарники доезжают из дефолтов."""
    _write(mgr, {"tools": {"ffmpeg": {"version_url": "https://my.mirror/ver"}}})
    state = mgr.load()
    assert state.ffmpeg.version_url == "https://my.mirror/ver"
    assert set(state.ffmpeg.binaries) == {"ffmpeg", "ffplay", "ffprobe"}
