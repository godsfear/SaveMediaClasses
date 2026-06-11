"""Тесты слотов параллельности DownloadManager: динамический лимит, кламп."""

import asyncio

import pytest

from config import DEFAULT_MAX_PARALLEL, MAX_PARALLEL_CEILING
from events import EventBus, SettingsChangedEvent
from managers.download_manager import DownloadManager


def make_dm(limit_fn=None, bus=None):
    return DownloadManager(
        provider_factories={},
        default_provider="yt-dlp",
        log_path="",
        bus=bus or EventBus(),
        task_runner=lambda *a: None,
        max_parallel=limit_fn,
    )


def test_max_parallel_default_and_clamp():
    assert make_dm().max_parallel == DEFAULT_MAX_PARALLEL
    assert make_dm(lambda: 0).max_parallel == 1                     # нижний кламп
    assert make_dm(lambda: 9999).max_parallel == MAX_PARALLEL_CEILING
    assert make_dm(lambda: "abc").max_parallel == DEFAULT_MAX_PARALLEL  # мусор → дефолт
    assert make_dm(lambda: 3).max_parallel == 3


def test_at_capacity_uses_dynamic_limit():
    limit = {"n": 2}
    dm = make_dm(lambda: limit["n"])
    assert dm.at_capacity is False          # активных нет
    limit["n"] = 1
    assert dm.max_parallel == 1             # лимит перечитан на лету


def test_slot_waiting_respects_limit_increase():
    """Задача ждёт слот; увеличение лимита + SettingsChangedEvent её пропускает."""
    async def scenario():
        limit = {"n": 1}
        bus = EventBus()
        dm = make_dm(lambda: limit["n"], bus=bus)

        await dm._acquire_slot()
        assert dm._running == 1

        # Второй слот при лимите 1 не выдаётся
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(dm._acquire_slot()), timeout=0.05)

        # Подняли лимит в "настройках" — событие будит ожидающих
        limit["n"] = 2
        bus.emit(SettingsChangedEvent())
        await asyncio.wait_for(dm._acquire_slot(), timeout=0.5)
        assert dm._running >= 2

        dm._release_slot()
        dm._release_slot()

    asyncio.run(scenario())


def test_slot_released_frees_waiter():
    async def scenario():
        dm = make_dm(lambda: 1)
        await dm._acquire_slot()

        waiter = asyncio.ensure_future(dm._acquire_slot())
        await asyncio.sleep(0.01)
        assert not waiter.done()            # ждёт слот

        dm._release_slot()                  # освобождение пропускает ожидающего
        await asyncio.wait_for(waiter, timeout=0.5)
        assert dm._running == 1
        dm._release_slot()

    asyncio.run(scenario())
