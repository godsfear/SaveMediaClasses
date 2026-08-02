"""
managers/tools_manager.py — generic-движок проверки и обновления инструментов.

Движок НЕ знает про конкретные инструменты. Он итерирует список ToolSpec
(из tool_registry) и единообразно выполняет три операции:

    check_all()  — локальные версии бинарников + удалённые версии инструментов
    update_all() — установка/обновление тех инструментов, что помечены needs_update

Вся специфика конкретных инструментов вынесена в managers/tool_registry.py.
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

Масштабирование на N инструментов НЕ затрагивает этот
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
import subprocess
from typing import TYPE_CHECKING, Callable, Optional

import httpx

from app_logging import get_logger
from managers.tool_specs import (
    ToolBinary, ToolSpec, InstallContext, ManualInstallRequired,
    TOOL_VERSION_MISSING, TOOL_VERSION_CALL_ERROR, TOOL_VERSION_REMOTE_ERR,
    TOOL_VERSION_UNKNOWN, TOOL_VERSION_NEEDS_RUNTIME,
    STATUS_OK, classify_version, status_needs_update,
)
from managers.tool_resolver import ToolLocation, ToolOrigin, ToolResolver
from managers.package_managers import package_manager_for

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

    def __init__(self, paths, resolver: ToolResolver | None = None) -> None:
        self._paths    = paths   # AppPaths — единый источник путей
        self._ext      = ".exe" if os.name == "nt" else ""
        self._log      = get_logger("tools")
        self._resolver = resolver or ToolResolver(paths)

        # Гард повторного запуска. Устанавливается СИНХРОННО в начале check_all()
        # до первого await — поэтому два конкурентных вызова не могут оба пройти.
        self._checking = False
        # Карта результата последней проверки: {tool_name: needs_update}
        self._needs_update: dict[str, bool] = {}
        self._locations: dict[str, ToolLocation] = {}
        self._remote_versions: dict[str, str] = {}

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

    def _binary_location(self, binary: ToolBinary) -> ToolLocation:
        """Системный инструмент первым, затем управляемая приложением копия."""
        return self._resolver.resolve(binary.filename)

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
            self._resolver.configure(state.tooling.detectors)
            self._needs_update = {}
            self._remote_versions = {}

            # 1. Локальные версии — по каждому бинарнику каждого инструмента.
            local: dict[str, str] = {}
            locations: dict[str, ToolLocation] = {}
            for spec in specs:
                for b in spec.binaries(state):
                    location = self._binary_location(b)
                    ver = await self._probe_local_version(
                        spec, b, timeout=state.timeouts.version_probe,
                        location=location)
                    local[b.name] = ver
                    locations[b.name] = location
                    on_local_version(b.name, ver)

            # 2. Удалённые версии — один сетевой запрос на инструмент.
            to = state.timeouts
            timeout = httpx.Timeout(connect=to.connect, read=to.read,
                                    write=to.connect, pool=to.connect)
            package_remotes = await self._fetch_package_remotes(
                locations.values(),
                timeout=state.timeouts.tool_download,
                proxy_url=proxy_url,
                package_managers=state.tooling.package_managers,
            )
            async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
                for spec in specs:
                    binaries = spec.binaries(state)
                    primary = next((b for b in binaries if b.is_primary), binaries[0])
                    primary_location = locations.get(primary.name, ToolLocation())
                    package_key = (
                        primary_location.manager, primary_location.package_id)
                    package_known = package_key in package_remotes
                    package_remote = package_remotes.get(package_key, "")
                    if package_known:
                        # Нет доступного обновления → установленная версия и есть
                        # latest для данного package/channel (Gyan, BtbN, ...).
                        remote = package_remote or local.get(
                            primary.name, TOOL_VERSION_MISSING)
                    else:
                        remote = await self._fetch_remote(spec, state, client)
                    self._remote_versions[spec.name] = remote

                    # 3. Классификация — по каждому бинарнику; needs_update — агрегат по инструменту.
                    tool_needs = False
                    for b in spec.binaries(state):
                        loc    = local.get(b.name, TOOL_VERSION_MISSING)
                        status = classify_version(loc, remote)
                        location = locations.get(b.name, ToolLocation())

                        # Системная копия проверяется первой. Если она неактуальна,
                        # уже имеющаяся managed-копия может быть рабочим fallback.
                        if location.origin == ToolOrigin.SYSTEM and status != STATUS_OK:
                            managed = self._resolver.managed(b.filename)
                            if managed.found:
                                managed_ver = await self._probe_local_version(
                                    spec, b, timeout=state.timeouts.version_probe,
                                    location=managed)
                                managed_status = classify_version(managed_ver, remote)
                                if managed_status == STATUS_OK:
                                    self._resolver.prefer_managed(b.filename)
                                    loc, status, location = managed_ver, managed_status, managed
                                else:
                                    self._resolver.prefer_managed(b.filename, False)
                        elif location.origin == ToolOrigin.SYSTEM:
                            self._resolver.prefer_managed(b.filename, False)

                        local[b.name] = loc
                        locations[b.name] = location
                        on_remote_done(b.name, loc, remote, status)
                        if status_needs_update(status, remote, loc):
                            tool_needs = True
                    self._needs_update[spec.name] = tool_needs
            self._locations = locations
        finally:
            self._checking = False

    async def _probe_local_version(self, spec: ToolSpec, binary: ToolBinary,
                                   timeout: float,
                                   location: ToolLocation | None = None) -> str:
        """timeout — лимит локального вызова version_probe (timeouts.version_probe)."""
        path = (location or self._binary_location(binary)).path
        if not path:
            return TOOL_VERSION_MISSING
        # Бинарник на месте, но без нужного рантайма запускать его бессмысленно
        # (generic yt-dlp без Python упадёт с непонятной ошибкой вызова).
        if spec.missing_runtime():
            return TOOL_VERSION_NEEDS_RUNTIME
        proc = None
        try:
            startup = self._win_startupinfo()
            command = binary.version_probe.render(path)
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=self._resolver.process_env(),
                startupinfo=startup,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            if proc.returncode != 0:
                self._log.warning(
                    "Version probe failed for %s at %s (code %s): %s",
                    binary.name, path, proc.returncode,
                    out.decode("utf-8", errors="replace").strip(),
                )
                return TOOL_VERSION_CALL_ERROR
            text = out.decode("utf-8", errors="replace").strip()
            return spec.parse_version(binary, text) or TOOL_VERSION_CALL_ERROR
        except Exception:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            self._log.exception("Failed to get local version for %s", binary.name)
            return TOOL_VERSION_CALL_ERROR

    async def _fetch_remote(self, spec: ToolSpec, state: "AppState",
                            client: httpx.AsyncClient) -> str:
        # Общий лимит запроса = timeouts.read (httpx-клиент стережёт фазы
        # соединения/чтения, wait_for — весь вызов целиком).
        try:
            url = spec.version_url(state)
            return await asyncio.wait_for(
                spec.fetch_remote_version(client, url), timeout=state.timeouts.read)
        except Exception:
            self._log.warning("Failed to get remote version for %s", spec.name, exc_info=True)
            return TOOL_VERSION_REMOTE_ERR

    async def _fetch_package_remotes(
        self, locations, timeout: float, proxy_url: str | None,
        package_managers,
    ) -> dict[tuple[str, str], str]:
        """Проверить каждый package manager один раз; '' = пакет актуален."""
        grouped: dict[str, set[str]] = {}
        for location in locations:
            if location.manager and location.package_id:
                grouped.setdefault(location.manager, set()).add(location.package_id)

        result: dict[tuple[str, str], str] = {}
        for manager, package_ids in grouped.items():
            adapter = package_manager_for(manager, package_managers)
            if adapter is None:
                continue
            command = adapter.check_command(proxy_url)
            # Некоторые менеджеры умеют обновлять пакет, но не имеют безопасной
            # команды проверки обновлений (uv tool). Для них ToolSpec сам
            # получает remote version через свой HTTP endpoint.
            if not command:
                continue
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    env=self._resolver.process_env(),
                    startupinfo=self._win_startupinfo(),
                )
                output, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                if proc.returncode != 0:
                    continue
                text = output.decode("utf-8", errors="replace")
                for package_id in package_ids:
                    result[(manager, package_id)] = \
                        adapter.parse_available_version(text, package_id)
            except Exception:
                if proc is not None and proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                self._log.warning(
                    "Package update check failed for %s", manager, exc_info=True)
        return result

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
            self._resolver.configure(state.tooling.detectors)
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
                        binaries = spec.binaries(state)
                        primary = next((b for b in binaries if b.is_primary), binaries[0])
                        location = self._locations.get(
                            primary.name, self._binary_location(primary))

                        upgraded = False
                        if location.origin == ToolOrigin.SYSTEM:
                            upgraded = await self._try_system_upgrade(
                                spec, state, location.path, state.timeouts.tool_download,
                                proxy_url, location.manager, location.package_id)
                            if upgraded:
                                refreshed = await self._probe_local_version(
                                    spec, primary,
                                    timeout=state.timeouts.version_probe,
                                    location=location,
                                )
                                upgraded = classify_version(
                                    refreshed,
                                    self._remote_versions.get(
                                        spec.name, TOOL_VERSION_UNKNOWN),
                                ) == STATUS_OK

                        if not upgraded:
                            await spec.install(ctx)
                            for binary in binaries:
                                self._resolver.prefer_managed(binary.filename)
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

    async def _try_system_upgrade(self, spec: ToolSpec, state: "AppState",
                                  executable: str,
                                  timeout: float, proxy_url: str | None,
                                  manager: str = "", package_id: str = "") -> bool:
        """Попытаться обновить системную копию её штатной командой."""
        adapter = package_manager_for(manager, state.tooling.package_managers)
        command = adapter.upgrade_command(package_id) \
            if adapter is not None and package_id else []
        if not command and not manager:
            command = spec.self_update_command(state, executable)
        if not command:
            return False
        proc = None
        try:
            env = self._resolver.process_env()
            if proxy_url:
                env["HTTP_PROXY"] = proxy_url
                env["HTTPS_PROXY"] = proxy_url
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                startupinfo=self._win_startupinfo(),
            )
            output, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            if proc.returncode == 0:
                return True
            self._log.warning(
                "System update failed for %s (code %s): %s",
                spec.name, proc.returncode,
                output.decode("utf-8", errors="replace").strip(),
            )
        except Exception:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            self._log.warning("System update failed for %s", spec.name, exc_info=True)
        return False


    @staticmethod
    def _win_startupinfo():
        if os.name != "nt":
            return None
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startup
