"""Общая настройка тестов: корень проекта в sys.path + сконфигурированная Locale."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from i18n import Locale          # noqa: E402
from paths import AppPaths       # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _configure_locale():
    """Locale нужна ConfigManager.load (resolve_language) — конфигурируем один раз."""
    Locale.configure(AppPaths.detect())
