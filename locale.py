"""
Locale — загрузчик языковых файлов из locale/*.json в типизированный dataclass.

Использование:
    from locale import Locale
    strings = Locale.load()
    print(strings.btn_check)

Добавить новый язык: положить locale/<code>.json с теми же ключами.
Добавить новую строку: добавить поле в Strings + ключ во все JSON-файлы.
"""

import ctypes
import json
import os
import sys
from dataclasses import dataclass, fields


@dataclass
class Strings:
    # Заголовки секций
    section_network:      str = ""
    section_downloaders:  str = ""
    section_cookies:      str = ""
    section_ytdlp:        str = ""
    section_ytdlp_urls:   str = ""
    section_deps:         str = ""
    section_deps_urls:    str = ""
    section_theme:        str = ""
    section_appearance:   str = ""

    # Группы цветов
    theme_group_controls: str = ""
    theme_group_surfaces: str = ""

    # Поля темы
    color_accent:    str = ""
    color_header:    str = ""
    color_switch:    str = ""
    color_text:      str = ""
    color_progress:  str = ""
    color_button:    str = ""
    color_appbar:    str = ""
    color_card:      str = ""

    # Поля настроек
    proxy_label:        str = ""
    yt_args_label:      str = ""
    switch_clean:       str = ""
    switch_playlist:    str = ""
    switch_metadata:    str = ""
    switch_source:      str = ""

    # Куки
    cookies_label:      str = ""
    cookies_none:       str = ""
    cookies_chrome:     str = ""
    cookies_yandex:     str = ""
    cookies_firefox:    str = ""
    cookies_edge:       str = ""
    cookies_opera:      str = ""
    cookies_switch_off: str = ""
    cookies_switch_on:  str = ""  # содержит {browser}

    # Язык
    language_label:     str = ""

    # Кнопки
    btn_check:          str = ""
    btn_update:         str = ""
    btn_checking:       str = ""
    btn_updating:       str = ""
    btn_reset_theme:    str = ""
    theme_hint:         str = ""

    # Статусы
    status_waiting:     str = ""
    status_checking:    str = ""
    status_ok:          str = ""
    status_updates:     str = ""
    status_all_ok:      str = ""  # {mins}
    status_has_updates: str = ""  # {mins}
    status_prep:        str = ""
    status_done_ok:     str = ""
    status_done_errors: str = ""
    status_critical:    str = ""  # {err}

    # Инструменты
    tool_dash:          str = ""  # {name}
    tool_versions:      str = ""  # {name} {loc} {rem}
    tool_querying:      str = ""  # {name} {loc}

    # Инструменты — отображаемые статусы (перевод sentinel-значений из tools_manager)
    tool_status_missing:    str = ""  # "Not installed" / "Отсутствует"
    tool_status_error:      str = ""  # "[Error]" / "[Ошибка]"
    tool_status_call_error: str = ""  # "[Call error]" / "[Ошибка вызова]"

    # Статусы обновления инструментов (показываются во время update_all)
    tool_update_downloading: str = ""  # "downloading..."
    tool_update_ok:          str = ""  # "updated successfully"
    tool_update_error:       str = ""  # "error: {detail}"
    tool_update_manual:      str = ""  # "install manually: {hint}" (non-Windows ffmpeg)

    # Загрузки — финальные сообщения в карточке
    download_completed:  str = ""  # "Download complete!" / "Загрузка завершена!"
    download_error_os:   str = ""  # "OS error: {detail}"
    download_error_code: str = ""  # "Error (code {code})"

    # URL поля
    url_yt_api:          str = ""
    url_yt_download:     str = ""
    url_ffmpeg_version:  str = ""
    url_ffmpeg_download: str = ""

    # main_screen
    header_folder:        str = ""
    header_download:      str = ""
    header_queue:         str = ""
    folder_not_selected:  str = ""
    url_label:            str = ""
    url_hint:             str = ""
    btn_clear:            str = ""
    btn_download:         str = ""
    btn_download_tooltip: str = ""
    btn_open_log:         str = ""
    switch_audio_only:    str = ""
    switch_cookies:       str = ""
    status_postprocessing: str = ""
    status_cancelled:     str = ""
    status_tools_ok:      str = ""
    status_tools_update:  str = ""
    status_ytdlp_missing: str = ""
    err_url_empty:        str = ""
    err_url_invalid:      str = ""
    err_max_parallel:     str = ""  # {n}

    # history_screen
    header_history:       str = ""
    history_empty:        str = ""
    filter_all:           str = ""
    filter_completed:     str = ""
    filter_failed:        str = ""
    filter_cancelled:     str = ""
    btn_refresh:          str = ""
    btn_open_folder:      str = ""
    btn_delete_record:    str = ""
    status_completed:     str = ""
    status_failed:        str = ""
    status_running:       str = ""
    tag_mp3:              str = ""
    tag_proxy:            str = ""
    tag_cookies:          str = ""
    tag_playlist:         str = ""
    stats_text:           str = ""  # {total} {ok} {fail} {avg}
    stats_avg:            str = ""  # {n}

    # app.py
    proxy_on:             str = ""
    proxy_off:            str = ""
    proxy_tooltip:        str = ""
    nav_history:          str = ""
    appbar_history:       str = ""
    appbar_settings:      str = ""
    appbar_main:          str = ""
    btn_folder:           str = ""
    btn_exit:             str = ""
    folder_select_text:   str = ""

    def fmt(self, key: str, **kwargs) -> str:
        """Получить строку по имени поля и подставить kwargs через format."""
        text = getattr(self, key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text


class Locale:
    DEFAULT_LANG = "en"
    _cache: dict = {}
    _available_cache: list | None = None  # кэш списка доступных языков

    @classmethod
    def load(cls, lang: str | None = None) -> Strings:
        """
        Загрузить locale/<lang>.json и вернуть Strings.
        Если lang не указан, используется язык системной локали.
        При отсутствии файла — fallback на английский.
        """
        lang = cls.default_language() if lang is None else cls.resolve_language(lang)

        if lang in cls._cache:
            return cls._cache[lang]

        locale_dir = os.path.join(os.path.dirname(__file__), "locale")
        path = os.path.join(locale_dir, f"{lang}.json")

        if not os.path.exists(path):
            if lang != cls.DEFAULT_LANG:
                return cls.load(cls.DEFAULT_LANG)
            return Strings()

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return Strings()

        # Заполняем только известные поля — лишние ключи в JSON игнорируются
        known = {f.name for f in fields(Strings)}
        kwargs = {k: v for k, v in data.items() if k in known}
        result = Strings(**kwargs)
        cls._cache[lang] = result
        return result

    @classmethod
    def default_language(cls) -> str:
        """Вернуть доступный язык для системной локали или английский."""
        return cls.resolve_language(cls._system_language_code())

    @classmethod
    def resolve_language(cls, lang: str | None) -> str:
        """Сопоставить код языка с файлами locale/*.json и откатиться на en."""
        requested = cls._normalize_language_code(lang)
        available = {code for code, _ in cls.available()}
        by_normalized = {
            cls._normalize_language_code(code).lower(): code
            for code in available
            if cls._normalize_language_code(code)
        }

        if requested:
            key = requested.lower()
            if key in by_normalized:
                return by_normalized[key]

            base = key.split("_", 1)[0]
            if base in by_normalized:
                return by_normalized[base]

        return cls.DEFAULT_LANG

    @classmethod
    def _system_language_code(cls) -> str | None:
        if sys.platform == "win32":
            code = cls._windows_user_locale()
            if code:
                return code

        for var_name in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
            value = os.environ.get(var_name)
            if value:
                code = cls._normalize_language_code(value)
                if code:
                    return code

        return None

    @staticmethod
    def _windows_user_locale() -> str | None:
        try:
            buffer = ctypes.create_unicode_buffer(85)
            length = ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer))
            return buffer.value if length else None
        except Exception:
            return None

    @staticmethod
    def _normalize_language_code(value: str | None) -> str:
        if not value:
            return ""

        code = str(value).strip()
        if not code:
            return ""

        code = code.split(":", 1)[0]
        code = code.split(".", 1)[0]
        code = code.split("@", 1)[0]
        code = code.replace("-", "_")

        if code.lower() in {"c", "posix"}:
            return ""

        return code

    @classmethod
    def available(cls) -> list[tuple[str, str]]:
        """
        Вернуть список (code, native_name) доступных языков.
        Имя читается из самого JSON (ключ '_name' если есть, иначе code).
        Результат кэшируется — файлы читаются только при первом вызове.
        """
        if cls._available_cache is not None:
            return cls._available_cache
        locale_dir = os.path.join(os.path.dirname(__file__), "locale")
        result = []
        try:
            for fname in sorted(os.listdir(locale_dir)):
                if fname.endswith(".json"):
                    code = fname[:-5]
                    try:
                        with open(os.path.join(locale_dir, fname), encoding="utf-8") as f:
                            data = json.load(f)
                        name = data.get("_name", code)
                    except Exception:
                        name = code
                    result.append((code, name))
        except Exception:
            pass
        cls._available_cache = result
        return result
