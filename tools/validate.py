#!/usr/bin/env python3
"""Validate the IndexLoom catalog, provenance, manifest, and examples."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from import_upstreams import GENERATED_MARKER, Yaml12Loader, canonical_json, sha256
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "v1alpha1" / "indexer.schema.json"
MANIFEST_PATH = ROOT / "catalog.json"
DEFINITIONS = ROOT / "definitions"
EXAMPLES = ROOT / "examples"


def definition_paths(directory: Path) -> Iterable[Path]:
    """Yield definition files in stable order without following symlinks."""
    if not directory.exists():
        return
    for path in sorted(directory.rglob("*.yml")):
        if path.is_file() and not path.is_symlink():
            yield path


def load_yaml(path: Path) -> Any:
    """Load exactly one YAML 1.2 document."""
    documents = list(yaml.load_all(path.read_text(encoding="utf-8"), Loader=Yaml12Loader))
    if len(documents) != 1:
        raise ValueError("file must contain exactly one YAML document")
    return documents[0]


def format_path(parts: Iterable[object]) -> str:
    """Format a JSON path for concise CI output."""
    rendered = "$"
    for part in parts:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered


def reconstruct_source(definition: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct the source Cardigann mapping for semantic digest checks."""
    metadata = definition["metadata"]
    provenance = definition["provenance"]["source"]
    spec = definition["spec"]
    implementation = spec["implementation"]

    source: dict[str, Any] = {"id": provenance["sourceId"]}
    if "replacedIds" in spec:
        source["replaces"] = spec["replacedIds"]
    source["name"] = metadata["name"]
    source["description"] = metadata["description"]
    source["language"] = metadata["language"]
    source["type"] = spec["privacy"]
    source["encoding"] = implementation["encoding"]
    if "followRedirects" in implementation:
        source["followredirect"] = implementation["followRedirects"]
    if "testLinkTorrent" in implementation:
        source["testlinktorrent"] = implementation["testLinkTorrent"]
    if "requestDelaySeconds" in implementation:
        source["requestDelay"] = implementation["requestDelaySeconds"]
    source["links"] = spec["baseUrls"]
    if "legacyUrls" in spec:
        source["legacylinks"] = spec["legacyUrls"]
    if "certificates" in implementation:
        source["certificates"] = implementation["certificates"]
    source["caps"] = implementation["capabilities"]
    source["settings"] = implementation["settings"]
    if "authentication" in implementation:
        source["login"] = implementation["authentication"]
    source["search"] = implementation["search"]
    if "download" in implementation:
        source["download"] = implementation["download"]
    return source


def load_manifest(errors: list[str]) -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"catalog.json: {error}")
        return {}
    required = {
        "catalogVersion",
        "definitionSchema",
        "generatedBy",
        "definitionCount",
        "sources",
        "deduplication",
        "definitions",
    }
    missing = required - set(manifest) if isinstance(manifest, dict) else required
    if missing:
        errors.append(f"catalog.json: missing fields {sorted(missing)}")
    return manifest if isinstance(manifest, dict) else {}


def manifest_entries(manifest: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    entries = manifest.get("definitions", [])
    if not isinstance(entries, list):
        errors.append("catalog.json: definitions must be an array")
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            errors.append(f"catalog.json: invalid definition entry at index {position}")
            continue
        identifier = entry["id"]
        if identifier in indexed:
            errors.append(f"catalog.json: duplicate entry {identifier!r}")
        indexed[identifier] = entry
    return indexed


def validate_file(
    path: Path,
    validator: Draft202012Validator,
    seen_ids: dict[str, Path],
    errors: list[str],
) -> dict[str, Any] | None:
    relative = path.relative_to(ROOT)
    try:
        definition = load_yaml(path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        errors.append(f"{relative}: {error}")
        return None

    for error in sorted(validator.iter_errors(definition), key=lambda item: list(item.path)):
        errors.append(f"{relative}:{format_path(error.path)}: {error.message}")
    if not isinstance(definition, dict):
        return None

    metadata = definition.get("metadata")
    identifier = metadata.get("id") if isinstance(metadata, dict) else None
    if not isinstance(identifier, str):
        return definition
    if path.stem != identifier:
        errors.append(f"{relative}: filename must be {identifier}.yml")
    if identifier in seen_ids:
        errors.append(
            f"{relative}: duplicate metadata.id {identifier!r}; "
            f"first seen in {seen_ids[identifier].relative_to(ROOT)}"
        )
    else:
        seen_ids[identifier] = path
    return definition


def validate_catalog_definition(
    path: Path,
    definition: dict[str, Any],
    entry: dict[str, Any] | None,
    errors: list[str],
) -> None:
    relative = path.relative_to(ROOT)
    first_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:4]
    if GENERATED_MARKER not in first_lines:
        errors.append(f"{relative}: missing generated-file marker")

    source = definition.get("provenance", {}).get("source", {})
    if isinstance(source, dict) and isinstance(source.get("contentSha256"), str):
        actual_content_sha = sha256(canonical_json(reconstruct_source(definition)))
        if source["contentSha256"] != actual_content_sha:
            errors.append(f"{relative}: provenance contentSha256 does not match reconstructed source")

    if entry is None:
        errors.append(f"{relative}: missing from catalog.json")
        return
    expected_path = entry.get("path")
    if expected_path != relative.as_posix():
        errors.append(f"{relative}: manifest path is {expected_path!r}")
    actual_sha = sha256(path.read_bytes())
    if entry.get("sha256") != actual_sha:
        errors.append(f"{relative}: manifest SHA-256 does not match file")
    if entry.get("sourceProject") != source.get("project"):
        errors.append(f"{relative}: manifest sourceProject does not match provenance")
    if entry.get("sourcePath") != source.get("path"):
        errors.append(f"{relative}: manifest sourcePath does not match provenance")


def main() -> int:
    """Validate schema compatibility, IDs, provenance, manifest, and hashes."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    seen_ids: dict[str, Path] = {}
    manifest = load_manifest(errors)
    entries = manifest_entries(manifest, errors)
    checked_catalog = 0
    checked_examples = 0

    actual_catalog_ids: set[str] = set()
    for path in definition_paths(DEFINITIONS):
        checked_catalog += 1
        definition = validate_file(path, validator, seen_ids, errors)
        if not isinstance(definition, dict):
            continue
        metadata = definition.get("metadata", {})
        identifier = metadata.get("id") if isinstance(metadata, dict) else None
        if not isinstance(identifier, str):
            continue
        actual_catalog_ids.add(identifier)
        validate_catalog_definition(path, definition, entries.get(identifier), errors)

    for path in definition_paths(EXAMPLES):
        checked_examples += 1
        validate_file(path, validator, seen_ids, errors)

    manifest_ids = set(entries)
    for identifier in sorted(manifest_ids - actual_catalog_ids):
        errors.append(f"catalog.json: entry {identifier!r} has no definition file")
    if manifest.get("definitionCount") != checked_catalog:
        errors.append(
            f"catalog.json: definitionCount={manifest.get('definitionCount')!r}, "
            f"actual={checked_catalog}"
        )
    if manifest.get("definitionSchema") != "indexloom.io/v1alpha1":
        errors.append("catalog.json: unexpected definitionSchema")
    if manifest.get("generatedBy") != "indexloom-importer/v1":
        errors.append("catalog.json: unexpected generatedBy")

    if errors:
        print("Definition validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        f"Validated {checked_catalog} catalog definition(s), "
        f"{checked_examples} example(s), provenance, and manifest with no errors."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
