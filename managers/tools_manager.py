"""
managers/tools_manager.py — generic-движок проверки и обновления инструментов.

Движок НЕ знает про конкретные инструменты. Он итерирует список ToolSpec
(из tool_registry) и единообразно выполняет три операции:

    check_all()  — локальные версии бинарников + удалённые версии инструментов
    update_all() — установка/обновление тех инструментов, что помечены needs_update

Вся специфика yt-dlp/ffmpeg вынесена в managers/tool_registry.py.
Сравнение версий — в managers/tool_specs.classify_version() (единый источник).

Добавление нового инструмента не требует правок в этом файле.

────────────────────────────────────────────────────────────────────────────
Граница взаимодействия (осознанный контракт, НЕ недосмотр)
────────────────────────────────────────────────────────────────────────────
ToolsManager — bus-АГНОСТИЧНЫЙ движок: наружу он сообщает о ходе работы через
типизированные колбэки (OnLocalVersion / OnRemoteDone / OnToolStatus /
OnProgress / OnDone), а НЕ через EventBus. Это порт: движок ничего не знает ни
про UI, ни про событийный вокабуляр приложения, поэтому его можно вызвать из
теста или CLI, подсунув print-колбэки. В события шины их транслирует адаптер —
ToolsController.

Масштабирование на N инструментов (напр. будущий aria2c) НЕ затрагивает этот
файл и не меняет контракт: колбэки ключуются по имени бинарника, движок просто
итерирует DEFAULT_TOOLS. Добавление инструмента = подкласс BaseTool в
tool_registry + строка в DEFAULT_TOOLS.

Конвенция по менеджерам (чтобы стиль интеграции не расходился при росте):
  • менеджер-ДВИЖОК (чистая доменная логика, один оркестрирующий вызывающий,
    ценность в изоляции/тестируемости) → колбэки-порт, адаптер-контроллер
    переводит их в шину.  ← ЭТОТ класс.
  • менеджер-ИСТОЧНИК СОБЫТИЙ (долгоживущий, fire-and-forget прогресс многим
    слушателям, сам по себе естественный издатель) → может брать EventBus
    напрямую.  ← так сделан DownloadManager.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from typing import TYPE_CHECKING, Callable, Optional

import httpx

from app_logging import get_logger
from managers.tool_specs import (
    ToolBinary, ToolSpec, InstallContext, ManualInstallRequired,
    TOOL_VERSION_MISSING, TOOL_VERSION_CALL_ERROR, TOOL_VERSION_REMOTE_ERR,
    TOOL_VERSION_UNKNOWN, TOOL_VERSION_NEEDS_RUNTIME,
    classify_version, status_needs_update,
)

if TYPE_CHECKING:
    from state import AppState

# ── Типизированные алиасы коллбэков ──────────────────────────────────────────
# check_all
OnLocalVersion = Callable[[str, str], None]              # (binary_name, local_version)
OnRemoteDone   = Callable[[str, str, str, str], None]    # (binary_name, local, remote, status)

# update_all
OnToolStatus = Callable[[str, str, str], None]           # (tool_name, code, detail)
OnProgress   = Callable[[Optional[float]], None]         # pct 0..1, или None = индетерминированный
OnDone       = Callable[..., None]                       # (had_errors: bool, critical_err: str = "")


class ToolsManager:

    def __init__(self, paths) -> None:
        self._paths    = paths   # AppPaths — единый источник путей
        self._ext      = ".exe" if os.name == "nt" else ""
        self._log      = get_logger("tools")

        # Гард повторного запуска. Устанавливается СИНХРОННО в начале check_all()
        # до первого await — поэтому два конкурентных вызова не могут оба пройти.
        self._checking = False
        # Карта результата последней проверки: {tool_name: needs_update}
        self._needs_update: dict[str, bool] = {}

    # ── Состояние ─────────────────────────────────────────────────────────────

    @property
    def is_checking(self) -> bool:
        """True пока выполняется check_all() — для блокировки повторного запуска."""
        return self._checking

    @property
    def needs_update(self) -> bool:
        """True если хотя бы один инструмент по итогам проверки подлежит обновлению."""
        return any(self._needs_update.values())

    def tool_needs_update(self, tool_name: str) -> bool:
        return self._needs_update.get(tool_name, False)

    # ── Пути ──────────────────────────────────────────────────────────────────

    def _binary_path(self, binary: ToolBinary) -> str:
        """
        Путь к бинарнику. Приоритет — наша tools_dir (управляемая приложением
        копия); если там нет, ищем установленный в системе на PATH (apt/brew/…).
        Так системные инструменты тоже детектятся как присутствующие.
        """
        local = os.path.join(self._paths.tools_dir, f"{binary.filename}{self._ext}")
        if os.path.exists(local):
            return local
        return shutil.which(binary.filename) or ""

    # ── Проверка версий ───────────────────────────────────────────────────────

    async def check_all(
        self,
        specs: list[ToolSpec],
        state: "AppState",
        proxy_url: str | None,
        on_local_version: OnLocalVersion,
        on_remote_done:   OnRemoteDone,
    ) -> None:
        """
        Проверить локальные версии всех бинарников и удалённые версии всех инструментов.
        Гард _checking защищает от двойного запуска (раньше lock покрывал лишь сброс флагов).
        """
        if self._checking:
            return
        self._checking = True
        try:
            self._needs_update = {}

            # 1. Локальные версии — по каждому бинарнику каждого инструмента.
            local: dict[str, str] = {}
            for spec in specs:
                for b in spec.binaries(state):
                    ver = await self._probe_local_version(spec, b)
                    local[b.name] = ver
                    on_local_version(b.name, ver)

            # 2. Удалённые версии — один сетевой запрос на инструмент.
            to = state.timeouts
            timeout = httpx.Timeout(connect=to.connect, read=to.read,
                                    write=to.connect, pool=to.connect)
            async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
                for spec in specs:
                    remote = await self._fetch_remote(spec, state, client)

                    # 3. Классификация — по каждому бинарнику; needs_update — агрегат по инструменту.
                    tool_needs = False
                    for b in spec.binaries(state):
                        loc    = local.get(b.name, TOOL_VERSION_MISSING)
                        status = classify_version(loc, remote)
                        on_remote_done(b.name, loc, remote, status)
                        if status_needs_update(status, remote):
                            tool_needs = True
                    self._needs_update[spec.name] = tool_needs
        finally:
            self._checking = False

    async def _probe_local_version(self, spec: ToolSpec, binary: ToolBinary) -> str:
        path = self._binary_path(binary)
        if not path:
            return TOOL_VERSION_MISSING
        # Бинарник на месте, но без нужного рантайма запускать его бессмысленно
        # (generic yt-dlp без Python упадёт с непонятной ошибкой вызова).
        if spec.missing_runtime():
            return TOOL_VERSION_NEEDS_RUNTIME
        try:
            startup = self._win_startupinfo()
            proc = await asyncio.create_subprocess_exec(
                path, binary.version_flag,
                stdout=asyncio.subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                startupinfo=startup,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            text = out.decode("utf-8", errors="replace").strip()
            return spec.parse_version(binary, text) or TOOL_VERSION_CALL_ERROR
        except Exception:
            self._log.exception("Failed to get local version for %s", binary.name)
            return TOOL_VERSION_CALL_ERROR

    async def _fetch_remote(self, spec: ToolSpec, state: "AppState",
                            client: httpx.AsyncClient) -> str:
        try:
            url = spec.version_url(state)
            return await asyncio.wait_for(spec.fetch_remote_version(client, url), timeout=8.0)
        except Exception:
            self._log.warning("Failed to get remote version for %s", spec.name, exc_info=True)
            return TOOL_VERSION_REMOTE_ERR

    # ── Установка / обновление ────────────────────────────────────────────────

    async def update_all(
        self,
        specs: list[ToolSpec],
        state: "AppState",
        proxy_url: str | None,
        on_status:   OnToolStatus,
        on_progress: OnProgress,
        on_done:     OnDone,
    ) -> None:
        """Установить/обновить инструменты, помеченные needs_update в последней check_all()."""
        had_errors = False
        try:
            # tools_dir может быть в профиле пользователя и ещё не существовать —
            # создаём перед первой записью (stream_to_file пишет в неё напрямую).
            os.makedirs(self._paths.tools_dir, exist_ok=True)
            async with httpx.AsyncClient(proxy=proxy_url, timeout=state.timeouts.tool_download,
                                         follow_redirects=True) as client:
                for spec in specs:
                    if not self._needs_update.get(spec.name):
                        continue

                    on_status(spec.name, "downloading", "")
                    ctx = InstallContext(
                        client=client,
                        tools_dir=str(self._paths.tools_dir),
                        ext=self._ext,
                        download_url=spec.download_url(state),
                        on_progress=on_progress,
                        state=state,
                        chunk_size=spec.chunk_size(state),
                    )
                    try:
                        await spec.install(ctx)
                        on_status(spec.name, "ok", "")
                    except ManualInstallRequired as manual:
                        on_status(spec.name, "manual", manual.hint)
                    except Exception as err:
                        had_errors = True
                        self._log.exception("Failed to update %s", spec.name)
                        on_status(spec.name, "error", str(err))

            on_done(had_errors)

        except Exception as err:
            self._log.exception("Critical tools update failure")
            on_done(had_errors=True, critical_err=str(err))

    # ── Утилиты ───────────────────────────────────────────────────────────────

    @staticmethod
    def _win_startupinfo():
        if os.name != "nt":
            return None
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startup
