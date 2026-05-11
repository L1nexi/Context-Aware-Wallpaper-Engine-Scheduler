from __future__ import annotations

import logging
import os
from typing import Optional

from utils.config_errors import ConfigIssue, ConfigLoadError, model_validate_document
from utils.config_documents import (
    ActivityFileConfig,
    ConfigFiles,
    ContextFileConfig,
    PlaylistsFileConfig,
    SchedulerFileConfig,
    SchedulingFileConfig,
    TagsFileConfig,
)
from utils.runtime_config import SchedulerConfig
from utils.yaml_document_reader import YamlDocumentReader

logger = logging.getLogger("WEScheduler.Config")

CONFIG_FILE_NAMES = (
    "scheduler.yaml",
    "playlists.yaml",
    "tags.yaml",
    "activity.yaml",
    "context.yaml",
    "scheduling.yaml",
)

CONFIG_FILE_MODELS = {
    "scheduler.yaml": SchedulerFileConfig,
    "playlists.yaml": PlaylistsFileConfig,
    "tags.yaml": TagsFileConfig,
    "activity.yaml": ActivityFileConfig,
    "context.yaml": ContextFileConfig,
    "scheduling.yaml": SchedulingFileConfig,
}


class ConfigLoader:
    def __init__(
        self,
        config_dir: str,
        reader: YamlDocumentReader | None = None,
    ):
        self.config_dir = config_dir
        self.reader = reader or YamlDocumentReader()
        self.config: Optional[SchedulerConfig] = None

    def _path_for(self, file_name: str) -> str:
        return os.path.join(self.config_dir, file_name)

    def required_paths(self) -> dict[str, str]:
        return {file_name: self._path_for(file_name) for file_name in CONFIG_FILE_NAMES}

    def fingerprint(self) -> tuple[tuple[str, bool, int], ...]:
        fingerprint: list[tuple[str, bool, int]] = []
        for file_name, file_path in self.required_paths().items():
            try:
                stat = os.stat(file_path)
            except FileNotFoundError:
                fingerprint.append((file_name, False, 0))
            else:
                fingerprint.append((file_name, True, stat.st_mtime_ns))
        return tuple(fingerprint)

    @classmethod
    def load_configured_wallpaper_engine_path(cls, config_dir: str) -> str | None:
        loader = cls(config_dir)
        scheduler_data = loader.reader.read_mapping(loader._path_for("scheduler.yaml"))
        scheduler_file = model_validate_document(
            SchedulerFileConfig,
            scheduler_data,
            "scheduler.yaml",
        )
        return scheduler_file.runtime.wallpaper_engine_path

    def load_files(self) -> ConfigFiles:
        if not os.path.isdir(self.config_dir):
            raise FileNotFoundError(f"Config directory not found at: {self.config_dir}")

        documents: dict[str, object] = {}
        issues: list[ConfigIssue] = []

        for file_name in CONFIG_FILE_NAMES:
            try:
                data = self.reader.read_mapping(self._path_for(file_name))
                documents[file_name] = model_validate_document(
                    CONFIG_FILE_MODELS[file_name],
                    data,
                    file_name,
                )
            except ConfigLoadError as exc:
                issues.extend(exc.issues)

        if issues:
            raise ConfigLoadError(issues)

        return ConfigFiles(
            scheduler=documents["scheduler.yaml"],
            playlists=documents["playlists.yaml"],
            tags=documents["tags.yaml"],
            activity=documents["activity.yaml"],
            context=documents["context.yaml"],
            scheduling=documents["scheduling.yaml"],
        )

    def load_verified_config(self) -> SchedulerConfig:
        files = self.load_files()
        self.config = files.to_verified_scheduler_config()
        logger.info("Config loaded from directory: %s", self.config_dir)
        return self.config
