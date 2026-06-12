"""Тесты DownloadOrchestrator: проверки перед запуском, исходы, события,
сопутствующие записи (meta.title, превью), возобновление из истории."""

from events import EventBus, DownloadAcceptedEvent, ResumeDownloadEvent
from managers.download_orchestrator import DownloadOrchestrator
from state import AppState


class FakeDM:
    def __init__(self, *, at_capacity=False, active_url=None, add_result="task-1",
                 paused_ids=()):
        self.at_capacity = at_capacity
        self._active_url = active_url
        self._add_result = add_result
        self._paused     = set(paused_ids)
        self.added       = []      # (snapshot, provider_key)
        self.resumed     = []

    def is_active_url(self, url):
        return url == self._active_url

    def add(self, snapshot, provider_key=None, task_id=None):
        self.added.append((snapshot, provider_key))
        return self._add_result

    def is_paused(self, task_id):
        return task_id in self._paused

    def resume(self, task_id):
        self.resumed.append(task_id)

    def active_temp_dirs(self):
        return set()


class FakeDB:
    def __init__(self, completed=None):
        self._completed = completed
        self.metas    = []     # (task_id, meta)
        self.deleted  = []

    def find_completed(self, url):
        return self._completed

    def save_meta(self, task_id, meta):
        self.metas.append((task_id, meta))

    def delete(self, task_id):
        self.deleted.append(task_id)


class FakeThumbs:
    @staticmethod
    def supports(provider_key):
        return provider_key == "yt-dlp"

    async def fetch(self, task_id, url):  # pragma: no cover — не исполняется
        pass


def make_orch(dm=None, db=None, bus=None, runner_calls=None):
    runner_calls = runner_calls if runner_calls is not None else []
    return DownloadOrchestrator(
        bus=bus or EventBus(),
        state=AppState(),
        dm=dm or FakeDM(),
        db=db if db is not None else FakeDB(),
        thumbs=FakeThumbs(),
        task_runner=lambda *a: runner_calls.append(a),
    ), runner_calls


# ── Выбор провайдера и валидация ──────────────────────────────────────────────

def test_resolve_tool_auto_routes_by_url():
    assert DownloadOrchestrator.resolve_tool("magnet:?xt=urn:btih:abc", "auto") == "aria2c"
    assert DownloadOrchestrator.resolve_tool("https://site/file.zip", "auto") == "aria2c"
    assert DownloadOrchestrator.resolve_tool("https://youtube.com/watch?v=x", "auto") == "yt-dlp"
    assert DownloadOrchestrator.resolve_tool("https://any", "aria2c") == "aria2c"


def test_is_valid_url_respects_selected_provider():
    assert DownloadOrchestrator.is_valid_url("https://youtube.com/watch", "yt-dlp")
    assert not DownloadOrchestrator.is_valid_url("not a url", "aria2c")


# ── Исходы submit ─────────────────────────────────────────────────────────────

def test_submit_invalid():
    orch, _ = make_orch()
    assert orch.submit("not a url", "aria2c").status == "invalid"


def test_submit_at_capacity():
    orch, _ = make_orch(dm=FakeDM(at_capacity=True))
    assert orch.submit("https://a/b.zip", "aria2c").status == "at_capacity"


def test_submit_already_active():
    url = "https://a/b.zip"
    orch, _ = make_orch(dm=FakeDM(active_url=url))
    assert orch.submit(url, "aria2c").status == "already_active"


def test_submit_duplicate_returns_prev_record():
    prev = object()
    orch, _ = make_orch(db=FakeDB(completed=prev))
    out = orch.submit("https://a/b.zip", "aria2c")
    assert out.status == "duplicate" and out.prev is prev


def test_start_anyway_skips_duplicate_check():
    dm = FakeDM()
    orch, _ = make_orch(dm=dm, db=FakeDB(completed=object()))
    assert orch.start_anyway("https://a/b.zip", "aria2c").status == "started"
    assert dm.added[0][1] == "aria2c"


def test_submit_no_exe():
    orch, _ = make_orch(dm=FakeDM(add_result=None))
    assert orch.submit("https://a/b.zip", "aria2c").status == "no_exe"


# ── Запуск: событие, meta.title, превью ───────────────────────────────────────

def test_launch_emits_accepted_and_saves_meta_for_aria2c():
    bus, db = EventBus(), FakeDB()
    accepted = []
    bus.on(DownloadAcceptedEvent, accepted.append)
    orch, runner = make_orch(db=db, bus=bus)

    out = orch.submit("https://a/b.zip", "aria2c")
    assert out.status == "started" and out.task_id == "task-1"
    assert accepted[0].task_id == "task-1"
    assert accepted[0].source == "aria2c" and accepted[0].pausable is True
    # aria2c не отдаёт метаданных — имя сохранено в историю явно
    # (для http-ссылки display name = сам URL).
    assert db.metas == [("task-1", {"title": "https://a/b.zip"})]
    assert runner == []   # превью для aria2c не запускается


def test_launch_schedules_thumbnail_for_ytdlp():
    db = FakeDB()
    orch, runner = make_orch(db=db)
    out = orch.submit("https://youtube.com/watch?v=x", "yt-dlp")
    assert out.status == "started"
    assert db.metas == []          # meta придёт от самого yt-dlp
    assert len(runner) == 1        # запланировано получение превью


# ── Пакетный запуск ───────────────────────────────────────────────────────────

def test_submit_batch_starts_valid_and_returns_leftover():
    orch, _ = make_orch()
    started, leftover = orch.submit_batch(
        ["https://a/b.zip", "not a url"], "aria2c")
    assert started == 1
    assert leftover == ["not a url"]


# ── Возобновление из истории ──────────────────────────────────────────────────

def test_resume_paused_task_resumes_in_place():
    dm = FakeDM(paused_ids={"t-paused"})
    db = FakeDB()
    orch, _ = make_orch(dm=dm, db=db)
    orch._on_resume_download(ResumeDownloadEvent(
        task_id="t-paused", url="https://a/b.zip", source="aria2c", params={}))
    assert dm.resumed == ["t-paused"]
    assert dm.added == [] and db.deleted == []   # перезапуска и замены записи нет


def test_resume_finished_task_relaunches_and_replaces_record():
    dm = FakeDM()
    db = FakeDB()
    orch, _ = make_orch(dm=dm, db=db)
    orch._on_resume_download(ResumeDownloadEvent(
        task_id="t-old", url="https://a/b.zip", source="aria2c",
        params={"download_path": "X"}, title="b.zip"))
    assert db.deleted == ["t-old"]               # старая incomplete-запись заменена
    snapshot, tool = dm.added[0]
    assert tool == "aria2c" and snapshot.download_path == "X"


def test_resume_unknown_source_falls_back_to_default_provider():
    dm = FakeDM()
    orch, _ = make_orch(dm=dm)
    orch._on_resume_download(ResumeDownloadEvent(
        task_id="t", url="https://a/page", source="nonexistent", params={}))
    assert dm.added[0][1] == "yt-dlp"
