"""Тесты DownloadManager: слоты параллельности и жизненный цикл попыток."""

import asyncio

import pytest

from config import DEFAULT_MAX_PARALLEL, MAX_PARALLEL_CEILING
from events import (
    AppClosingEvent, DownloadCompletedEvent, DownloadStartedEvent, EventBus,
    SettingsChangedEvent,
)
from managers.download_manager import DownloadManager
from managers.snapshot import DownloadSnapshot


def make_dm(limit_fn=None, bus=None):
    return DownloadManager(
        provider_factories={},
        default_provider="yt-dlp",
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


# ── Жизненный цикл попыток ────────────────────────────────────────────────────

class FakeProvider:
    """«Процесс» работает, пока тест не выставит release (cancel его не ускоряет)."""
    SOURCE_NAME = "fake"
    SUPPORTS_PAUSE = True

    def __init__(self, fail_build=False):
        self.release = asyncio.Event()
        self.fail_build = fail_build
        self.runs = self.running = self.max_running = self.cancels = 0

    def resolve_exe(self):
        return "fake.exe"

    def build_command(self, exe, snapshot):
        if self.fail_build:
            raise ValueError("bad args")
        return [exe]

    def cancel(self):
        self.cancels += 1

    def temp_dir(self):
        return ""

    def observe_line(self, line):
        pass

    def final_path(self):
        return ""

    def parse_progress(self, line):
        return None

    def format_status(self, line):
        return line

    def failure_reason(self, output):
        return ""

    @classmethod
    def post_processing_tags(cls):
        return []

    async def run(self, cmd_args, on_line, on_finish):
        self.runs += 1
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        await self.release.wait()
        self.running -= 1
        on_finish(0)


def make_live_dm(providers, bus, limit=5):
    """Менеджер с настоящим планировщиком корутин (как page.run_task)."""
    return DownloadManager(
        provider_factories={key: (lambda p=p: p) for key, p in providers.items()},
        default_provider=next(iter(providers)),
        bus=bus,
        task_runner=lambda fn, *args: asyncio.ensure_future(fn(*args)),
        max_parallel=lambda: limit,
    )


def _snap(url="https://ex.com/file.zip"):
    return DownloadSnapshot.from_params(url, {})


async def _tick():
    await asyncio.sleep(0.01)


def test_fast_pause_resume_never_runs_task_twice():
    """Resume до выхода убитого процесса: новая попытка ждёт прежнюю, итог один."""
    async def scenario():
        bus, done = EventBus(), []
        bus.on(DownloadCompletedEvent, done.append)
        provider = FakeProvider()
        dm = make_live_dm({"fake": provider}, bus)

        task_id = dm.add(_snap())
        await _tick()
        dm.pause(task_id)
        dm.resume(task_id)                  # прежний run ещё не вернулся
        await _tick()
        assert provider.runs == 1           # вторая попытка ждёт первую

        provider.release.set()              # процесс первой попытки вышел
        await _tick()
        assert provider.runs == 2 and provider.max_running == 1
        assert len(done) == 1 and done[0].success
        assert dm.active_count == 0

    asyncio.run(scenario())


def test_pause_while_waiting_for_slot_does_not_start_process():
    async def scenario():
        bus = EventBus()
        first, second = FakeProvider(), FakeProvider()
        dm = make_live_dm({"first": first, "second": second}, bus, limit=1)

        dm.add(_snap("https://ex.com/1.zip"), "first")
        waiting = dm.add(_snap("https://ex.com/2.zip"), "second")
        await _tick()
        dm.pause(waiting)                   # ждёт слот, процесса ещё нет
        first.release.set()
        await _tick()
        assert second.runs == 0 and dm.is_paused(waiting)

        dm.resume(waiting)
        second.release.set()
        await _tick()
        assert second.runs == 1 and dm.active_count == 0

    asyncio.run(scenario())


def test_build_command_error_finalizes_task():
    async def scenario():
        bus, done = EventBus(), []
        bus.on(DownloadCompletedEvent, done.append)
        dm = make_live_dm({"fake": FakeProvider(fail_build=True)}, bus)

        dm.add(_snap())
        await _tick()
        assert dm.active_count == 0 and not dm.is_active_url(_snap().url)
        assert len(done) == 1 and not done[0].success

    asyncio.run(scenario())


def test_app_closing_kills_processes_without_history_events():
    async def scenario():
        bus, done = EventBus(), []
        bus.on(DownloadCompletedEvent, done.append)
        provider = FakeProvider()
        dm = make_live_dm({"fake": provider}, bus)

        dm.add(_snap())
        await _tick()
        bus.emit(AppClosingEvent())
        assert provider.cancels == 1

        provider.release.set()
        await _tick()
        # Итог не пишется: запись 'running' станет 'incomplete' при следующем старте.
        assert done == []

    asyncio.run(scenario())


def test_history_record_is_created_on_accept():
    """INSERT истории — сразу в add(): meta и превью приходят раньше свободного слота."""
    bus, started = EventBus(), []
    bus.on(DownloadStartedEvent, started.append)
    dm = DownloadManager({"fake": FakeProvider}, "fake", bus, task_runner=lambda *a: None)

    task_id = dm.add(_snap())

    assert [e.task_id for e in started] == [task_id]
