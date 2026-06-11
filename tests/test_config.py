"""Тесты чистой логики config.py: миграции from_dict, утилиты, severity."""

import pytest

from config import (
    ThemeConfig, NamedTheme, WindowConfig, TimeoutsConfig,
    hex_to_flet, is_valid_hex, severity_color, SEVERITY_TOKENS,
    safe_str, safe_int, get_fallback_bool,
    download_display_name, magnet_btih,
)


# ── ThemeConfig ───────────────────────────────────────────────────────────────

def test_theme_defaults_are_dark():
    assert ThemeConfig() == ThemeConfig.dark_default()
    assert ThemeConfig.light_default().bg_color == "FAFAFA"


def test_theme_from_dict_soft_migration():
    t = ThemeConfig.from_dict({"accent_color": "112233"})
    assert t.accent_color == "112233"
    # Отсутствующие ключи берутся из тёмных дефолтов
    assert t.bg_color == ThemeConfig().bg_color


@pytest.mark.parametrize("raw", [None, [], "x", 42])
def test_theme_from_dict_garbage_input(raw):
    assert ThemeConfig.from_dict(raw) == ThemeConfig()


def test_theme_from_dict_empty_values_fall_back():
    t = ThemeConfig.from_dict({"accent_color": "", "text_color": None})
    assert t.accent_color == ThemeConfig().accent_color
    assert t.text_color == ThemeConfig().text_color


def test_named_theme_from_dict():
    nt = NamedTheme.from_dict({"mode": "light", "colors": {"bg_color": "ABCDEF"}})
    assert nt.mode == "light"
    assert nt.config.bg_color == "ABCDEF"
    # Неизвестный режим откатывается на dark
    assert NamedTheme.from_dict({"mode": "weird"}).mode == "dark"
    assert NamedTheme.from_dict("garbage").mode == "dark"


# ── WindowConfig ──────────────────────────────────────────────────────────────

@pytest.fixture
def fixed_screen(monkeypatch):
    monkeypatch.setattr(WindowConfig, "_get_screen_metrics",
                        staticmethod(lambda: (1920, 1080)))


def test_window_clamps_to_screen(fixed_screen):
    w = WindowConfig.from_dict({"width": 5000, "height": 5000, "left": 5000, "top": 5000})
    assert (w.width, w.height) == (1920, 1080)
    assert (w.left, w.top) == (0, 0)          # 1920-1920=0, 1080-1080=0


def test_window_negative_position_clamped(fixed_screen):
    w = WindowConfig.from_dict({"left": -100, "top": -100})
    assert w.left == 0 and w.top == 0


def test_window_defaults_on_garbage(fixed_screen):
    w = WindowConfig.from_dict({"width": "abc", "height": None})
    d = WindowConfig()
    assert (w.width, w.height) == (d.width, d.height)


# ── TimeoutsConfig ────────────────────────────────────────────────────────────

def test_timeouts_roundtrip():
    t = TimeoutsConfig(connect=1.5, thumbnail_meta=33.0, card_fade=0.0)
    restored = TimeoutsConfig.from_dict(t.to_dict())
    assert restored == t


def test_timeouts_rejects_nonpositive_except_card_fade():
    t = TimeoutsConfig.from_dict({"connect": 0, "read": -1, "card_fade": 0})
    d = TimeoutsConfig()
    assert t.connect == d.connect          # 0 недопустим → дефолт
    assert t.read == d.read                # отрицательное → дефолт
    assert t.card_fade == 0.0              # 0 допустим (карточка уходит сразу)


def test_timeouts_garbage_values():
    assert TimeoutsConfig.from_dict({"connect": "zz"}).connect == TimeoutsConfig().connect
    assert TimeoutsConfig.from_dict(None) == TimeoutsConfig()


# ── Утилиты ───────────────────────────────────────────────────────────────────

def test_safe_str():
    assert safe_str(None) == ""
    assert safe_str(5) == "5"


@pytest.mark.parametrize("value,default,expected", [
    (None, 7, 7), ("", 7, 7), ("12", 0, 12), ("12.9", 0, 12), ("abc", 3, 3), (5.7, 0, 5),
])
def test_safe_int(value, default, expected):
    assert safe_int(value, default) == expected


def test_get_fallback_bool():
    assert get_fallback_bool({}, "k", True) is True
    assert get_fallback_bool({"k": None}, "k", True) is True
    assert get_fallback_bool({"k": ""}, "k", True) is True
    assert get_fallback_bool({"k": False}, "k", True) is False
    assert get_fallback_bool({"k": 1}, "k", False) is True


def test_hex_to_flet():
    assert hex_to_flet("aabbcc") == "#AABBCC"
    assert hex_to_flet("#AABBCC") == "#AABBCC"
    assert hex_to_flet("xyz") == "#FFFFFF"      # мусор → белый


def test_is_valid_hex():
    assert is_valid_hex("00B4D8")
    assert is_valid_hex("#00b4d8")
    assert not is_valid_hex("00B4D")
    assert not is_valid_hex("GGGGGG")


def test_severity_color_uses_theme_tokens():
    t = ThemeConfig()
    assert severity_color(t, "ok") == hex_to_flet(t.status_ok_color)
    assert severity_color(t, "warning") == hex_to_flet(t.status_warning_color)
    assert severity_color(t, "error") == hex_to_flet(t.status_error_color)
    # Неизвестная severity → вторичный текст (как info)
    assert severity_color(t, "whatever") == hex_to_flet(t.text_secondary_color)
    assert set(SEVERITY_TOKENS) == {"ok", "warning", "error", "info"}


def test_download_display_name():
    assert download_display_name("magnet:?xt=urn:btih:abc&dn=My%20File") == "My File"
    assert download_display_name(r"C:\dir\file.torrent") == "file.torrent"
    assert download_display_name("https://ex.com/page") == "https://ex.com/page"


def test_magnet_btih():
    assert magnet_btih("magnet:?xt=urn:btih:AbCd123&dn=x") == "abcd123"
    assert magnet_btih("https://ex.com") == ""
