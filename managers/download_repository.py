"""
DownloadRepository — SQLite-слой истории загрузок.

Схема таблицы downloads:

  Индексируемые колонки (по ним ищем и фильтруем):
    task_id       TEXT PRIMARY KEY  — UUID задачи
    url           TEXT              — исходная ссылка
    source        TEXT              — провайдер ("yt-dlp", "aria2c", ...)
    status        TEXT              — "running"|"completed"|"failed"|"cancelled"
    started_at    REAL              — Unix timestamp начала
    finished_at   REAL              — Unix timestamp завершения (NULL пока идёт)
    error_message TEXT              — текст ошибки (NULL если успех)

  Расширяемые поля:
    params        TEXT              — JSON-снимок параметров загрузки (без url — он в отдельной колонке)
    thumbnail     BLOB              — JPEG-байты превью (NULL если нет)
    meta          TEXT              — JSON метаданных из yt-dlp --dump-single-json
"""

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, fields
from typing import Any, Dict, Generator, List, Optional

from app_logging import get_logger
from events import (
    EventBus,
    DownloadStartedEvent,
    DownloadCompletedEvent,
    DownloadCancelledEvent,
)


# ── Схема ─────────────────────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS downloads (
    task_id       TEXT PRIMARY KEY,
    url           TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'yt-dlp',
    status        TEXT NOT NULL DEFAULT 'running',
    started_at    REAL NOT NULL,
    finished_at   REAL,
    error_message TEXT,
    params        TEXT NOT NULL DEFAULT '{}',
    thumbnail     BLOB,
    meta          TEXT
);
"""

_MIGRATE_THUMBNAIL = """
ALTER TABLE downloads ADD COLUMN thumbnail BLOB;
"""

_MIGRATE_META = """
ALTER TABLE downloads ADD COLUMN meta TEXT;
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_downloads_status     ON downloads (status);",
    "CREATE INDEX IF NOT EXISTS idx_downloads_url        ON downloads (url);",
    "CREATE INDEX IF NOT EXISTS idx_downloads_started_at ON downloads (started_at DESC);",
]

_INSERT = """
INSERT OR IGNORE INTO downloads (task_id, url, source, status, started_at, params)
VALUES (:task_id, :url, :source, 'running', :started_at, :params);
"""

_UPDATE_FINISHED = """
UPDATE downloads
SET status = :status, finished_at = :finished_at, error_message = :error_message
WHERE task_id = :task_id;
"""

_UPDATE_THUMBNAIL = """
UPDATE downloads SET thumbnail = :thumbnail WHERE task_id = :task_id;
"""

_UPDATE_META = """
UPDATE downloads SET meta = :meta WHERE task_id = :task_id;
"""


# ── Модель записи ─────────────────────────────────────────────────────────────

class DownloadRecord:
    """
    Запись из БД. params и meta десериализуются в dict при создании.
    """
    __slots__ = (
        "task_id", "url", "source", "status",
        "started_at", "finished_at", "error_message",
        "params", "thumbnail", "meta",
    )

    def __init__(self, params: str = "{}", thumbnail: Optional[bytes] = None,
                 meta: Optional[str] = None, **kwargs):
        for k, v in kwargs.items():
            if k in self.__slots__:
                setattr(self, k, v)
        try:
            self.params: Dict[str, Any] = json.loads(params) if isinstance(params, str) else params
        except (json.JSONDecodeError, TypeError):
            self.params = {}
        self.thumbnail: Optional[bytes] = thumbnail
        try:
            self.meta: Optional[Dict[str, Any]] = json.loads(meta) if isinstance(meta, str) else meta
        except (json.JSONDecodeError, TypeError):
            self.meta = None

    def __repr__(self) -> str:
        return f"<DownloadRecord {self.task_id[:8]}… {self.status} {self.url[:40]}>"


# ── Репозиторий ───────────────────────────────────────────────────────────────

class DownloadRepository:

    def __init__(self, db_path: str, bus: EventBus) -> None:
        self._db_path = db_path
        self._bus     = bus
        self._log     = get_logger("db")
        self._init_db()
        self._subscribe()

    # ── Инициализация ─────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_TABLE)
            for idx in _CREATE_INDEXES:
                conn.execute(idx)
            for migration in (_MIGRATE_THUMBNAIL, _MIGRATE_META):
                try:
                    conn.execute(migration)
                except sqlite3.OperationalError as err:
                    if "duplicate column name" not in str(err).lower():
                        self._log.exception("Database migration failed")
                except Exception:
                    self._log.exception("Database migration failed")

    def _subscribe(self) -> None:
        self._unsubs = [
            self._bus.on(DownloadStartedEvent,   self._on_started),
            self._bus.on(DownloadCompletedEvent, self._on_completed),
            self._bus.on(DownloadCancelledEvent, self._on_cancelled),
        ]

    def dispose(self) -> None:
        """Отписаться от всех событий шины. Вызывать при уничтожении объекта."""
        for unsub in getattr(self, "_unsubs", []):
            unsub()

    # ── Обработчики событий ───────────────────────────────────────────────────

    def _on_started(self, e: DownloadStartedEvent) -> None:
        snap = e.snapshot
        try:
            # url хранится в отдельной колонке — не дублируем в params
            snap_dict = asdict(snap)
            snap_dict.pop("url", None)
            params_json = json.dumps(snap_dict, ensure_ascii=False)
        except TypeError:
            d = vars(snap) if hasattr(snap, "__dict__") else {}
            d.pop("url", None)
            params_json = json.dumps(d)
        try:
            with self._connect() as conn:
                conn.execute(_INSERT, {
                    "task_id":    e.task_id,
                    "url":        snap.url,
                    "source":     e.source,
                    "started_at": time.time(),
                    "params":     params_json,
                })
        except Exception:
            self._log.exception("Failed to insert download record: %s", e.task_id)

    def _on_completed(self, e: DownloadCompletedEvent) -> None:
        self._finish(e.task_id, "completed" if e.success else "failed",
                     None if e.success else e.message)

    def _on_cancelled(self, e: DownloadCancelledEvent) -> None:
        self._finish(e.task_id, "cancelled", None)

    def _finish(self, task_id: str, status: str, error: Optional[str]) -> None:
        try:
            with self._connect() as conn:
                conn.execute(_UPDATE_FINISHED, {
                    "task_id":       task_id,
                    "status":        status,
                    "finished_at":   time.time(),
                    "error_message": error,
                })
        except Exception:
            self._log.exception("Failed to update download record: %s", task_id)

    # ── Публичный API ─────────────────────────────────────────────────────────

    def get_history(self, limit: int = 100,
                    status: Optional[str] = None) -> List[DownloadRecord]:
        query  = "SELECT * FROM downloads"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        return self._fetch(query, params)

    def get_by_url(self, url: str) -> Optional[DownloadRecord]:
        rows = self._fetch(
            "SELECT * FROM downloads WHERE url = ? ORDER BY started_at DESC LIMIT 1",
            [url]
        )
        return rows[0] if rows else None

    def get_stats(self) -> dict:
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("""
                    SELECT
                        COUNT(*)                                       AS total,
                        SUM(status = 'completed')                      AS completed,
                        SUM(status = 'failed')                         AS failed,
                        SUM(status = 'cancelled')                      AS cancelled,
                        AVG(CASE WHEN finished_at IS NOT NULL
                            THEN finished_at - started_at END)         AS avg_duration_sec
                    FROM downloads
                """).fetchone()
                return dict(row) if row else {}
        except Exception:
            self._log.exception("Failed to get download stats")
            return {}

    def save_thumbnail(self, task_id: str, data: bytes) -> None:
        """Сохранить JPEG-байты thumbnail в БД."""
        try:
            with self._connect() as conn:
                conn.execute(_UPDATE_THUMBNAIL, {"task_id": task_id, "thumbnail": data})
        except Exception:
            self._log.exception("Failed to save thumbnail: %s", task_id)

    def save_meta(self, task_id: str, meta: dict) -> None:
        """Сохранить JSON-метаданные из yt-dlp."""
        try:
            with self._connect() as conn:
                conn.execute(_UPDATE_META, {
                    "task_id": task_id,
                    "meta":    json.dumps(meta, ensure_ascii=False),
                })
        except Exception:
            self._log.exception("Failed to save metadata: %s", task_id)

    def delete(self, task_id: str) -> None:
        """Удалить запись из истории."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM downloads WHERE task_id = ?", (task_id,))
        except Exception:
            self._log.exception("Failed to delete download record: %s", task_id)

    # ── Приватное ─────────────────────────────────────────────────────────────

    def _fetch(self, query: str, params: list) -> List[DownloadRecord]:
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, params).fetchall()
                return [DownloadRecord(**dict(r)) for r in rows]
        except Exception:
            self._log.exception("Failed to fetch download records")
            return []

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path, timeout=5)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
