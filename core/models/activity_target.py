from __future__ import annotations


def normalize_match_text(value: str, *, case_sensitive: bool) -> str:
    """Return the canonical text used by literal activity matchers."""

    return value if case_sensitive else value.casefold()


def normalize_process_name(value: str, *, case_sensitive: bool) -> str:
    """Normalize a process name while treating the optional ``.exe`` suffix consistently."""

    normalized = normalize_match_text(value, case_sensitive=case_sensitive)
    suffix = ".exe"
    return normalized[: -len(suffix)] if normalized.endswith(suffix) else normalized
