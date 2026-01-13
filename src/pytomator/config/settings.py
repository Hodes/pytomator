import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".pytomator"
CONFIG_FILE = CONFIG_PATH / "config.json"


def load_config():
    if not CONFIG_FILE.exists():
        return {}

    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def save_config(data):
    CONFIG_PATH.mkdir(exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
