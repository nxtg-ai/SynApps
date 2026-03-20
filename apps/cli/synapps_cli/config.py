import json
import os
from pathlib import Path

DEFAULT_URL = "http://localhost:8000"
CONFIG_PATH = Path.home() / ".synapps" / "config.json"


def get_config() -> dict:
    cfg = {"url": DEFAULT_URL, "token": None}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            cfg.update(data)
        except (json.JSONDecodeError, OSError) as exc:
            # config file unreadable — fall through to env vars
            pass  # noqa: S110
    cfg["url"] = os.environ.get("SYNAPPS_URL", cfg["url"]).rstrip("/")
    cfg["token"] = os.environ.get("SYNAPPS_TOKEN", cfg.get("token"))
    return cfg
