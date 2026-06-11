"""
managers/snapshot.py — неизменяемый снимок параметров загрузки.

Выделен в отдельный модуль, чтобы его могли типизированно импортировать все
слои (events, providers, download_manager, экраны) без циклических зависимостей:
модуль зависит только от stdlib (AppState — лишь под TYPE_CHECKING).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import AppState


@dataclass(frozen=True)
class DownloadSnapshot:
    """Неизменяемая копия параметров загрузки.
    Изменение настроек во время загрузки не затрагивает уже запущенные задачи."""
    url:              str
    download_path:    str
    proxy_enabled:    bool
    proxy_address:    str
    cookies_enabled:  bool
    cookies_browser:  str
    playlist_enabled: bool
    embed_metadata:   bool
    audio_only:       bool
    yt_dlp_args:      str
    clean_titles:     bool
    save_to_source:   bool
    # Параметры инструмента из конфига (флаги CLI и шаблоны путей)
    aria2_args:            str = ""   # фиксированные CLI-флаги aria2c (из Aria2cConfig)
    aria2_seed_args:       str = ""   # флаги режима раздачи (seed)
    aria2_part_dirname:    str = ".part"
    seed:                  bool = False  # запуск в режиме раздачи (не скачивания)
    cookies_flag:          str = "--cookies-from-browser"
    playlist_flag_on:      str = "--yes-playlist"
    playlist_flag_off:     str = "--no-playlist"
    metadata_flags:        str = "--embed-metadata --embed-thumbnail"
    audio_flags:           str = "-x --audio-format mp3 --audio-quality 0"
    clean_title_template:  str = "%(title)s.%(ext)s"
    title_id_template:     str = "%(title)s [%(id)s].%(ext)s"
    playlist_dir_template: str = "%(playlist_title)s"
    playlist_idx_prefix:   str = "%(playlist_index)s - "
    source_dir_template:   str = "%(extractor_key)s"

    @classmethod
    def from_state(cls, state: "AppState", url: str) -> "DownloadSnapshot":
        """Собрать неизменяемый снимок из текущего AppState.

        Знание внутренних имён флагов/шаблонов yt-dlp-параметров локализовано
        здесь, а не в UI-экране: экрану достаточно вызвать from_state(state, url).
        Доступ к параметрам — через типизированный аксессор state.ytdlp,
        поэтому строковых имён инструментов тут тоже нет.
        """
        p = state.ytdlp.parameters
        a = state.aria2c.parameters
        return cls(
            url=url,
            download_path=state.download_path,
            aria2_args=a.download,
            aria2_seed_args=a.seed,
            aria2_part_dirname=a.part_dirname,
            proxy_enabled=state.proxy_enabled,
            proxy_address=state.proxy_address,
            cookies_enabled=p.cookies.state,
            cookies_browser=p.cookies.browser,
            playlist_enabled=p.playlist.state,
            embed_metadata=p.embed_metadata.state,
            audio_only=p.audio_only.state,
            yt_dlp_args=p.extra_args.value,
            clean_titles=p.clean_titles.state,
            save_to_source=p.save_to_source.state,
            cookies_flag=p.cookies.flag,
            playlist_flag_on=p.playlist.flag_on,
            playlist_flag_off=p.playlist.flag_off,
            metadata_flags=p.embed_metadata.args,
            audio_flags=p.audio_only.args,
            clean_title_template=p.clean_titles.template_on,
            title_id_template=p.clean_titles.template_off,
            playlist_dir_template=p.playlist.dir_template,
            playlist_idx_prefix=p.playlist.idx_prefix,
            source_dir_template=p.save_to_source.dir_template,
        )

    @classmethod
    def from_params(cls, url: str, params: dict) -> "DownloadSnapshot":
        """Восстановить снимок из сохранённого в БД params (asdict без url) — для
        возобновления/раздачи из истории. Берём только известные поля; для
        отсутствующих обязательных подставляем безопасные дефолты (старые/частичные
        записи не должны ронять реконструкцию)."""
        valid = {f.name for f in fields(cls)}
        kw = {k: v for k, v in (params or {}).items() if k in valid and k != "url"}
        required_defaults = dict(
            download_path="", proxy_enabled=False, proxy_address="",
            cookies_enabled=False, cookies_browser="none", playlist_enabled=False,
            embed_metadata=False, audio_only=False, yt_dlp_args="",
            clean_titles=False, save_to_source=False,
        )
        for k, v in required_defaults.items():
            kw.setdefault(k, v)
        return cls(url=url, **kw)
