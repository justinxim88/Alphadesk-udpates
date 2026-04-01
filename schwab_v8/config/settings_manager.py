"""Settings Manager v5 — hotkeys, paper trading, preferences."""

import json, os

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "settings.json")

DEFAULTS = {
    "app_key": "", "app_secret": "",
    "paper_mode": False, "paper_hash": "", "live_hash": "",
    "default_session": "NORMAL", "default_duration": "DAY",
    "default_qty": 1, "confirm_orders": False,
    "hotkeys": {
        "buy_market":     "Ctrl+B",
        "sell_market":    "Ctrl+S",
        "flatten":        "Ctrl+F",
        "cancel_all":     "Ctrl+X",
        "reverse":        "Ctrl+R",
        "refresh":        "F5",
        "chart_zoom":     "Ctrl+Z",
        "chart_recenter": "Ctrl+0",
    },
    "default_period": "1M",
    "default_indicators": ["Volume"],
    "font_size": 12,
    "show_dom": True,
}

def load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH) as f:
                saved = json.load(f)
            merged = dict(DEFAULTS); merged.update(saved)
            if "hotkeys" in saved:
                merged["hotkeys"] = {**DEFAULTS["hotkeys"], **saved["hotkeys"]}
            return merged
        except: pass
    return dict(DEFAULTS)

def save_settings(data: dict):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)

def get_credentials():
    s = load_settings(); return s.get("app_key",""), s.get("app_secret","")

def set_credentials(app_key: str, app_secret: str):
    s = load_settings(); s["app_key"] = app_key; s["app_secret"] = app_secret; save_settings(s)

def get(key: str, default=None):
    return load_settings().get(key, default)

def set_value(key: str, value):
    s = load_settings(); s[key] = value; save_settings(s)
