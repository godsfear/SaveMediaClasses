"""
managers/thumbnails.py — фоновое получение превью и метаданных загрузки.

Раньше эта логика жила в MainScreen (экран сам создавал YtDlpProvider, ходил в
сеть и писал в репозиторий). Сервис локализует её на сервисном слое:

  • знает, какие провайдеры умеют отдавать превью (supports);
  • качает превью/метаданные через yt-dlp, пишет их в DownloadRepository;
  • о готовой картинке сообщает шиной (ThumbnailReadyEvent) — экран лишь
    подписан и рисует, без знания, откуда превью взялось.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app_logging import get_logger
from events import EventBus, ThumbnailReadyEvent
from managers.providers import YtDlpProvider

if TYPE_CHECKING:
    from managers.download_repository import DownloadRepository
    from managers.snapshot import DownloadSnapshot
    from managers.tool_resolver import ToolResolver
    from paths import AppPaths
    from state import AppState


class ThumbnailService:

    def __init__(self, paths: "AppPaths", bus: EventBus,
                 db: "DownloadRepository | None", state: "AppState",
                 resolver: "ToolResolver | None" = None) -> None:
        """resolver — общий с загрузками (Services.tool_resolver): иначе метаданные
        запрашивал бы не тот yt-dlp, что выбран проверкой инструментов."""
        self._paths    = paths
        self._bus      = bus
        self._db       = db
        self._state    = state
        self._resolver = resolver
        self._log      = get_logger("app")

    @staticmethod
    def supports(provider_key: str) -> bool:
        """Умеет ли провайдер отдавать превью/метаданные (только yt-dlp)."""
        return provider_key == YtDlpProvider.SOURCE_NAME

    async def fetch(self, task_id: str, snapshot: "DownloadSnapshot") -> None:
        """Получить превью и метаданные, сохранить в БД и оповестить шину.
        Сеть и авторизация — из снимка загрузки. Ошибки не фатальны: загрузка
        идёт независимо от превью."""
        url = snapshot.url
        try:
            provider = YtDlpProvider(self._paths, self._resolver)
            exe = provider.resolve_exe()
            if not exe:
                return
            to = self._state.timeouts
            thumb_data, meta = await provider.fetch_thumbnail(
                exe, snapshot,
                connect_timeout=to.thumbnail_connect, read_timeout=to.thumbnail_read,
                meta_timeout=to.thumbnail_meta)
            if self._db is not None:
                if thumb_data:
                    self._db.save_thumbnail(task_id, thumb_data)
                if meta:
                    self._db.save_meta(task_id, meta)
            if thumb_data:
                self._bus.emit(ThumbnailReadyEvent(task_id=task_id, data=thumb_data))
        except Exception:
            self._log.warning("Failed to fetch thumbnail for %s", url, exc_info=True)
