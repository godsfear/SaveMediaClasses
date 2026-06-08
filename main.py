import flet as ft

from app import SaveMediaApp
from paths import AppPaths

if __name__ == "__main__":
    ft.run(SaveMediaApp().main, assets_dir=str(AppPaths.detect().assets_dir))
