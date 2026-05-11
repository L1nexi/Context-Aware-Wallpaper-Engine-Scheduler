from __future__ import annotations

import os
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from utils.config_errors import ConfigIssue, ConfigLoadError, raise_config_error


def _node_child_path(path: tuple[str | int, ...], key_node: Node) -> tuple[str | int, ...]:
    if isinstance(key_node, ScalarNode):
        return path + (str(key_node.value),)
    return path + ("<key>",)


def _inspect_node(
    node: Node | None,
    source_file: str,
    path: tuple[str | int, ...] = (),
    visited: set[int] | None = None,
) -> list[ConfigIssue]:
    if node is None:
        return []

    if visited is None:
        visited = set()

    node_id = id(node)
    if node_id in visited:
        return []
    visited.add(node_id)

    issues: list[ConfigIssue] = []
    if isinstance(node, MappingNode):
        seen_keys: set[str] = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode):
                key = str(key_node.value)
                if key in seen_keys:
                    issues.append(
                        ConfigIssue(
                            source_file=source_file,
                            field_path=path + (key,),
                            message=f"duplicate YAML key '{key}'",
                            code="yaml_duplicate_key",
                            line=key_node.start_mark.line + 1,
                            column=key_node.start_mark.column + 1,
                        )
                    )
                else:
                    seen_keys.add(key)

            issues.extend(_inspect_node(value_node, source_file, _node_child_path(path, key_node), visited))
        return issues

    if isinstance(node, SequenceNode):
        for index, child in enumerate(node.value):
            issues.extend(_inspect_node(child, source_file, path + (index,), visited))

    return issues


def _yaml_error_location(exc: yaml.YAMLError) -> tuple[int | None, int | None]:
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    if mark is None:
        return None, None
    return mark.line + 1, mark.column + 1


class YamlDocumentReader:
    def read_mapping(self, path: str) -> dict[str, Any]:
        source_file = os.path.basename(path)

        try:
            with open(path, "r", encoding="utf-8") as file:
                text = file.read()
        except FileNotFoundError:
            raise_config_error(
                source_file,
                "missing required file",
                code="missing_file",
            )
        except UnicodeDecodeError as exc:
            raise_config_error(
                source_file,
                f"file must be valid UTF-8: {exc}",
                code="utf8_decode_error",
            )
        except OSError as exc:
            raise_config_error(
                source_file,
                f"failed to read file: {exc}",
                code="file_read_error",
            )

        try:
            node = yaml.compose(text)
        except yaml.YAMLError as exc:
            line, column = _yaml_error_location(exc)
            raise_config_error(
                source_file,
                f"invalid YAML: {exc}",
                code="invalid_yaml",
                line=line,
                column=column,
            )

        node_issues = _inspect_node(node, source_file)
        if node_issues:
            raise ConfigLoadError(node_issues)

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            line, column = _yaml_error_location(exc)
            raise_config_error(
                source_file,
                f"invalid YAML: {exc}",
                code="invalid_yaml",
                line=line,
                column=column,
            )

        if data is None:
            data = {}

        if not isinstance(data, dict):
            line = node.start_mark.line + 1 if node is not None else None
            column = node.start_mark.column + 1 if node is not None else None
            raise_config_error(
                source_file,
                "top-level YAML document must be a mapping",
                code="yaml_top_level_mapping_required",
                line=line,
                column=column,
            )

        return data
