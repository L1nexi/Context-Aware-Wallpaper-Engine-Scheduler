from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

def _format_field_path(path: tuple[str | int, ...]) -> str:
    if not path:
        return ""

    rendered: list[str] = []
    for part in path:
        if isinstance(part, int):
            if rendered:
                rendered[-1] = f"{rendered[-1]}[{part}]"
            else:
                rendered.append(f"[{part}]")
            continue

        if not rendered:
            rendered.append(part)
            continue

        if IDENTIFIER_RE.fullmatch(part):
            rendered.append(part)
        else:
            rendered[-1] = f"{rendered[-1]}['{part}']"
    return ".".join(rendered)


@dataclass(frozen=True)
class ConfigIssue:
    source_file: str
    field_path: tuple[str | int, ...]
    message: str
    code: str = "config_error"

    def render(self) -> str:
        field_path = _format_field_path(self.field_path)
        if field_path:
            return f"{self.source_file} > {field_path}: {self.message}"
        return f"{self.source_file}: {self.message}"


class ConfigLoadError(ValueError):
    def __init__(self, issues: list[ConfigIssue]):
        self.issues = issues
        super().__init__(self.__str__())

    def __str__(self) -> str:
        return "\n".join(issue.render() for issue in self.issues)


def raise_config_error(
    source_file: str,
    message: str,
    field_path: tuple[str | int, ...] = (),
    code: str = "config_error",
) -> None:
    raise ConfigLoadError(
        [
            ConfigIssue(
                source_file=source_file,
                field_path=field_path,
                message=message,
                code=code,
            )
        ]
    )


def validation_issues(source_file: str, exc: ValidationError) -> list[ConfigIssue]:
    return [
        ConfigIssue(
            source_file=source_file,
            field_path=tuple(err.get("loc", ())),
            message=err["msg"],
            code=err.get("type", "validation_error"),
        )
        for err in exc.errors()
    ]


ModelT = TypeVar("ModelT", bound=BaseModel)


def model_validate_document(
    model: type[ModelT],
    data: dict[str, Any],
    source_file: str,
) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(validation_issues(source_file, exc)) from exc
