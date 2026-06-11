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


def test_purge_older_than(repo, bus, tmp_path):
    import time as _time
    for tid, status in (("done", True), ("bad", False)):
        _start(bus, tid, f"https://{tid}")
        bus.emit(DownloadCompletedEvent(task_id=tid, success=status, message="",
                                        output_tail="" if status else "x"))
    _start(bus, "active", "https://active")          # running — не трогается

    # Состарим финальные записи напрямую в БД (события пишут текущее время)
    old = _time.time() - 90 * 86_400
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("UPDATE downloads SET started_at = ?, finished_at = ? "
                 "WHERE task_id IN ('done', 'bad')", (old, old))
    conn.commit(); conn.close()

    assert repo.purge_older_than(0) == 0             # 0 = хранить всё
    assert repo.purge_older_than(365) == 0           # моложе года
    assert repo.purge_older_than(30) == 2            # старше месяца — удалены
    left = {r.task_id for r in repo.get_history()}
    assert left == {"active"}                        # running пережил чистку


def test_history_filter_and_find_completed(repo, bus):
    _start(bus, "a", "https://a")
    bus.emit(DownloadCompletedEvent(task_id="a", success=True, message=""))
    _start(bus, "b", "https://b")
    bus.emit(DownloadCompletedEvent(task_id="b", success=False, message="Exit code 1",
                                    output_tail="x"))
    assert {r.task_id for r in repo.get_history(status="failed")} == {"b"}
    assert repo.find_completed("https://a") is not None
    assert repo.find_completed("https://b") is None   # failed не считается завершённой


# ── Поиск (Python-фильтр поверх выборки) ──────────────────────────────────────

def test_record_search_text_casefold():
    from types import SimpleNamespace
    from screens.history_screen import record_search_text

    rec = SimpleNamespace(
        url="https://youtube.com/watch?v=ABC",
        meta={"title": "Моё Видео Про Кошек"},
        error_message="ERROR: Sign in required",
    )
    blob = record_search_text(rec)
    assert "моё видео про кошек" in blob              # кириллица сложена casefold
    assert "youtube.com" in blob
    assert "sign in required" in blob

    bare = SimpleNamespace(url="https://x", meta=None, error_message=None)
    assert record_search_text(bare) == "https://x"
