"""
events.py — типизированные события приложения + EventBus.

Правила:
  - Каждое событие — frozen dataclass (неизменяемо, безопасно передавать между слоями).
  - EventBus.emit() синхронный: все обработчики вызываются в том же asyncio-тике,
    откуда пришёл emit(). Это безопасно для Flet — page.update() можно вызывать
    прямо в обработчике.
  - Подписка через bus.on(EventType, handler) — возвращает функцию отписки.
  - Один EventBus на всё приложение, создаётся в app.py и передаётся вниз.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, TYPE_CHECKING, Type, TypeVar

from app_logging import get_logger

if TYPE_CHECKING:
    from managers.snapshot import DownloadSnapshot

E = TypeVar("E")


# ── Загрузки ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DownloadProgressEvent:
    task_id: str
    pct:     float
    status:  str
    source:  str = "yt-dlp"   # будущий aria2c просто ставит source="aria2c"

@dataclass(frozen=True)
class DownloadPostprocessingEvent:
    task_id: str
    source:  str = "yt-dlp"

@dataclass(frozen=True)
class DownloadCompletedEvent:
    task_id:      str
    success:      bool
    message:      str        # технический текст для БД (на английском)
    source:       str = "yt-dlp"
    error_code:   int | None = None  # код возврата процесса (только при success=False)
    error_detail: str = ""           # текст ошибки ОС (только при сбое запуска)
    output_tail:  str = ""           # последние строки вывода процесса (только при сбое)
    file_path:    str = ""           # путь к скачанному файлу (только при success=True)

@dataclass(frozen=True)
class DownloadStartedEvent:
    """Эмитируется в момент старта загрузки — содержит полный снимок параметров.
    DownloadRepository использует его для записи в БД."""
    task_id:  str
    snapshot: "DownloadSnapshot"   # импорт под TYPE_CHECKING (модуль снимка лёгкий, но не тянем менеджеры в события)
    source:   str = "yt-dlp"

@dataclass(frozen=True)
class DownloadCancelledEvent:
    task_id: str
    source:  str = "yt-dlp"

@dataclass(frozen=True)
class DownloadPausedEvent:
    """Загрузка поставлена на паузу — БД переводит запись в статус 'incomplete'."""
    task_id: str
    source:  str = "aria2c"

@dataclass(frozen=True)
class DownloadResumedEvent:
    """Загрузка снята с паузы и снова идёт — БД возвращает статус 'running'."""
    task_id: str
    source:  str = "aria2c"

@dataclass(frozen=True)
class ResumeDownloadEvent:
    """Запрос из истории: возобновить незавершённую загрузку на главном экране.
    Несёт всё для реконструкции (params — снимок без url) + имя для карточки."""
    task_id: str
    url:     str
    source:  str
    params:  dict
    title:   str = ""

@dataclass(frozen=True)
class DownloadSeedingEvent:
    """Началась раздача торрента — БД переводит запись в статус 'seeding'."""
    task_id: str
    source:  str = "aria2c"

@dataclass(frozen=True)
class ThumbnailReadyEvent:
    """Превью загрузки получено (ThumbnailService) — карточка может показать картинку."""
    task_id: str
    data:    bytes

@dataclass(frozen=True)
class ClipboardUrlEvent:
    """В буфере обмена появились ссылки на загрузку (слежение включено).
    MainScreen добавляет их строками в поле URL."""
    urls: tuple


# ── Инструменты (yt-dlp / ffmpeg) ─────────────────────────────────────────────

@dataclass(frozen=True)
class ToolsCheckedEvent:
    """Эмитируется после завершения проверки версий."""
    needs_update: bool

@dataclass(frozen=True)
class StatusMessageEvent:
    """Сообщение для нижнего статус-бара главного экрана (нейтральный канал:
    статус инструментов, ошибки валидации URL, лимит параллельных загрузок и т.п.).
    Несёт только семантику; цвет выводит подписчик из токенов темы (severity_color)."""
    message:  str
    severity: str = "info"   # "ok" | "warning" | "error" | "info"


@dataclass(frozen=True)
class ToolsRestoredEvent:
    """Эмитируется при старте если проверка была недавно.
    Восстанавливает виджеты из сохранённого state без обращения к сети."""
    needs_update:     bool
    versions:         dict   # Dict[str, VersionState], ключ — имя бинарника
    mins_until_check: int


# ── Детальные события инструментов (для SettingsScreen) ───────────────────────

@dataclass(frozen=True)
class ToolVersionLocalEvent:
    """Найдена локальная версия инструмента — промежуточный результат проверки."""
    tool_name:     str
    local_version: str

@dataclass(frozen=True)
class ToolVersionRemoteEvent:
    """Получены обе версии инструмента после сетевого запроса."""
    tool_name:      str
    local_version:  str
    remote_version: str
    status:         str   # "ok" | "outdated" | "missing" | "error"

@dataclass(frozen=True)
class ToolButtonStateEvent:
    """Смена отображаемого состояния кнопки Check/Update."""
    mode: str   # "check" | "update" | "checking" | "updating"

@dataclass(frozen=True)
class ToolProgressEvent:
    """Обновление прогресс-бара скачивания/установки."""
    pct:     float | None   # 0.0–1.0 или None (indeterminate)
    visible: bool = True

@dataclass(frozen=True)
class ToolProgressMessageEvent:
    """Строка статуса операции с инструментами (для виджета progress_text).
    Несёт только семантику; цвет выводит подписчик из токенов темы (severity_color)."""
    key:      str   # "checking"|"prep"|"updates"|"ok"|"done_ok"|"done_errors"|"critical:<text>"
    severity: str = "info"   # "ok" | "warning" | "error" | "info"

@dataclass(frozen=True)
class ToolInstallStatusEvent:
    """Статус загрузки/установки конкретного инструмента."""
    tool_name: str    # "yt-dlp" | "ffmpeg"
    code:      str    # "downloading" | "ok" | "error" | "manual"
    detail:    str = ""


# ── Жизненный цикл приложения / настройки ────────────────────────────────────
# Заменяют ранее внедрявшиеся колбэки (set_on_*, on_save, on_close).
# Источник лишь сообщает о намерении; оркестрация — в обработчиках app.py.

@dataclass(frozen=True)
class SettingsChangedEvent:
    """Что-то в состоянии изменилось и должно быть сохранено на диск.
    Эмитируется при смене настроек, выборе папки, переключении прокси, изменении окна."""
    pass

@dataclass(frozen=True)
class ThemeChangedEvent:
    """Изменён цвет темы — нужно переприменить тему ко всем экранам."""
    pass

@dataclass(frozen=True)
class LanguageChangedEvent:
    """Сменён язык — нужно перестроить все текстовые метки UI."""
    pass

@dataclass(frozen=True)
class DownloadPathChangedEvent:
    """Сменилась папка загрузки (выбор в диалоге). MainScreen перевыводит свою
    метку из state — без прямого доступа контроллера к виджетам экрана."""
    pass

@dataclass(frozen=True)
class ToolsActionRequestedEvent:
    """Пользователь нажал кнопку Check/Update в настройках. Экран лишь сообщает
    о намерении; маршрутизацию (check или update) выполняет ToolsController."""
    pass

@dataclass(frozen=True)
class CookiesChangedEvent:
    """Изменён выбор браузера для cookies (в настройках).
    MainScreen перевыводит состояние своего переключателя из state — без
    прямого доступа одного экрана к виджетам другого."""
    pass

@dataclass(frozen=True)
class WindowStateEvent:
    """Окно стало видимым (фокус/разворачивание) или ушло с глаз (свёрнуто/
    потеряло фокус). Источник — WindowController (он владеет window.on_event);
    потребитель — уведомления: тост не нужен, когда окно и так перед глазами.
    ВАЖНО: свойства window.focused/minimized во Flet статичны (не обновляются
    с Flutter-стороны) — единственный надёжный источник состояния это события."""
    in_view: bool

@dataclass(frozen=True)
class AppClosingEvent:
    """Окно закрывается — подписчикам пора освободить ресурсы (dispose)."""
    pass


# ── Шина ──────────────────────────────────────────────────────────────────────

class EventBus:
    """
    Минималистичная синхронная шина событий.

    Использование:
        bus = EventBus()

        # Подписка
        unsub = bus.on(DownloadProgressEvent, handler)

        # Отписка
        unsub()

        # Публикация
        bus.emit(DownloadProgressEvent(task_id=..., pct=0.5, status="..."))
    """

    def __init__(self) -> None:
        self._handlers: Dict[type, List[Callable]] = {}
        self._log = get_logger("app")

    def on(self, event_type: Type[E], handler: Callable[[E], None]) -> Callable:
        """Подписаться на событие. Возвращает функцию отписки."""
        self._handlers.setdefault(event_type, []).append(handler)
        def unsubscribe():
            try:
                self._handlers[event_type].remove(handler)
            except (KeyError, ValueError):
                self._log.exception("Unsubscribe failed")
        return unsubscribe

    def emit(self, event: object) -> None:
        """Синхронно вызвать всех подписчиков данного типа события."""
        for handler in list(self._handlers.get(type(event), [])):
            try:
                handler(event)
            except Exception:
                # Один упавший обработчик не должен ломать остальных
                self._log.exception("Event handler failed for %s", type(event).__name__)
