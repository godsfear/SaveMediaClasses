"""Тесты classify_version / status_needs_update — единый источник сравнения версий."""

import pytest

from managers.tool_specs import (
    classify_version, remote_is_known, status_needs_update,
    TOOL_VERSION_MISSING, TOOL_VERSION_CALL_ERROR, TOOL_VERSION_REMOTE_ERR,
    TOOL_VERSION_UNKNOWN, TOOL_VERSION_NEEDS_RUNTIME,
    STATUS_OK, STATUS_OUTDATED, STATUS_MISSING, STATUS_ERROR,
)


@pytest.mark.parametrize("local,remote,expected", [
    (TOOL_VERSION_MISSING,       "1.2",                 STATUS_MISSING),
    (TOOL_VERSION_CALL_ERROR,    "1.2",                 STATUS_ERROR),
    (TOOL_VERSION_NEEDS_RUNTIME, "1.2",                 STATUS_ERROR),
    ("1.2",                      TOOL_VERSION_REMOTE_ERR, STATUS_ERROR),
    ("1.2",                      TOOL_VERSION_UNKNOWN,  STATUS_ERROR),
    ("1.2",                      "1.2",                 STATUS_OK),
    ("7.1.1-full_build",         "7.1.1",               STATUS_OK),   # remote in local
    ("7.1",                      "7.1.1",               STATUS_OK),   # local in remote
    ("2024.01.01",               "2025.06.01",          STATUS_OUTDATED),
])
def test_classify_version(local, remote, expected):
    assert classify_version(local, remote) == expected


def test_remote_is_known():
    assert remote_is_known("1.0")
    assert not remote_is_known(TOOL_VERSION_REMOTE_ERR)
    assert not remote_is_known(TOOL_VERSION_UNKNOWN)


@pytest.mark.parametrize("status,remote,expected", [
    (STATUS_MISSING,  "1.0",                  True),
    (STATUS_OUTDATED, "1.0",                  True),
    (STATUS_OK,       "1.0",                  False),
    (STATUS_ERROR,    "1.0",                  False),
    # Без валидной удалённой версии обновлять нечего
    (STATUS_MISSING,  TOOL_VERSION_REMOTE_ERR, False),
    (STATUS_OUTDATED, TOOL_VERSION_UNKNOWN,    False),
])
def test_status_needs_update(status, remote, expected):
    assert status_needs_update(status, remote) is expected
