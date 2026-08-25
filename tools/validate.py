#!/usr/bin/env python3
"""Validate all IndexLoom YAML definitions against the current schema."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "v1alpha1" / "indexer.schema.json"
DEFINITION_ROOTS = (ROOT / "definitions", ROOT / "examples")


def definition_paths() -> Iterable[Path]:
    """Yield definition files in stable order without following symlink files."""
    for directory in DEFINITION_ROOTS:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.yml")):
            if path.is_file() and not path.is_symlink():
                yield path


def load_yaml(path: Path) -> Any:
    """Load exactly one YAML document."""
    with path.open("r", encoding="utf-8") as stream:
        documents = list(yaml.safe_load_all(stream))
    if len(documents) != 1:
        raise ValueError("file must contain exactly one YAML document")
    return documents[0]


def format_path(parts: Iterable[object]) -> str:
    """Format a JSON path for concise CI output."""
    rendered = "$"
    for part in parts:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered


def main() -> int:
    """Validate schema compatibility, IDs, filenames, and duplicates."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    seen_ids: dict[str, Path] = {}
    checked = 0

    for path in definition_paths():
        checked += 1
        relative = path.relative_to(ROOT)
        try:
            definition = load_yaml(path)
        except (OSError, ValueError, yaml.YAMLError) as error:
            errors.append(f"{relative}: {error}")
            continue

        for error in sorted(validator.iter_errors(definition), key=lambda item: list(item.path)):
            errors.append(f"{relative}:{format_path(error.path)}: {error.message}")

        if not isinstance(definition, dict):
            continue
        metadata = definition.get("metadata")
        identifier = metadata.get("id") if isinstance(metadata, dict) else None
        if not isinstance(identifier, str):
            continue
        if path.stem != identifier:
            errors.append(f"{relative}: filename must be {identifier}.yml")
        if identifier in seen_ids:
            errors.append(
                f"{relative}: duplicate metadata.id {identifier!r}; "
                f"first seen in {seen_ids[identifier].relative_to(ROOT)}"
            )
        else:
            seen_ids[identifier] = path

    if errors:
        print("Definition validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Validated {checked} definition file(s) with no errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
