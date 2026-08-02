import flet as ft

from app import SaveMediaApp
from paths import AppPaths

# `flet run` исполняет файл как __main__, а production bundle импортирует модуль
# `main`. Поэтому запуск нельзя прятать за `if __name__ == "__main__"`: в сборке
# Flutter-окно откроется, но Python-приложение не подключится и останется пустым.
ft.run(SaveMediaApp().main, assets_dir=str(AppPaths.detect().assets_dir))
