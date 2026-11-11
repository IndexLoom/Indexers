from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_database import build  # noqa: E402


class DatabaseReleaseTests(unittest.TestCase):
    def test_lossless_definition_and_indexed_fields(self) -> None:
        source = (ROOT / "examples/example.yml").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            defs = root / "definitions"
            defs.mkdir()
            (defs / "example.yml").write_bytes(source)
            manifest = {
                "definitionSchema": "indexloom.io/v1alpha1",
                "definitionCount": 1,
                "sources": [{
                    "project": "jackett", "repository": "https://github.com/Jackett/Jackett",
                    "revision": "0" * 40, "discovered": 1, "selected": 1,
                    "license": "GPL-2.0-only"
                }],
                "deduplication": {"aliases": []},
                "definitions": [{
                    "id": "example", "path": "definitions/example.yml",
                    "sha256": hashlib.sha256(source).hexdigest(),
                    "sourceProject": "jackett",
                    "sourcePath": "src/Jackett.Common/Definitions/example.yml",
                }],
            }
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(manifest), encoding="utf-8")
            release = build(defs, catalog_path, root / "dist", "a" * 40)
            self.assertEqual(release["definitionCount"], 1)
            db = sqlite3.connect(root / "dist/indexers.db")
            try:
                row = db.execute("SELECT definition_yaml, definition_json FROM definitions WHERE id='example'").fetchone()
                self.assertEqual(row[0].encode("utf-8"), source)
                self.assertEqual(json.loads(row[1])["metadata"]["id"], "example")
                self.assertEqual(db.execute("SELECT count(*) FROM search_modes").fetchone()[0], 1)
            finally:
                db.close()
            self.assertEqual(set(release["assets"]), {
                "indexers.db", "indexers.db.zst", "indexers.jsonl.gz", "indexers.jsonl.zst", "indexers.tsv.zst"
            })
            for name, asset in release["assets"].items():
                self.assertEqual(hashlib.sha256((root / "dist" / name).read_bytes()).hexdigest(),
                                 asset["sha256"])

    def test_retains_both_upstream_variants_when_definitions_differ(self) -> None:
        source = (ROOT / "examples/example.yml").read_bytes()
        upstream = (
            "id: example\n"
            "name: Example\n"
            "description: Variant source\n"
            "language: en\n"
            "type: public\n"
            "encoding: UTF-8\n"
            "links: [https://example.invalid/]\n"
            "caps: {modes: {search: [q]}}\n"
            "search: {paths: [{path: /search}], rows: {selector: .result}, fields: {}}\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            definitions = root / "catalog" / "definitions"
            definitions.mkdir(parents=True)
            (definitions / "example.yml").write_bytes(source)
            jackett = root / "jackett"
            prowlarr = root / "prowlarr"
            jpath = jackett / "src/Jackett.Common/Definitions/example.yml"
            ppath = prowlarr / "definitions/example.yml"
            jpath.parent.mkdir(parents=True)
            ppath.parent.mkdir(parents=True)
            jpath.write_text(upstream, encoding="utf-8")
            ppath.write_text(upstream.replace("Variant source", "Different variant"),
                             encoding="utf-8")
            manifest = {
                "definitionSchema": "indexloom.io/v1alpha1",
                "definitionCount": 1,
                "sources": [
                    {
                        "project": "jackett", "repository": "https://github.com/Jackett/Jackett",
                        "revision": "0" * 40, "discovered": 1, "selected": 1,
                        "license": "GPL-2.0-only"
                    },
                    {
                        "project": "prowlarr-indexers",
                        "repository": "https://github.com/Prowlarr/Indexers",
                        "revision": "1" * 40, "discovered": 1, "selected": 0,
                        "license": "GPL-2.0-only"
                    },
                ],
                "deduplication": {"aliases": []},
                "definitions": [{
                    "id": "example", "path": "definitions/example.yml",
                    "sha256": hashlib.sha256(source).hexdigest(),
                    "sourceProject": "jackett",
                    "sourcePath": "src/Jackett.Common/Definitions/example.yml",
                }],
            }
            catalog = root / "catalog" / "catalog.json"
            catalog.write_text(json.dumps(manifest), encoding="utf-8")
            release = build(definitions, catalog, root / "dist", "a" * 40, {
                "jackett": jackett, "prowlarr-indexers": prowlarr
            })
            self.assertEqual(release["statistics"]["upstream_variants"], 2)
            self.assertEqual(release["statistics"]["selected_variants"], 1)
            db = sqlite3.connect(root / "dist/indexers.db")
            try:
                rows = db.execute(
                    "SELECT project, canonical_id, selected, document_yaml "
                    "FROM upstream_variants ORDER BY project"
                ).fetchall()
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0][0:3], ("jackett", "example", 1))
                self.assertEqual(rows[1][0:3], ("prowlarr-indexers", "example", 0))
                self.assertIn("Variant source", rows[0][3])
                self.assertIn("Different variant", rows[1][3])
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM definitions").fetchone()[0], 1
                )
            finally:
                db.close()

    def test_fails_closed_when_catalog_has_wrong_digest(self) -> None:
        source = (ROOT / "examples/example.yml").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            defs = root / "definitions"
            defs.mkdir()
            (defs / "example.yml").write_bytes(source)
            catalog = {"definitionSchema": "indexloom.io/v1alpha1", "definitionCount": 1,
                       "definitions": [{"id": "example", "path": "definitions/example.yml",
                                        "sha256": "0" * 64}]}
            manifest = root / "catalog.json"
            manifest.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaises(ValueError):
                build(defs, manifest, root / "dist", "a" * 40)


if __name__ == "__main__":
    unittest.main()
