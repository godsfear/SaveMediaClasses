"""Тесты чистой логики пакета config: миграции from_dict, утилиты, severity."""

import pytest

from config import (
    ThemeConfig, NamedTheme, WindowConfig, TimeoutsConfig,
    ParamQuality, ParamSubtitles, ParamExtraArgs, DEFAULT_QUALITY_PRESETS,
    DEFAULT_YT_DLP_ARGS, _LEGACY_YT_DLP_ARGS,
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


# ── ParamQuality ──────────────────────────────────────────────────────────────

def test_quality_defaults():
    q = ParamQuality()
    assert q.value == "best"
    assert q.selected_args() == ""                  # best: формат решает extra_args
    assert "-f" in q.presets["1080p"]
    assert list(q.presets) == list(DEFAULT_QUALITY_PRESETS)


def test_quality_selected_args():
    q = ParamQuality(value="720p")
    assert "height<=720" in q.selected_args()
    assert ParamQuality(value="nonexistent").selected_args() == ""


def test_quality_from_dict_unknown_value_falls_back_to_best():
    q = ParamQuality.from_dict({"value": "9000p"})
    assert q.value == "best"


def test_quality_from_dict_merges_user_presets():
    q = ParamQuality.from_dict({
        "value": "custom",
        "presets": {"custom": "-f worst", "1080p": "-f my-override"},
    })
    assert q.value == "custom"                      # пользовательский пресет валиден
    assert q.presets["custom"] == "-f worst"
    assert q.presets["1080p"] == "-f my-override"   # правка дефолта
    assert "720p" in q.presets                      # недостающие доехали из дефолтов


def test_quality_roundtrip():
    q = ParamQuality(value="480p")
    assert ParamQuality.from_dict(q.to_dict()) == q


# ── ParamSubtitles ────────────────────────────────────────────────────────────

def test_subtitles_default_off():
    p = ParamSubtitles()
    assert p.value == "off"
    assert p.selected_args("ru") == ""


def test_subtitles_language_value_uses_lang_template():
    p = ParamSubtitles(value="ru")
    args = p.selected_args(ui_language="en")     # язык пункта важнее языка UI
    assert "--embed-subs" in args
    assert "--sub-langs ru.*" in args
    assert "--write-auto-subs" not in args


def test_subtitles_auto_uses_ui_language():
    p = ParamSubtitles(value="auto")
    args = p.selected_args(ui_language="ru")
    assert "--write-auto-subs" in args
    assert "ru.*" in args
    # Региональный код сводится к базовому
    assert "en.*" in ParamSubtitles(value="auto").selected_args("en_US")


def test_subtitles_all():
    assert "--sub-langs all" in ParamSubtitles(value="all").selected_args("ru")


def test_subtitles_from_dict_keeps_off_preset():
    """Даже если пользователь сломал карту, режим "off" обязан существовать."""
    p = ParamSubtitles.from_dict({"value": "off", "presets": {"all": "-x"}})
    assert p.selected_args("ru") == ""


def test_subtitles_roundtrip():
    p = ParamSubtitles(value="auto")
    assert ParamSubtitles.from_dict(p.to_dict()) == p


# ── ParamExtraArgs: формат ушёл в пресеты качества ────────────────────────────

def test_extra_args_default_has_no_format():
    tokens = DEFAULT_YT_DLP_ARGS.split()
    assert "-f" not in tokens                       # формат задают пресеты качества
    assert "--merge-output-format" in tokens


def test_extra_args_legacy_default_migrates():
    """Нетронутый старый дефолт (с -f bestvideo+bestaudio/best) → новый без формата."""
    migrated = ParamExtraArgs.from_dict({"value": _LEGACY_YT_DLP_ARGS})
    assert migrated.value == DEFAULT_YT_DLP_ARGS


def test_extra_args_user_value_untouched():
    custom = "-f bestaudio --limit-rate 1M"
    assert ParamExtraArgs.from_dict({"value": custom}).value == custom
    # Пустое значение пользователя — тоже его выбор, не подменяем дефолтом
    assert ParamExtraArgs.from_dict({"value": ""}).value == ""


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
