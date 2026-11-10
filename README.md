# IndexLoom Indexers

[![Catalog CI](https://github.com/IndexLoom/Indexers/actions/workflows/validate.yml/badge.svg)](https://github.com/IndexLoom/Indexers/actions/workflows/validate.yml)
[![Database releases](https://img.shields.io/badge/catalog-SQLite-blue)](https://github.com/IndexLoom/Indexers/releases)
[![Schema: v1alpha1](https://img.shields.io/badge/schema-indexloom.io%2Fv1alpha1-orange.svg)](schema/v1alpha1/indexer.schema.json)

IndexLoom Indexers is the **separately released, versioned database** of
torrent indexer definitions for [IndexLoom](https://github.com/IndexLoom/IndexLoom).
It imports Jackett and Prowlarr/Indexers Cardigann definitions from pinned
Git revisions without requiring either application at runtime.

## Download

[Download the latest database release](https://github.com/IndexLoom/Indexers/releases/latest).
Release assets are published **outside the source repository**, using the
approach adopted in the anime mapping/timestamp database projects.

| File | Description |
| --- | --- |
| `indexers.db` | Complete queryable SQLite distribution |
| `indexers.db.zst` | Compressed SQLite distribution |
| `indexers.jsonl.zst` | Lossless definition export, one record per line |
| `indexers.tsv.zst` | Tab-separated export containing complete definition JSON |
| `indexers.jsonl.gz` | Gzip transport for automatic IndexLoom runtime updates |
| `manifest.json` | Schema version, exact upstream commits, statistics, asset sizes and SHA-256 |
| `SHA256SUMS` | Independent integrity checks for all release assets |

No generated YAML catalog is committed to this Git repository. The importer
creates temporary YAML intermediates **only during the release build**.
Every database record retains the original converted YAML definition,
its semantic JSON view, complete Cardigann settings, capabilities, authentication,
search paths, filters and source hashes. Dedicated tables index origins,
categories, search modes, configured fields, URLs and source aliases.

The index tables intentionally do not fabricate "genres" or "tags" if the
upstream does not provide them. All native fields are preserved and indexed
when they can be identified safely.

## Update lifecycle

- Each day, the scheduled GitHub Actions workflow checks fresh Jackett and
  Prowlarr/Indexers source revisions.
- Any upstream revision change or catalog builder change triggers a new release.
- Runs against unchanged upstreams are skipped unless a manual force release
  is requested. Manually trigger via Actions > Build and release Indexers database.
- The import is deterministic for specified revisions, validates the matching
  `indexloom.io/v1alpha1` schema, manifest/provenance and source hashes,
  then runs SQLite integrity checks and verifies every published file digest.
- IndexLoom polls the latest release manifest and downloads a new verified
  export only when its manifest digest changes. Existing credentials and
  indexer settings are preserved.

A build is still only a **definition validation**, not proof that every
tracker remains reachable or fully executable by the evolving Cardigann engine.

## Database schema

The current distribution format is `indexloom-indexers/v1`.
The following tables are available:

- `definitions` — one record per canonical indexer with complete
  `definition_json` and lossless `definition_yaml`, provenance, language,
  privacy, protocol and hashes.
- `sources` — upstream repositories, revisions, discovered and selected counts.
- `base_urls` — primary and legacy URLs in original priority order.
- `category_mappings` — source category IDs, categories, descriptions and
  complete per-category objects.
- `search_modes` — the full set of declared query modes and fields.
- `configuration_fields` — complete Cardigann configuration settings.
- `capabilities` — every native capability entry as JSON.
- `aliases` — recorded cross-ID deduplication aliases.
- `upstream_variants` — all original Jackett and Prowlarr definitions,
  including overlapping IDs whose upstream behavior differs. The canonical
  winner is marked with `selected = 1`.
- `metadata` — distribution and schema version.

Example:

```sql
SELECT id, name, language, privacy FROM definitions ORDER BY name;
SELECT source_id, category, description
FROM category_mappings WHERE definition_id = 'nyaasi';
SELECT definition_yaml FROM definitions WHERE id = 'nyaasi';
```

## Building from upstream sources

Use Python 3.13, [uv](https://docs.astral.sh/uv/) and `zstd`:

```bash
uv sync --frozen --python 3.13
git clone --depth=1 https://github.com/Jackett/Jackett.git /tmp/jackett
git clone --depth=1 https://github.com/Prowlarr/Indexers.git /tmp/prowlarr-indexers
uv run python tools/import_upstreams.py \
  --jackett-root /tmp/jackett \
  --jackett-revision "$(git -C /tmp/jackett rev-parse HEAD)" \
  --prowlarr-root /tmp/prowlarr-indexers \
  --prowlarr-revision "$(git -C /tmp/prowlarr-indexers rev-parse HEAD)" \
  --output /tmp/indexloom-catalog/definitions \
  --manifest /tmp/indexloom-catalog/catalog.json
INDEXLOOM_CATALOG_ROOT=/tmp/indexloom-catalog uv run python tools/validate.py
uv run python tools/build_database.py \
  --definitions /tmp/indexloom-catalog/definitions \
  --catalog /tmp/indexloom-catalog/catalog.json \
  --output /tmp/indexloom-dist --builder-revision "$(git rev-parse HEAD)"
```

The importer continues to prefer Jackett for matching canonical IDs and
collapses cross-ID site aliases. This is source deduplication, not merging
the semantic differences of definitions from both upstreams.

## License and contribution

Repository-written tooling and documentation use AGPL-3.0-or-later;
generated source-derived Cardigann content retains GPL-2.0-only, recorded
in its per-definition provenance and `THIRD_PARTY.md`.
Contribute changes to the importer, database generator or upstream source,
not to an individual generated YAML file.
