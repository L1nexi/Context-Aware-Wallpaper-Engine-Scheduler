import json
import os

class ConfigLoader:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = {}

    def load(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found at: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        return self.config

    def get_playlists(self):
        return self.config.get("playlists", [])

    def get_policies(self):
        return self.config.get("policies", {})
