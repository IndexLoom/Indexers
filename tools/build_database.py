#!/usr/bin/env python3
"""Build the lossless, queryable IndexLoom indexer release from pinned source definitions."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from import_upstreams import (
    JACKETT_PROJECT, JACKETT_REPOSITORY, PROWLARR_PROJECT, PROWLARR_REPOSITORY,
    Yaml12Loader, discover,
)

SCHEMA_ID = "indexloom.io/v1alpha1"
DISTRIBUTION_FORMAT = "indexloom-indexers/v1"


def json_compatible(value: Any) -> Any:
    # Cardigann permits integer and string YAML mapping keys in the same map.
    # JSON requires text keys; the original lossless YAML is retained separately.
    if isinstance(value, dict):
        return {str(key): json_compatible(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_compatible(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(json_compatible(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


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
        -- Indexable native categories without losing the original source mapping.
        CREATE TABLE definition_categories (
            definition_id TEXT NOT NULL REFERENCES definitions(id),
            category TEXT NOT NULL, origin TEXT NOT NULL
                CHECK (origin IN ('categorymappings', 'categories')),
            PRIMARY KEY (definition_id, category, origin)
        );
        CREATE TABLE search_mode_parameters (
            definition_id TEXT NOT NULL REFERENCES definitions(id),
            mode TEXT NOT NULL, position INTEGER NOT NULL, parameter TEXT NOT NULL,
            PRIMARY KEY (definition_id, mode, position),
            FOREIGN KEY (definition_id, mode) REFERENCES search_modes(definition_id, mode)
        );
        -- Statically inferred features. These record declarations, not tested support.
        CREATE TABLE definition_features (
            definition_id TEXT PRIMARY KEY REFERENCES definitions(id),
            has_authentication INTEGER NOT NULL CHECK (has_authentication IN (0, 1)),
            has_captcha INTEGER NOT NULL CHECK (has_captcha IN (0, 1)),
            has_download_handler INTEGER NOT NULL CHECK (has_download_handler IN (0, 1)),
            supports_genre INTEGER NOT NULL CHECK (supports_genre IN (0, 1)),
            allows_raw_search INTEGER NOT NULL CHECK (allows_raw_search IN (0, 1)),
            search_path_count INTEGER NOT NULL,
            alternate_url_count INTEGER NOT NULL
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
        -- Every upstream variant is retained, including the differences
        -- discarded by canonical Jackett-first deduplication.
        CREATE TABLE upstream_variants (
            project TEXT NOT NULL REFERENCES sources(project),
            path TEXT NOT NULL, canonical_id TEXT REFERENCES definitions(id),
            source_id TEXT NOT NULL, revision TEXT NOT NULL,
            source_sha256 TEXT NOT NULL, selected INTEGER NOT NULL,
            document_json TEXT NOT NULL, document_yaml TEXT NOT NULL,
            PRIMARY KEY (project, path)
        );
        CREATE INDEX upstream_variants_canonical_idx ON upstream_variants(canonical_id);
        CREATE INDEX definitions_language_idx ON definitions(language);
        CREATE INDEX definitions_privacy_idx ON definitions(privacy);
        CREATE INDEX definitions_source_idx ON definitions(source_project);
        CREATE INDEX category_mappings_category_idx ON category_mappings(category);
        CREATE INDEX category_mappings_source_id_idx ON category_mappings(source_id);
        CREATE INDEX search_modes_mode_idx ON search_modes(mode);
        CREATE INDEX definition_categories_category_idx ON definition_categories(category);
        CREATE INDEX search_mode_parameters_parameter_idx ON search_mode_parameters(parameter);
        CREATE INDEX definition_features_genre_idx ON definition_features(supports_genre);
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
                   builder_revision: str, upstream_roots: dict[str, Path] | None = None) -> dict[str, int]:
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
            native_categories: set[tuple[str, str]] = set()
            if isinstance(mappings, list):
                for value in mappings:
                    if isinstance(value, dict) and value.get("cat") is not None:
                        native_categories.add((str(value["cat"]), "categorymappings"))
            declared_categories = capabilities.get("categories", {})
            if isinstance(declared_categories, dict):
                native_categories.update((str(key), "categories") for key in declared_categories)
            for category, origin in sorted(native_categories):
                db.execute("INSERT INTO definition_categories VALUES (?, ?, ?)",
                           (identifier, category, origin))
                counts["definition_categories"] += 1
            modes = capabilities.get("modes", {})
            supports_genre = False
            if isinstance(modes, dict):
                for name, parameters in sorted(modes.items()):
                    db.execute("INSERT INTO search_modes VALUES (?, ?, ?)",
                               (identifier, str(name), canonical_json(parameters)))
                    counts["search_modes"] += 1
                    if isinstance(parameters, list):
                        for position, parameter in enumerate(parameters):
                            parameter = str(parameter)
                            db.execute(
                                "INSERT INTO search_mode_parameters VALUES (?, ?, ?, ?)",
                                (identifier, str(name), position, parameter),
                            )
                            counts["search_mode_parameters"] += 1
                            supports_genre |= parameter == "genre"
            authentication = impl.get("authentication")
            search = impl.get("search", {})
            paths = search.get("paths", []) if isinstance(search, dict) else []
            db.execute(
                "INSERT INTO definition_features VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier, int(authentication is not None),
                    int(isinstance(authentication, dict) and "captcha" in authentication),
                    int(impl.get("download") is not None),
                    int(supports_genre), int(capabilities.get("allowrawsearch") is True),
                    len(paths) if isinstance(paths, list) else 0,
                    max(0, len(spec["baseUrls"]) - 1) + len(spec.get("legacyUrls", [])),
                ),
            )
            counts["definition_features"] += 1
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
        if upstream_roots:
            canonical_ids = {record["id"] for record in records}
            selected_sources = {
                (record["definition"]["provenance"]["source"]["project"],
                 record["definition"]["provenance"]["source"]["path"])
                for record in records
            }
            aliases = {
                item["sourceId"]: item["canonicalId"]
                for item in manifest.get("deduplication", {}).get("aliases", [])
            }
            for source in manifest["sources"]:
                project = source["project"]
                root = upstream_roots[project]
                definition_root = (root / "src/Jackett.Common/Definitions"
                                   if project == JACKETT_PROJECT else root / "definitions")
                candidates = discover(
                    project=project,
                    repository=source["repository"],
                    revision=source["revision"],
                    repository_root=root,
                    definition_root=definition_root,
                    recursive=project == PROWLARR_PROJECT,
                )
                if len(candidates) != source["discovered"]:
                    raise ValueError(f"source revision changed during build: {project}")
                for candidate in candidates:
                    canonical_id = candidate.canonical_id
                    if canonical_id not in canonical_ids:
                        canonical_id = aliases.get(candidate.source_id)
                    # Not all source definitions must map to an active canonical
                    # one; nullable identity preserves otherwise orphaned evidence.
                    if canonical_id not in canonical_ids:
                        canonical_id = None
                    selected = int((project, candidate.relative_path) in selected_sources)
                    db.execute(
                        "INSERT INTO upstream_variants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (project, candidate.relative_path, canonical_id, candidate.source_id,
                         source["revision"], sha256(candidate.source_bytes), selected,
                         canonical_json(candidate.document),
                         candidate.source_bytes.decode("utf-8-sig")),
                    )
                    counts["upstream_variants"] += 1
                    counts["selected_variants"] += selected
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


def build(catalog_dir: Path, catalog: Path, output: Path, revision: str,
          upstream_roots: dict[str, Path] | None = None) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    input_catalog, records = load_snapshot(catalog_dir, catalog)
    db_path = output / "indexers.db"
    counts = build_database(db_path, input_catalog, records, revision, upstream_roots)
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
    # Gzip is a transport-only stream for IndexLoom's Rust runtime: the same
    # canonical records are also available as zstd and full SQLite assets.
    gzip_path = output / "indexers.jsonl.gz"
    with jsonl.open("rb") as original, gzip_path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0, compresslevel=9) as packed:
            shutil.copyfileobj(original, packed)
    jsonl.unlink()
    tsv.unlink()
    source_revisions = {item["project"]: item["revision"] for item in input_catalog["sources"]}
    assets = [db_path, gzip_path, *compressed]
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
    parser.add_argument("--jackett-root", type=Path)
    parser.add_argument("--prowlarr-root", type=Path)
    args = parser.parse_args()
    if bool(args.jackett_root) != bool(args.prowlarr_root):
        parser.error("both upstream roots must be supplied together")
    upstreams = ({JACKETT_PROJECT: args.jackett_root, PROWLARR_PROJECT: args.prowlarr_root}
                 if args.jackett_root else None)
    manifest = build(args.definitions, args.catalog, args.output, args.builder_revision, upstreams)
    print(json.dumps({"definitionCount": manifest["definitionCount"],
                      "statistics": manifest["statistics"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
