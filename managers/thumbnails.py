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
    from paths import AppPaths
    from state import AppState


class ThumbnailService:

    def __init__(self, paths: "AppPaths", bus: EventBus,
                 db: "DownloadRepository | None", state: "AppState") -> None:
        self._paths = paths
        self._bus   = bus
        self._db    = db
        self._state = state
        self._log   = get_logger("app")

    @staticmethod
    def supports(provider_key: str) -> bool:
        """Умеет ли провайдер отдавать превью/метаданные (только yt-dlp)."""
        return provider_key == YtDlpProvider.SOURCE_NAME

    async def fetch(self, task_id: str, url: str) -> None:
        """Получить превью и метаданные, сохранить в БД и оповестить шину.
        Ошибки не фатальны: загрузка идёт независимо от превью."""
        try:
            provider = YtDlpProvider(self._paths)
            exe = provider.resolve_exe()
            if not exe:
                return
            st        = self._state
            proxy_url = st.proxy_address.strip() if st.proxy_enabled else None
            to        = st.timeouts
            thumb_data, meta = await provider.fetch_thumbnail(
                exe, url, proxy_url=proxy_url,
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
