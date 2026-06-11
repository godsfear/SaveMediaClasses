"""
NotificationController — системные уведомления о финале загрузки.

Ответственность:
  - По DownloadCompletedEvent показать тост «завершено/ошибка», НО только когда
    окно свёрнуто или не в фокусе (на виду пользователь и так видит карточку).
  - Кроссплатформенная доставка без новых зависимостей:
      Windows — PowerShell + WinRT ToastNotification (фоновый процесс),
      macOS   — osascript display notification,
      Linux   — notify-send (если установлен).

Не знает про экраны; имя загрузки берёт из БД (meta.title) с фолбэком на URL.
Трей во Flet 0.85 невозможен (нет tray-API) — уведомления его и заменяют.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape as xml_escape

import flet as ft

from app_logging import get_logger
from config import download_display_name
from events import DownloadCompletedEvent, WindowStateEvent
from i18n import Locale

if TYPE_CHECKING:
    from services import Services

_APP_TITLE = "SaveMedia"
# AppUserModelID для тостов. ВАЖНО: Windows 11 МОЛЧА отбрасывает тосты от
# незарегистрированных AppID — ID обязан существовать в реестре
# (HKCU\Software\Classes\AppUserModelId\<id>, без прав администратора).
# ID намеренно равен видимому имени: Windows кеширует атрибуцию и может
# показывать в шапке тоста САМ ID вместо DisplayName из реестра — пусть
# тогда показывает «SaveMedia», а не «SaveMedia.SaveMedia».
_APP_ID = "SaveMedia"


def register_win_app_id(display_name: str = _APP_TITLE,
                        icon_path: str = "") -> bool:
    """Зарегистрировать AppUserModelID в HKCU (идемпотентно). Без этого
    CreateToastNotifier(...).Show() на Windows 11 отрабатывает без ошибок,
    но уведомление не показывается. Возвращает успех."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\AppUserModelId\{_APP_ID}",
        )
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, display_name)
        if icon_path and os.path.exists(icon_path):
            winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon_path)
        winreg.CloseKey(key)
        return True
    except Exception:
        get_logger("app").warning("Failed to register toast AppUserModelId",
                                  exc_info=True)
        return False


def build_toast_xml(title: str, body: str, icon_uri: str = "") -> str:
    """XML тоста WinRT; текст экранируется (XML-сущности).

    title оставлять пустым на Windows: шапку тоста система сама подписывает
    DisplayName зарегистрированного AppID — свой заголовок дублировал бы его.
    icon_uri — png/jpg для appLogoOverride (логотип слева); путь должен быть
    БЕЗ не-ASCII символов: кириллицу в src тосты не разрешают."""
    parts = [f"<text>{xml_escape(t)}</text>" for t in (title, body) if t]
    if icon_uri:
        parts.append(f'<image placement="appLogoOverride" hint-crop="circle" '
                     f'src="{xml_escape(icon_uri, {chr(34): "&quot;"})}"/>')
    return ("<toast><visual><binding template='ToastGeneric'>"
            + "".join(parts) + "</binding></visual></toast>")


def build_ps_script(toast_xml: str) -> str:
    """PowerShell-скрипт показа тоста (Windows PowerShell 5.1 + WinRT).

    Каждый используемый WinRT-тип загружается явно (включая XmlDocument и
    ToastNotification — без этого New-Object падает с «Cannot find type»).
    XML вставляется в одинарные кавычки — кавычки внутри удваиваются."""
    quoted = toast_xml.replace("'", "''")
    return (
        "[Windows.UI.Notifications.ToastNotificationManager, "
        "Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null\n"
        "[Windows.UI.Notifications.ToastNotification, "
        "Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null\n"
        "[Windows.Data.Xml.Dom.XmlDocument, "
        "Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null\n"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
        f"$x.LoadXml('{quoted}')\n"
        "$t = New-Object Windows.UI.Notifications.ToastNotification $x\n"
        "[Windows.UI.Notifications.ToastNotificationManager]::"
        f"CreateToastNotifier('{_APP_ID}').Show($t)\n"
    )


class NotificationController:

    def __init__(self, page: ft.Page, svc: "Services") -> None:
        self._page = page
        self._svc  = svc
        self._log  = get_logger("app")
        # Видимость окна отслеживается по WindowStateEvent (его шлёт
        # WindowController из window.on_event). Свойства window.focused/
        # minimized НЕ годятся: Flet не обновляет их с Flutter-стороны —
        # они вечно показывают начальные True/False, и тосты глушились бы всегда.
        # None = состояние ещё неизвестно → уведомляем (лучше лишний тост,
        # чем молча неработающая функция).
        self._in_view: bool | None = None
        # Windows 11 не показывает тосты от незарегистрированного AppID —
        # регистрируем свой в HKCU один раз при старте (идемпотентно).
        # В реестр — .ico (большой PNG для атрибуции Windows игнорирует).
        ico = svc.paths.app_icon_ico
        register_win_app_id(
            icon_path=str(ico if os.path.exists(ico) else svc.paths.app_icon))
        # Логотип для тела тоста: тосты не принимают пути с не-ASCII символами
        # (проект может лежать в «Мой диск» и т.п.) — копируем png в служебную
        # папку приложения (%APPDATA%-база, ASCII) один раз.
        self._toast_icon = self._prepare_toast_icon()
        svc.bus.on(WindowStateEvent,       self._on_window_state)
        svc.bus.on(DownloadCompletedEvent, self._on_completed)

    def _prepare_toast_icon(self) -> str:
        if sys.platform != "win32":
            return ""
        try:
            import shutil
            import tempfile
            src = str(self._svc.paths.app_icon)
            if not os.path.exists(src):
                return ""
            # Папка приложения может лежать в кириллическом пути («Мой диск») —
            # копируем в %LOCALAPPDATA%\SaveMedia (обычно ASCII), иначе в temp.
            base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
            dst_dir = os.path.join(base, _APP_TITLE)
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, "toast_icon.png")
            if (not os.path.exists(dst)
                    or os.path.getsize(dst) != os.path.getsize(src)):
                shutil.copyfile(src, dst)
            return dst if dst.isascii() else ""
        except Exception:
            self._log.debug("Failed to prepare toast icon", exc_info=True)
            return ""

    # ── Обработка события ─────────────────────────────────────────────────────

    def _on_window_state(self, e: WindowStateEvent) -> None:
        self._in_view = e.in_view

    def _on_completed(self, e: DownloadCompletedEvent) -> None:
        if not self._svc.state.notify_on_complete:
            return
        # Глушим тост только когда ДОСТОВЕРНО известно, что окно на виду.
        if self._in_view is True:
            self._log.debug("notification suppressed: window in view")
            return
        s    = Locale.load(self._svc.state.language)
        name = self._download_name(e.task_id)
        text = (s.fmt("notify_done", name=name) if e.success
                else s.fmt("notify_failed", name=name))
        self._log.debug("showing toast: %s", text)
        self._notify(_APP_TITLE, text)

    def _download_name(self, task_id: str) -> str:
        try:
            rec = self._svc.db.get(task_id)
            if rec is not None:
                meta = rec.meta or {}
                return (meta.get("title") or meta.get("fulltitle")
                        or download_display_name(rec.url) or rec.url)
        except Exception:
            self._log.debug("Failed to resolve download name for toast", exc_info=True)
        return _APP_TITLE

    # ── Доставка по платформам ────────────────────────────────────────────────

    def _notify(self, title: str, body: str) -> None:
        try:
            if sys.platform == "win32":
                self._notify_windows(title, body)
            elif sys.platform == "darwin":
                subprocess.Popen(
                    ["osascript", "-e",
                     f'display notification "{body}" with title "{title}"'])
            else:
                subprocess.Popen(["notify-send", title, body])
        except Exception:
            # Нет notify-send / PowerShell недоступен — уведомление не критично.
            self._log.debug("System notification failed", exc_info=True)

    def _notify_windows(self, title: str, body: str) -> None:
        # title не передаём: шапку подписывает DisplayName зарегистрированного
        # AppID — иначе «SaveMedia» показывалось бы дважды.
        script  = build_ps_script(build_toast_xml("", body, self._toast_icon))
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
