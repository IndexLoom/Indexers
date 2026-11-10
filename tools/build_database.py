#!/usr/bin/env python3
"""Build the lossless, queryable IndexLoom indexer release from pinned source definitions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from import_upstreams import Yaml12Loader

SCHEMA_ID = "indexloom.io/v1alpha1"
DISTRIBUTION_FORMAT = "indexloom-indexers/v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def connect_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = DELETE")
    connection.execute("PRAGMA page_size = 4096")
    connection.executescript(
        """
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE sources (
            project TEXT PRIMARY KEY, repository TEXT NOT NULL, revision TEXT NOT NULL,
            discovered INTEGER NOT NULL, selected INTEGER NOT NULL, license TEXT NOT NULL
        );
        CREATE TABLE definitions (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
            language TEXT NOT NULL, protocol TEXT NOT NULL, privacy TEXT NOT NULL,
            engine TEXT NOT NULL, source_project TEXT NOT NULL REFERENCES sources(project),
            source_id TEXT NOT NULL, source_repository TEXT NOT NULL,
            source_revision TEXT NOT NULL, source_path TEXT NOT NULL,
            source_license TEXT NOT NULL, source_file_sha256 TEXT NOT NULL,
            source_content_sha256 TEXT NOT NULL, definition_sha256 TEXT NOT NULL,
            definition_json TEXT NOT NULL, definition_yaml TEXT NOT NULL
        );
        CREATE TABLE base_urls (
            definition_id TEXT NOT NULL REFERENCES definitions(id), kind TEXT NOT NULL,
            position INTEGER NOT NULL, url TEXT NOT NULL,
            PRIMARY KEY (definition_id, kind, position)
        );
        CREATE TABLE category_mappings (
            definition_id TEXT NOT NULL REFERENCES definitions(id), position INTEGER NOT NULL,
            source_id TEXT, category TEXT, description TEXT, data_json TEXT NOT NULL,
            PRIMARY KEY (definition_id, position)
        );
        CREATE TABLE search_modes (
            definition_id TEXT NOT NULL REFERENCES definitions(id), mode TEXT NOT NULL,
            parameters_json TEXT NOT NULL, PRIMARY KEY (definition_id, mode)
        );
        CREATE TABLE configuration_fields (
            definition_id TEXT NOT NULL REFERENCES definitions(id), position INTEGER NOT NULL,
            name TEXT, kind TEXT, label TEXT, data_json TEXT NOT NULL,
            PRIMARY KEY (definition_id, position)
        );
        CREATE TABLE capabilities (
            definition_id TEXT NOT NULL REFERENCES definitions(id), name TEXT NOT NULL,
            data_json TEXT NOT NULL, PRIMARY KEY (definition_id, name)
        );
        CREATE TABLE aliases (
            source_id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL REFERENCES definitions(id),
            reason TEXT NOT NULL
        );
        CREATE INDEX definitions_language_idx ON definitions(language);
        CREATE INDEX definitions_privacy_idx ON definitions(privacy);
        CREATE INDEX definitions_source_idx ON definitions(source_project);
        CREATE INDEX category_mappings_category_idx ON category_mappings(category);
        CREATE INDEX category_mappings_source_id_idx ON category_mappings(source_id);
        CREATE INDEX search_modes_mode_idx ON search_modes(mode);
        """
    )
    return connection


def load_snapshot(directory: Path, catalog_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if catalog.get("definitionSchema") != SCHEMA_ID:
        raise ValueError("unsupported catalog definition schema")
    items = catalog.get("definitions")
    if not isinstance(items, list) or catalog.get("definitionCount") != len(items):
        raise ValueError("invalid definition count in catalog manifest")
    known = set()
    definitions = []
    for entry in sorted(items, key=lambda item: item["id"]):
        identifier = entry["id"]
        if not identifier or identifier in known or "/" in identifier or "\\" in identifier:
            raise ValueError(f"invalid or duplicate definition ID: {identifier!r}")
        known.add(identifier)
        if entry.get("path") != f"definitions/{identifier}.yml":
            raise ValueError(f"unexpected catalog path for {identifier}")
        path = directory / f"{identifier}.yml"
        data = path.read_bytes()
        if sha256(data) != entry["sha256"]:
            raise ValueError(f"definition checksum mismatch: {identifier}")
        definition = yaml.load(data, Loader=Yaml12Loader)
        if not isinstance(definition, dict):
            raise ValueError(f"definition must be an object: {identifier}")
        if definition.get("apiVersion") != SCHEMA_ID or definition.get("kind") != "Indexer":
            raise ValueError(f"unsupported definition: {identifier}")
        if definition.get("metadata", {}).get("id") != identifier:
            raise ValueError(f"definition ID mismatch: {identifier}")
        provenance = definition.get("provenance", {}).get("source", {})
        if provenance.get("project") != entry.get("sourceProject"):
            raise ValueError(f"definition source mismatch: {identifier}")
        if provenance.get("path") != entry.get("sourcePath"):
            raise ValueError(f"definition source path mismatch: {identifier}")
        definitions.append({"id": identifier, "definition": definition,
                            "definitionYaml": data.decode("utf-8"),
                            "definitionSha256": entry["sha256"]})
    actual = {path.name for path in directory.glob("*.yml") if path.is_file()}
    expected = {f"{identifier}.yml" for identifier in known}
    if actual != expected:
        raise ValueError(f"catalog files differ from manifest: {len(actual)} vs {len(expected)}")
    return catalog, definitions


def build_database(db_path: Path, manifest: dict[str, Any], records: list[dict[str, Any]],
                   builder_revision: str) -> dict[str, int]:
    db = connect_database(db_path)
    counts: Counter[str] = Counter()
    try:
        db.executemany("INSERT INTO metadata VALUES (?, ?)", [
            ("distribution_format", DISTRIBUTION_FORMAT),
            ("schema_version", SCHEMA_ID),
            ("builder_revision", builder_revision),
            ("definition_count", str(len(records))),
        ])
        for source in manifest["sources"]:
            db.execute(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?)",
                (source["project"], source["repository"], source["revision"],
                 source["discovered"], source["selected"], source["license"]),
            )
        for record in records:
            data = record["definition"]
            identifier = record["id"]
            metadata = data["metadata"]
            spec = data["spec"]
            impl = spec["implementation"]
            provenance = data["provenance"]["source"]
            db.execute(
                "INSERT INTO definitions VALUES (" + ",".join(["?"] * 18) + ")",
                (identifier, metadata["name"], metadata.get("description", ""),
                 metadata["language"], spec["protocol"], spec["privacy"], impl["engine"],
                 provenance["project"], provenance["sourceId"], provenance["repository"],
                 provenance["revision"], provenance["path"], provenance["license"],
                 provenance["fileSha256"], provenance["contentSha256"],
                 record["definitionSha256"], canonical_json(data), record["definitionYaml"]),
            )
            for kind, urls in (("primary", spec["baseUrls"]), ("legacy", spec.get("legacyUrls", []))):
                for position, url in enumerate(urls):
                    db.execute("INSERT INTO base_urls VALUES (?, ?, ?, ?)",
                               (identifier, kind, position, url))
            capabilities = impl.get("capabilities", {})
            for name, value in sorted(capabilities.items()):
                db.execute("INSERT INTO capabilities VALUES (?, ?, ?)",
                           (identifier, str(name), canonical_json(value)))
            mappings = capabilities.get("categorymappings", [])
            if isinstance(mappings, list):
                for position, value in enumerate(mappings):
                    if not isinstance(value, dict):
                        continue
                    db.execute("INSERT INTO category_mappings VALUES (?, ?, ?, ?, ?, ?)",
                               (identifier, position,
                                str(value["id"]) if value.get("id") is not None else None,
                                str(value["cat"]) if value.get("cat") is not None else None,
                                str(value["desc"]) if value.get("desc") is not None else None,
                                canonical_json(value)))
                    counts["category_mappings"] += 1
            modes = capabilities.get("modes", {})
            if isinstance(modes, dict):
                for name, parameters in sorted(modes.items()):
                    db.execute("INSERT INTO search_modes VALUES (?, ?, ?)",
                               (identifier, str(name), canonical_json(parameters)))
                    counts["search_modes"] += 1
            for position, field in enumerate(impl.get("settings", [])):
                if not isinstance(field, dict):
                    continue
                db.execute("INSERT INTO configuration_fields VALUES (?, ?, ?, ?, ?, ?)",
                           (identifier, position, field.get("name"), field.get("type"),
                            field.get("label"), canonical_json(field)))
                counts["configuration_fields"] += 1
            counts[f"source:{provenance['project']}"] += 1
            counts[f"privacy:{spec['privacy']}"] += 1
        for alias in manifest.get("deduplication", {}).get("aliases", []):
            db.execute("INSERT INTO aliases VALUES (?, ?, ?)",
                       (alias["sourceId"], alias["canonicalId"], alias["reason"]))
        counts["definitions"] = len(records)
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("SQLite foreign key check failed")
        db.execute("VACUUM")
    finally:
        db.close()
    return dict(sorted(counts.items()))


def compress(source: Path) -> Path:
    if not shutil.which("zstd"):
        raise RuntimeError("zstd executable is required for release builds")
    target = source.with_name(source.name + ".zst")
    subprocess.run(["zstd", "-q", "-f", "-19", "-T1", "-o", str(target), str(source)],
                   check=True)
    return target


def build(catalog_dir: Path, catalog: Path, output: Path, revision: str) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    input_catalog, records = load_snapshot(catalog_dir, catalog)
    db_path = output / "indexers.db"
    counts = build_database(db_path, input_catalog, records, revision)
    jsonl = output / "indexers.jsonl"
    with jsonl.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(canonical_json(record) + "\n")
    tsv = output / "indexers.tsv"
    with tsv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, dialect="excel-tab", lineterminator="\n")
        writer.writerow(("id", "name", "language", "privacy", "source", "category_count",
                         "configuration_count", "definition_json"))
        for record in records:
            data = record["definition"]
            impl = data["spec"]["implementation"]
            caps = impl.get("capabilities", {})
            writer.writerow((
                record["id"], data["metadata"]["name"], data["metadata"]["language"],
                data["spec"]["privacy"], data["provenance"]["source"]["project"],
                len(caps.get("categorymappings", [])), len(impl.get("settings", [])),
                canonical_json(data),
            ))
    compressed = [compress(db_path), compress(jsonl), compress(tsv)]
    # Only the compressed text exports are distributed; SQLite is available in both variants.
    jsonl.unlink()
    tsv.unlink()
    source_revisions = {item["project"]: item["revision"] for item in input_catalog["sources"]}
    assets = [db_path, *compressed]
    asset_info = {
        path.name: {"sha256": sha256(path.read_bytes()), "bytes": path.stat().st_size}
        for path in sorted(assets)
    }
    release_manifest = {
        "format": DISTRIBUTION_FORMAT,
        "schemaVersion": SCHEMA_ID,
        "builderRevision": revision,
        "sourceRevisions": source_revisions,
        "definitionCount": len(records),
        "statistics": counts,
        "assets": asset_info,
    }
    (output / "manifest.json").write_text(
        json.dumps(release_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sums = [(sha256(path.read_bytes()), path.name) for path in sorted(output.iterdir()) if path.is_file()]
    (output / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for digest, name in sums), encoding="utf-8"
    )
    return release_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definitions", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--builder-revision", required=True)
    args = parser.parse_args()
    manifest = build(args.definitions, args.catalog, args.output, args.builder_revision)
    print(json.dumps({"definitionCount": manifest["definitionCount"],
                      "statistics": manifest["statistics"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
