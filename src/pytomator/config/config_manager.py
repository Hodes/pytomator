import json
from pathlib import Path

from pytomator.config.default_config import get_default_config
from pytomator.core.events import EventEmitter


class ConfigManager(EventEmitter):
    
    @staticmethod
    def get_instance():
        if not hasattr(ConfigManager, "_instance"):
            ConfigManager._instance = ConfigManager()
        return ConfigManager._instance
    
    def __init__(self):
        super().__init__()
        self.CONFIG_PATH = Path.home() / ".pytomator"
        self.CONFIG_FILE = self.CONFIG_PATH / "config.json"
        self.config = self.load_config()

    def load_config(self):
        config = {}
        if not self.CONFIG_FILE.exists():
            config = get_default_config()
        else:
            with open(self.CONFIG_FILE, "r") as f:
                config = json.load(f)
        
        self.emit("config_loaded", config)
        self.apply_config(config)
        return config

    def save_config(self, data):
        self.CONFIG_PATH.mkdir(exist_ok=True)
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
            self.emit("config_saved", data)
        self.apply_config(data)
            
    def apply_config(self, data):
        if not isinstance(data, dict):
            return
        self.emit("config_applied", data)
