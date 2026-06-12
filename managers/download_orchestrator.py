"""
managers/download_orchestrator.py — оркестрация запуска загрузок.

Решения уровня приложения, ранее жившие в MainScreen:
  • выбор провайдера для ссылки (auto → реестр, resolve_provider_for_url);
  • проверки перед запуском: валидность URL, свободные слоты, дубль активной
    загрузки, повтор уже скачанного (по истории);
  • сборка снимка параметров и постановка задачи в DownloadManager;
  • сопутствующие записи: meta.title для провайдеров без метаданных, запуск
    получения превью, замена incomplete-записи при возобновлении из истории.

Не знает про виджеты. Исходы возвращает вызывающему (SubmitOutcome) — экран
переводит их в локализованные сообщения; о принятой задаче сообщает шиной
(DownloadAcceptedEvent) — карточку рисует подписанный MainScreen. Диалог
подтверждения повтора — UI-решение: оркестратор возвращает "duplicate" с
прежней записью, а после согласия пользователя экран зовёт start_anyway().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from app_logging import get_logger
from config import download_display_name
from events import DownloadAcceptedEvent, ResumeDownloadEvent
from managers.providers import (
    PROVIDERS, DEFAULT_PROVIDER, Aria2cProvider,
    resolve_provider_for_url, torrent_name,
)
from managers.snapshot import DownloadSnapshot

if TYPE_CHECKING:
    from events import EventBus
    from managers.download_manager import DownloadManager
    from managers.download_repository import DownloadRepository
    from managers.thumbnails import ThumbnailService
    from state import AppState


@dataclass(frozen=True)
class SubmitOutcome:
    """Исход постановки загрузки. status:
    "started" | "invalid" | "at_capacity" | "already_active" | "duplicate" | "no_exe".
    prev — запись истории для "duplicate" (экран показывает диалог подтверждения);
    tool — провайдер, которому ушла бы ссылка (для сообщения "no_exe")."""
    status:  str
    task_id: str | None = None
    prev:    Any = None
    tool:    str = ""


class DownloadOrchestrator:

    def __init__(self, bus: "EventBus", state: "AppState", dm: "DownloadManager",
                 db: "DownloadRepository | None", thumbs: "ThumbnailService",
                 task_runner: Callable[..., Any]) -> None:
        """task_runner — планировщик coroutine (в app.py: page.run_task);
        нужен для фонового получения превью."""
        self._bus         = bus
        self._state       = state
        self._dm          = dm
        self._db          = db
        self._thumbs      = thumbs
        self._task_runner = task_runner
        self._log         = get_logger("app")
        # Возобновление/повтор из истории обрабатывается здесь; навигация
        # (переключение на главный экран) остаётся за подпиской в app.py.
        bus.on(ResumeDownloadEvent, self._on_resume_download)

    # ── Выбор провайдера и имени ──────────────────────────────────────────────

    @staticmethod
    def resolve_tool(url: str, selected: str) -> str:
        """Конкретный провайдер для ссылки: "auto" решает реестр, иначе — выбор."""
        return resolve_provider_for_url(url) if selected == "auto" else selected

    @classmethod
    def is_valid_url(cls, url: str, selected: str) -> bool:
        """Валидна ли ссылка для провайдера, который её получит."""
        return PROVIDERS[cls.resolve_tool(url, selected)].is_valid_url(url)

    @staticmethod
    def download_name(url: str) -> str:
        """Имя для карточки/истории. Для .torrent — реальное имя из метаданных
        торрента (info.name), не из имени файла; иначе — общий резолвер."""
        if url.lower().endswith(".torrent"):
            return torrent_name(url) or download_display_name(url)
        return download_display_name(url)

    # ── Постановка загрузок ───────────────────────────────────────────────────

    def submit(self, url: str, selected: str) -> SubmitOutcome:
        """Одна ссылка: полный набор проверок, включая повтор по истории
        (по URL/контент-хешу, без учёта source)."""
        tool = self.resolve_tool(url, selected)
        if not PROVIDERS[tool].is_valid_url(url):
            return SubmitOutcome("invalid")
        if self._dm.at_capacity:
            return SubmitOutcome("at_capacity")
        if self._dm.is_active_url(url):
            return SubmitOutcome("already_active")
        prev = self._db.find_completed(url) if self._db is not None else None
        if prev is not None:
            return SubmitOutcome("duplicate", prev=prev)
        return self._start(url, tool)

    def start_anyway(self, url: str, selected: str) -> SubmitOutcome:
        """Запуск после подтверждения повтора — проверка истории пропускается."""
        return self._start(url, self.resolve_tool(url, selected))

    def submit_batch(self, urls: list[str], selected: str) -> tuple[int, list[str]]:
        """Пачка ссылок: запускаем валидные, остальные возвращаем как leftover.
        Проверку повтора по истории в пакете не делаем — N подтверждений подряд
        хуже, чем повторная загрузка."""
        started, leftover = 0, []
        for url in urls:
            tool = self.resolve_tool(url, selected)
            if (self._dm.at_capacity
                    or not PROVIDERS[tool].is_valid_url(url)
                    or self._dm.is_active_url(url)):
                leftover.append(url)
                continue
            snapshot = DownloadSnapshot.from_state(self._state, url)
            if self.launch(snapshot, tool, self.download_name(url)) is None:
                leftover.append(url)
                continue
            started += 1
        return started, leftover

    def _start(self, url: str, tool: str) -> SubmitOutcome:
        snapshot = DownloadSnapshot.from_state(self._state, url)
        task_id = self.launch(snapshot, tool, self.download_name(url))
        if task_id is None:
            return SubmitOutcome("no_exe", tool=tool)
        return SubmitOutcome("started", task_id=task_id, tool=tool)

    def launch(self, snapshot: DownloadSnapshot, tool: str, title: str) -> str | None:
        """Запустить загрузку по готовому снимку: задача в менеджер + событие для
        UI. Общий путь для нового скачивания и возобновления из истории.
        None — исполняемый файл провайдера не найден."""
        task_id = self._dm.add(snapshot, provider_key=tool)
        if task_id is None:
            return None
        # Провайдер без метаданных (aria2c) — имя в историю как meta.title.
        if not self._thumbs.supports(tool) and self._db is not None:
            self._db.save_meta(task_id, {"title": title})
        self._bus.emit(DownloadAcceptedEvent(
            task_id=task_id, title=title, source=tool,
            pausable=PROVIDERS[tool].SUPPORTS_PAUSE,
        ))
        # Превью качает сервис; готовая картинка придёт ThumbnailReadyEvent.
        if self._thumbs.supports(tool):
            self._task_runner(self._thumbs.fetch, task_id, snapshot.url)
        return task_id

    # ── Возобновление из истории ──────────────────────────────────────────────

    def _on_resume_download(self, e: ResumeDownloadEvent) -> None:
        """Возобновление/повтор из истории. Если задача ещё жива в этой сессии
        НА ПАУЗЕ — просто снять с паузы (вид карточки обновит DownloadResumedEvent);
        иначе реконструировать снимок и запустить заново (докачка идёт через
        детерминированную .part)."""
        if self._dm.is_paused(e.task_id):
            self._dm.resume(e.task_id)
            return
        try:
            snapshot = DownloadSnapshot.from_params(e.url, e.params or {})
        except Exception:
            self._log.warning("Failed to rebuild snapshot for resume: %s", e.url, exc_info=True)
            snapshot = DownloadSnapshot.from_state(self._state, e.url)
        # Старую incomplete-запись заменит новая (новый task_id) — не плодим дубли.
        if self._db is not None:
            self._db.delete(e.task_id)
        tool = e.source if e.source in PROVIDERS else DEFAULT_PROVIDER
        self.launch(snapshot, tool, e.title or self.download_name(e.url))

    # ── Обслуживание ──────────────────────────────────────────────────────────

    def clean_temp(self) -> tuple[int, int]:
        """Удалить временные .part-подпапки aria2c, кроме активных загрузок.
        Возвращает (удалено папок, освобождено байт). Экран настроек зовёт это
        вместо прямого обращения к классу провайдера."""
        return Aria2cProvider.clean_temp_dirs(
            self._state.download_path,
            exclude=self._dm.active_temp_dirs(),
            part_dirname=self._state.aria2c.parameters.part_dirname,
        )
