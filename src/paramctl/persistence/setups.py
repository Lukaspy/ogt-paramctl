"""YAML save/load for ``Setup`` instances with a schema-version migration spine.

The on-disk format is the JSON-mode dump of the Pydantic model serialised
with PyYAML. Enums round-trip as their string values; dicts keyed on
``ChannelId`` get string keys.

Schema versioning (per CLAUDE.md §96) is mandatory: the ``schema_version``
field on a saved file must match :data:`paramctl.models.CURRENT_SCHEMA_VERSION`,
or be migratable to it. This module provides the migration spine — a chain
of ``(from_version, migration_fn)`` entries — that gets populated when a
breaking schema bump lands. Today there is only v1, so the chain is empty.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from ..models.setup import CURRENT_SCHEMA_VERSION, Setup

logger = logging.getLogger(__name__)


class SetupFileError(Exception):
    """Raised for any structural problem reading a setup file."""


_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    # When v2 ships, populate as:
    #   1: _migrate_v1_to_v2,
    # Each function takes a dict and returns the v(n+1) dict, including a
    # bumped ``schema_version`` field.
}


def dump_setup_yaml(setup: Setup) -> str:
    """Serialise a ``Setup`` to a YAML string.

    The format is a plain mapping of every Pydantic field; no custom tags.
    Keys preserve insertion order so the output is reasonable to read.
    """
    payload = setup.model_dump(mode="json")
    text: str = yaml.safe_dump(
        _stringify_channel_keys(payload),
        sort_keys=False,
        default_flow_style=False,
    )
    return text


def load_setup_yaml(text: str) -> Setup:
    """Parse a YAML string into a ``Setup``, migrating older schema versions.

    Raises:
        SetupFileError: If the payload is not a mapping, lacks a recognised
            ``schema_version``, or fails Pydantic validation after migration.
    """
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise SetupFileError(
            f"setup YAML root must be a mapping; got {type(data).__name__}"
        )

    return _validate(_apply_migrations(dict(data)))


def save_setup(path: Path | str, setup: Setup) -> None:
    """Write a ``Setup`` to ``path`` as YAML."""
    Path(path).write_text(dump_setup_yaml(setup))


def load_setup(path: Path | str) -> Setup:
    """Read a ``Setup`` YAML from ``path``."""
    try:
        text = Path(path).read_text()
    except OSError as exc:
        raise SetupFileError(f"could not read {path}: {exc}") from exc
    return load_setup_yaml(text)


def _apply_migrations(data: dict[str, Any]) -> dict[str, Any]:
    if "schema_version" not in data:
        raise SetupFileError("setup YAML is missing the required 'schema_version' field")

    version = data["schema_version"]
    if not isinstance(version, int):
        raise SetupFileError(
            f"schema_version must be an integer; got {version!r}"
        )

    visited: set[int] = set()
    while version != CURRENT_SCHEMA_VERSION:
        if version in visited:
            raise SetupFileError(
                f"migration loop detected at schema_version={version}"
            )
        visited.add(version)
        migration = _MIGRATIONS.get(version)
        if migration is None:
            raise SetupFileError(
                f"cannot migrate setup from schema_version={version} "
                f"to {CURRENT_SCHEMA_VERSION}; no migration registered"
            )
        data = migration(data)
        version = data.get("schema_version", version)

    return data


def _validate(data: dict[str, Any]) -> Setup:
    try:
        return Setup.model_validate(data)
    except Exception as exc:  # ValidationError, but keep the catch broad
        raise SetupFileError(f"setup payload failed validation: {exc}") from exc


def _stringify_channel_keys(payload: dict[str, Any]) -> dict[str, Any]:
    """YAML cannot round-trip enum-keyed dicts cleanly; force string keys.

    Pydantic's ``model_dump(mode='json')`` already converts enum *values* to
    strings, but dict *keys* sometimes stay as enum instances. We walk the
    payload and coerce them to plain strings so ``yaml.safe_dump`` is happy.
    """
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            cleaned[key] = {
                (k.value if hasattr(k, "value") else str(k)): v for k, v in value.items()
            }
        else:
            cleaned[key] = value
    return cleaned


__all__ = [
    "SetupFileError",
    "dump_setup_yaml",
    "load_setup",
    "load_setup_yaml",
    "save_setup",
]
