import sys
from pathlib import Path


class AppPaths:

    @staticmethod
    def app_dir() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent

        return Path(__file__).resolve().parent

    @classmethod
    def config_file(cls) -> Path:
        return cls.app_dir() / "config.json"

    @classmethod
    def db_file(cls) -> Path:
        return cls.app_dir() / "savemedia.db"

    @classmethod
    def log_file(cls) -> Path:
        return cls.app_dir() / "savemedia.log"

    @classmethod
    def tools_dir(cls) -> Path:
        return cls.app_dir() / "tools"

    @classmethod
    def locale_dir(cls) -> Path:
        return cls.app_dir() / "locale"