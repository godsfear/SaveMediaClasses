"""
ui_utils.py — мелкие UI-хелперы, общие для экранов.

Здесь живёт то, что раньше дублировалось в экранах и не принадлежит ни одному
из них: открытие пути системным способом и форматирование дат/длительностей
для карточек. Цветовые токены темы — в config (SEVERITY_TOKENS и др.), не здесь.
"""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
from typing import Optional

from app_logging import get_logger


def open_path(path: str) -> None:
    """Открыть путь системным способом: для папки — проводник, для файла —
    ассоциированное приложение (плеер, редактор и т.п.)."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        get_logger("app").exception("Failed to open path: %s", path)


def fmt_ts(ts: Optional[float]) -> str:
    """Unix-время → короткая дата для карточек ('—' если времени нет)."""
    if not ts:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%d %b %Y  %H:%M")
    except Exception:
        return "—"


def fmt_duration(started: Optional[float], finished: Optional[float]) -> str:
    """Длительность '  •  Xм Yс' между двумя метками ('' если неприменимо)."""
    if not started or not finished:
        return ""
    secs = int(finished - started)
    if secs < 1:
        return ""
    if secs < 60:
        return f"  •  {secs}с"
    return f"  •  {secs // 60}м {secs % 60}с"
