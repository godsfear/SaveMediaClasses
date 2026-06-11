"""Тесты разбора многострочного поля URL (пакетная загрузка, буфер обмена)."""

from config import parse_url_lines
from managers.providers import extract_download_urls


def test_single_url():
    assert parse_url_lines("https://x ") == ["https://x"]


def test_multiple_lines_order_preserved():
    raw = "https://b\nhttps://a\n\nhttps://c\n"
    assert parse_url_lines(raw) == ["https://b", "https://a", "https://c"]


def test_duplicates_removed():
    assert parse_url_lines("https://x\nhttps://x") == ["https://x"]


def test_spaces_inside_line_kept():
    """Пути к .torrent и magnet-ссылки могут содержать пробелы — строка не режется."""
    path = r"C:\My Files\movie name.torrent"
    assert parse_url_lines(path) == [path]


def test_empty_and_none():
    assert parse_url_lines("") == []
    assert parse_url_lines(None) == []
    assert parse_url_lines("\n  \n") == []


def test_crlf_input():
    assert parse_url_lines("https://a\r\nhttps://b") == ["https://a", "https://b"]


# ── Фильтр ссылок из произвольного текста (слежение за буфером) ───────────────

def test_extract_download_urls_filters_noise():
    text = ("просто текст\n"
            "https://youtube.com/watch?v=1\n"
            "ещё заметка без ссылки\n"
            "magnet:?xt=urn:btih:abc\n"
            "C:/files/movie.torrent\n"
            "42\n")
    assert extract_download_urls(text) == [
        "https://youtube.com/watch?v=1",
        "magnet:?xt=urn:btih:abc",
        "C:/files/movie.torrent",
    ]


def test_extract_download_urls_empty_for_plain_text():
    assert extract_download_urls("обычный абзац текста\nи вторая строка") == []
    assert extract_download_urls("") == []
