import json
import logging
import os
from typing import Dict, List, Any

import jsonschema

logger = logging.getLogger("WEScheduler.Config")

# ---------------------------------------------------------------------------
# JSON Schema for scheduler_config.json
# ---------------------------------------------------------------------------
# Top-level and all known sub-objects use additionalProperties=False to catch
# typos early.  The `policies` object is intentionally open (additionalProperties
# = generic policy schema) so that disabled/experimental policy blocks do not
# cause validation errors; unknown policy names are silently ignored at runtime.
# ---------------------------------------------------------------------------
_POLICY_BASE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "enabled":      {"type": "boolean"},
        "weight_scale": {"type": "number", "minimum": 0},
    },
}

_CONFIG_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["we_path", "playlists"],
    "additionalProperties": False,
    "properties": {
        "we_path":  {"type": "string", "minLength": 1},
        "language": {"type": "string"},
        "playlists": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "tags"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "tags": {
                        "type": "object",
                        "minProperties": 1,
                        "additionalProperties": {"type": "number"},
                    },
                },
            },
        },
        "policies": {
            "type": "object",
            # Unknown policy names are validated as the base schema so they
            # at least have a well-formed structure, but are not hard-blocked.
            "additionalProperties": _POLICY_BASE_SCHEMA,
            "properties": {
                "activity": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "enabled":          {"type": "boolean"},
                        "weight_scale":     {"type": "number", "minimum": 0},
                        "smoothing_window": {"type": "number", "minimum": 1},
                        "rules":            {"type": "object", "additionalProperties": {"type": "string"}},
                        "title_rules":      {"type": "object", "additionalProperties": {"type": "string"}},
                    },
                },
                "time": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "enabled":              {"type": "boolean"},
                        "weight_scale":         {"type": "number", "minimum": 0},
                        "auto":                 {"type": "boolean"},
                        "default_day_start":    {"type": "number", "minimum": 0, "exclusiveMaximum": 24},
                        "default_night_start":  {"type": "number", "minimum": 0, "exclusiveMaximum": 24},
                    },
                },
                "season": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "enabled":      {"type": "boolean"},
                        "weight_scale": {"type": "number", "minimum": 0},
                    },
                },
                "weather": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "enabled":          {"type": "boolean"},
                        "weight_scale":     {"type": "number", "minimum": 0},
                        "api_key":          {"type": "string"},
                        "lat":              {"type": ["string", "number"]},
                        "lon":              {"type": ["string", "number"]},
                        "interval":         {"type": "number", "minimum": 60},
                        "request_timeout":  {"type": "number", "minimum": 1},
                        "warmup_timeout":   {"type": "number", "minimum": 0},
                    },
                },
            },
        },
        "disturbance": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "startup_delay":     {"type": "number", "minimum": 0},
                "idle_threshold":    {"type": "number", "minimum": 0},
                "min_interval":      {"type": "number", "minimum": 0},
                "force_interval":    {"type": "number", "minimum": 0},
                "wallpaper_interval":{"type": "number", "minimum": 0},
                "cpu_threshold":     {"type": "number", "minimum": 0, "maximum": 100},
                "cpu_window":        {"type": "integer", "minimum": 1},
                "fullscreen_defer":  {"type": "boolean"},
            },
        },
    },
}


class ConfigLoader:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found at: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        try:
            jsonschema.validate(self.config, _CONFIG_SCHEMA)
        except jsonschema.ValidationError as exc:
            path = " → ".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "(root)"
            raise ValueError(f"Config validation error at '{path}': {exc.message}") from exc

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
