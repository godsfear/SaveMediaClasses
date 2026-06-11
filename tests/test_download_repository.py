"""Тесты DownloadRepository: запись через события шины, error_output, миграции."""

import sqlite3

import pytest

from events import EventBus, DownloadStartedEvent, DownloadCompletedEvent
from managers.download_repository import DownloadRepository
from managers.snapshot import DownloadSnapshot


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def repo(tmp_path, bus):
    return DownloadRepository(db_path=str(tmp_path / "test.db"), bus=bus)


def _start(bus, task_id="t1", url="https://x"):
    snap = DownloadSnapshot.from_params(url, {})
    bus.emit(DownloadStartedEvent(task_id=task_id, snapshot=snap, source="yt-dlp"))


def test_failed_download_stores_error_output(repo, bus):
    _start(bus)
    tail = "WARNING: something\nERROR: Video unavailable"
    bus.emit(DownloadCompletedEvent(
        task_id="t1", success=False, message="Exit code 1",
        error_code=1, output_tail=tail,
    ))
    rec = repo.get_history()[0]
    assert rec.status == "failed"
    assert rec.error_message == "Exit code 1"
    assert rec.error_output == tail


def test_successful_download_has_no_error_output(repo, bus):
    _start(bus)
    bus.emit(DownloadCompletedEvent(task_id="t1", success=True, message=""))
    rec = repo.get_history()[0]
    assert rec.status == "completed"
    assert rec.error_output == ""           # DownloadRecord нормализует None → ""


def test_migration_adds_error_output_to_old_db(tmp_path, bus):
    """БД старой схемы (без error_output) дополняется колонкой при инициализации."""
    db_path = str(tmp_path / "old.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE downloads (
            task_id       TEXT PRIMARY KEY,
            url           TEXT NOT NULL,
            source        TEXT NOT NULL DEFAULT 'yt-dlp',
            status        TEXT NOT NULL DEFAULT 'running',
            started_at    REAL NOT NULL,
            finished_at   REAL,
            error_message TEXT,
            params        TEXT NOT NULL DEFAULT '{}'
        );
    """)
    conn.execute(
        "INSERT INTO downloads (task_id, url, started_at) VALUES ('old1', 'https://y', 1.0)")
    conn.commit()
    conn.close()

    repo = DownloadRepository(db_path=db_path, bus=bus)
    rec = repo.get_history()[0]              # SELECT * работает с новой колонкой
    assert rec.task_id == "old1"
    assert rec.error_output == ""

    # И запись сбоя в мигрированную БД работает
    bus.emit(DownloadCompletedEvent(task_id="old1", success=False,
                                    message="Exit code 2", output_tail="boom"))
    assert repo.get_history()[0].error_output == "boom"


def test_history_filter_and_find_completed(repo, bus):
    _start(bus, "a", "https://a")
    bus.emit(DownloadCompletedEvent(task_id="a", success=True, message=""))
    _start(bus, "b", "https://b")
    bus.emit(DownloadCompletedEvent(task_id="b", success=False, message="Exit code 1",
                                    output_tail="x"))
    assert {r.task_id for r in repo.get_history(status="failed")} == {"b"}
    assert repo.find_completed("https://a") is not None
    assert repo.find_completed("https://b") is None   # failed не считается завершённой
