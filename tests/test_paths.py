"""AppPaths: пути, которые должны работать и в dev, и в сборке flet build."""

import tomllib

from paths import AppPaths


def test_pyproject_is_found_next_to_code_not_exe(tmp_path):
    """В flet build app_dir — папка exe, а pyproject.toml лежит в app/ рядом с
    модулями. Версия для окна About должна читаться при любом app_dir."""
    with open(AppPaths(app_dir=tmp_path).pyproject, "rb") as f:
        assert tomllib.load(f)["project"]["version"]
