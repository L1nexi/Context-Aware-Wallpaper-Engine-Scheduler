import json
import logging
import os
from typing import Dict, List, Any

logger = logging.getLogger("WEScheduler.Config")

class ConfigLoader:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found at: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        logger.info(f"Config loaded from: {self.config_path}")
        return self.config

    def get_playlists(self) -> List[Dict[str, Any]]:
        return self.config.get("playlists", [])

    def get_policies(self) -> Dict[str, Any]:
        return self.config.get("policies", {})

    def get_we_path(self) -> str:
        return self.config.get("we_path", "")

    def get_disturbance_config(self) -> Dict[str, int]:
        return self.config.get("disturbance", {
            "idle_threshold": 30,
            "min_interval": 60,
            "force_interval": 300
        })
