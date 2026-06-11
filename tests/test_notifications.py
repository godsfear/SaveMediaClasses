"""Тесты уведомлений: сборка тоста (XML + PS) и маппинг видимости окна."""

import pytest

from controllers.notification_controller import build_toast_xml, build_ps_script
from controllers.window_controller import window_event_visibility


def test_toast_xml_escapes_markup():
    xml = build_toast_xml("SaveMedia", 'Видео <best> & "клип"')
    assert "&lt;best&gt;" in xml and "&amp;" in xml
    assert "<text>SaveMedia</text>" in xml
    assert xml.startswith("<toast>") and xml.endswith("</toast>")
    assert "<image" not in xml                       # без иконки — без элемента


def test_toast_xml_embeds_icon():
    xml = build_toast_xml("SaveMedia", "done", "file:///C:/app/SaveMedia.png")
    assert 'placement="appLogoOverride"' in xml
    assert 'src="file:///C:/app/SaveMedia.png"' in xml


def test_ps_script_escapes_single_quotes():
    xml = build_toast_xml("SaveMedia", "файл д'Артаньяна")
    script = build_ps_script(xml)
    # Одинарная кавычка внутри PS-строки в одинарных кавычках удваивается
    assert "д''Артаньяна" in script
    # Тост идёт от ЗАРЕГИСТРИРОВАННОГО AppUserModelID (Windows 11 молча
    # отбрасывает тосты незарегистрированных приложений). ID = видимому имени:
    # Windows может показать в шапке сам ID вместо DisplayName из реестра.
    assert "CreateToastNotifier('SaveMedia')" in script
    assert "LoadXml('" in script


def test_ps_script_is_valid_for_plain_text():
    script = build_ps_script(build_toast_xml("SaveMedia", "Загрузка завершена: video.mp4"))
    assert "ToastNotificationManager" in script
    assert "Загрузка завершена: video.mp4" in script


def test_ps_script_loads_all_winrt_types():
    """В Windows PowerShell каждый WinRT-тип грузится явно; без XmlDocument
    скрипт падает с «Cannot find type» (проверено живым запуском)."""
    script = build_ps_script(build_toast_xml("t", "b"))
    assert "Windows.UI.Notifications.ToastNotificationManager," in script
    assert "Windows.UI.Notifications.ToastNotification," in script
    assert "Windows.Data.Xml.Dom.XmlDocument," in script


# ── Видимость окна по событиям (window.focused/minimized во Flet статичны) ────

@pytest.mark.parametrize("ev,expected", [
    ("windoweventtype.blur",       False),
    ("windoweventtype.minimize",   False),
    ("windoweventtype.hide",       False),
    ("windoweventtype.focus",      True),
    ("windoweventtype.restore",    True),
    ("windoweventtype.show",       True),
    ("windoweventtype.maximize",   True),
    ("windoweventtype.unmaximize", True),    # окно всё ещё видно
    ("windoweventtype.close",      None),    # не про видимость
    ("windoweventtype.resized",    None),
    ("windoweventtype.moved",      None),
])
def test_window_event_visibility(ev, expected):
    assert window_event_visibility(ev) is expected
