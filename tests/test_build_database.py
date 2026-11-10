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
