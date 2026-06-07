import flet as ft
from pathlib import Path

from app import SaveMediaApp

if __name__ == "__main__":
    ft.run(SaveMediaApp().main, assets_dir=str(Path(__file__).parent))
