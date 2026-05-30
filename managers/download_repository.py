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

  Расширяемое поле (не влияет на схему при добавлении новых параметров):
    params        TEXT              — JSON-снимок всех параметров загрузки
    thumbnail     BLOB              — JPEG-байты превью (NULL если нет)

Добавление нового параметра в DownloadSnapshot → просто появляется в JSON,
старые записи читаются без ошибок через params.get() с дефолтом.
"""

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any, Dict, Generator, List, Optional

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
    thumbnail     BLOB
);
"""

_MIGRATE_THUMBNAIL = """
ALTER TABLE downloads ADD COLUMN thumbnail BLOB;
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


# ── Модель записи ─────────────────────────────────────────────────────────────

class DownloadRecord:
    """
    Запись из БД. params десериализуется в dict при создании —
    обращаться как record.params["audio_only"] или record.params.get("new_field", default).
    """
    __slots__ = (
        "task_id", "url", "source", "status",
        "started_at", "finished_at", "error_message",
        "params", "thumbnail",
    )

    def __init__(self, params: str = "{}", thumbnail: Optional[bytes] = None, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        # Десериализуем JSON → dict при чтении, не при каждом обращении
        try:
            self.params: Dict[str, Any] = json.loads(params) if isinstance(params, str) else params
        except (json.JSONDecodeError, TypeError):
            self.params = {}
        self.thumbnail: Optional[bytes] = thumbnail

    def __repr__(self) -> str:
        return f"<DownloadRecord {self.task_id[:8]}… {self.status} {self.url[:40]}>"


# ── Репозиторий ───────────────────────────────────────────────────────────────

class DownloadRepository:

    def __init__(self, db_path: str, bus: EventBus) -> None:
        self._db_path = db_path
        self._bus     = bus
        self._init_db()
        self._subscribe()

    # ── Инициализация ─────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)
            for idx in _CREATE_INDEXES:
                conn.execute(idx)
            # Миграция: добавить колонку thumbnail если её нет
            try:
                conn.execute(_MIGRATE_THUMBNAIL)
            except Exception:
                pass  # Колонка уже существует — это норма

    def _subscribe(self) -> None:
        self._bus.on(DownloadStartedEvent,   self._on_started)
        self._bus.on(DownloadCompletedEvent, self._on_completed)
        self._bus.on(DownloadCancelledEvent, self._on_cancelled)

    # ── Обработчики событий ───────────────────────────────────────────────────

    def _on_started(self, e: DownloadStartedEvent) -> None:
        snap = e.snapshot
        try:
            # Снимок целиком в JSON — схема БД не зависит от состава параметров
            params_json = json.dumps(asdict(snap), ensure_ascii=False)
        except TypeError:
            # На случай если snapshot не dataclass (например, aria2c даст другой тип)
            params_json = json.dumps(vars(snap) if hasattr(snap, "__dict__") else {})
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
            pass

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
            pass

    # ── Публичный API чтения ──────────────────────────────────────────────────

    def get_history(self, limit: int = 100,
                    status: Optional[str] = None) -> List[DownloadRecord]:
        """Последние `limit` записей, опционально отфильтрованных по статусу."""
        query  = "SELECT * FROM downloads"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        return self._fetch(query, params)

    def get_by_url(self, url: str) -> Optional[DownloadRecord]:
        """Последняя запись для данного URL — для дедупликации."""
        rows = self._fetch(
            "SELECT * FROM downloads WHERE url = ? ORDER BY started_at DESC LIMIT 1",
            [url]
        )
        return rows[0] if rows else None

    def get_stats(self) -> dict:
        """Агрегированная статистика."""
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
            return {}

    def save_thumbnail(self, task_id: str, data: bytes) -> None:
        """Сохранить JPEG-байты thumbnail в БД."""
        try:
            with self._connect() as conn:
                conn.execute(_UPDATE_THUMBNAIL, {
                    "task_id":   task_id,
                    "thumbnail": data,
                })
        except Exception:
            pass

    # ── Приватное ─────────────────────────────────────────────────────────────

    def _fetch(self, query: str, params: list) -> List[DownloadRecord]:
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, params).fetchall()
                return [DownloadRecord(**dict(r)) for r in rows]
        except Exception:
            return []

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
