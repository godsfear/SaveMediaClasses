"""
config/utils.py — примитивные хелперы без зависимостей от остального проекта:
безопасные преобразования, hex-цвета, разбор URL.
"""

import os
from typing import Any, Dict


def hex_to_flet(hex_str: str) -> str:
    h = hex_str.strip().lstrip("#").upper()
    if len(h) == 6 and all(c in "0123456789ABCDEF" for c in h):
        return f"#{h}"
    return "#FFFFFF"


def is_valid_hex(value: str) -> bool:
    h = value.strip().lstrip("#").upper()
    return len(h) == 6 and all(c in "0123456789ABCDEF" for c in h)


def download_display_name(url: str) -> str:
    """Человекочитаемое имя загрузки из URL.

    magnet — параметр dn (display name), он же реальное имя торрента;
    остальные ссылки возвращаются как есть (для yt-dlp имя берётся из метаданных
    отдельно, у прямых http-ссылок имя файла и так видно в самом URL)."""
    from urllib.parse import urlparse, parse_qs, unquote
    u = safe_str(url).strip()
    if u.lower().startswith("magnet:"):
        try:
            dn = parse_qs(urlparse(u).query).get("dn", [""])[0]
            if dn:
                return unquote(dn)
        except Exception:
            pass
    # Локальный .torrent/.metalink — показываем имя файла, а не весь путь.
    if u.lower().endswith((".torrent", ".metalink")):
        return os.path.basename(u.replace("\\", "/")) or u
    return u


def magnet_btih(url: str) -> str:
    """BitTorrent info-hash (btih) из magnet-ссылки в нижнем регистре; '' если нет.

    Лежит прямо в URL: magnet:?xt=urn:btih:<HASH>&... — отдельно хранить не нужно.
    Идентифицирует содержимое торрента независимо от трекеров (tr) и имени (dn),
    поэтому годится как ключ дедупликации повторных загрузок."""
    import re
    m = re.search(r"xt=urn:btih:([0-9a-zA-Z]+)", safe_str(url), re.IGNORECASE)
    return m.group(1).lower() if m else ""


def parse_url_lines(raw: str) -> list:
    """Разобрать многострочный текст в список ссылок: по строке на ссылку, без
    пустых и дубликатов (порядок сохраняется). Разделитель — только перевод
    строки: URL и пути к .torrent-файлам могут содержать пробелы.
    Используется полем URL главного экрана и слежением за буфером обмена."""
    seen = set()
    urls = []
    for line in (raw or "").splitlines():
        u = line.strip()
        if u and u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def safe_int(value: Any, default: int = 0) -> int:
    if value is None or value == "": return default
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return default


def get_fallback_bool(source_dict: Dict[str, Any], key: str, default_bool: bool) -> bool:
    val = source_dict.get(key)
    return default_bool if val is None or val == "" else bool(val)
