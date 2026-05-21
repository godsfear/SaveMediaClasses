import json
import os
from typing import Any, Dict

from config import DEFAULT_CONFIG, safe_str, safe_int, get_fallback_bool


class ConfigManager:

    def __init__(self, config_file: str) -> None:
        self.config_file = config_file

    def load(self) -> Dict[str, Any]:
        config_data: Dict[str, Any] = DEFAULT_CONFIG.copy()
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        config_data = loaded
            except Exception:
                pass
        return config_data

    def load_window_geometry(self) -> Dict[str, int]:
        init_w = safe_int(DEFAULT_CONFIG["window"]["width"],  600)
        init_h = safe_int(DEFAULT_CONFIG["window"]["height"], 650)
        init_l = safe_int(DEFAULT_CONFIG["window"]["left"],   100)
        init_t = safe_int(DEFAULT_CONFIG["window"]["top"],    100)

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        window_geo = loaded.get("window", {})
                        if isinstance(window_geo, dict):
                            init_w = safe_int(window_geo.get("width"),  init_w)
                            init_h = safe_int(window_geo.get("height"), init_h)
                            init_l = safe_int(window_geo.get("left"),   init_l)
                            init_t = safe_int(window_geo.get("top"),    init_t)
            except Exception:
                pass

        return {"width": init_w, "height": init_h, "left": init_l, "top": init_t}

    def save(self, config_data: Dict[str, Any]) -> None:
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except OSError:
            pass
