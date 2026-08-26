# IndexLoom Indexers

[![Catalog CI](https://github.com/IndexLoom/Indexers/actions/workflows/ci.yml/badge.svg)](https://github.com/IndexLoom/Indexers/actions/workflows/ci.yml)
[![Schema: v1alpha1](https://img.shields.io/badge/schema-indexloom.io%2Fv1alpha1-orange.svg)](schema/v1alpha1/indexer.schema.json)

IndexLoom Indexers is the reproducible, provenance-aware YAML catalog for
[`IndexLoom`](https://github.com/IndexLoom/IndexLoom). It converts compatible
upstream definitions at pinned revisions, removes duplicate sites, preserves
license metadata and verifies every generated artifact before publication.

> [!IMPORTANT]
> The format is pre-stable and currently identified as
> `indexloom.io/v1alpha1`. Files under `definitions/` are generated and must not
> be edited by hand.

## Catalog guarantees

- Exact 40-character source commit IDs; a rebuild never silently follows a
  moving upstream branch.
- Deterministic conversion of compatible Jackett and Prowlarr Indexers
  Cardigann YAML.
- Deduplication by site identity while retaining definitions unique to either
  source.
- Source repository, revision, path, original ID, license and source-file
  SHA-256 in every generated definition.
- Semantic-content SHA-256 that detects importer drift independently from YAML
  formatting.
- Manifest coverage, schema validation, unique IDs and filenames, provenance
  validation and generated-file marker enforcement in CI.

For matching IDs, the Jackett definition is currently canonical. Definitions
for the same site under different IDs are collapsed using the converter's
recorded deduplication rules; `catalog.json` contains the complete report.

## Layout

```text
definitions/              Generated, deduplicated definitions
examples/                 Hand-authored non-production format examples
schema/v1alpha1/          JSON Schema mirrored from the application contract
tools/import_upstreams.py Deterministic upstream converter
tools/validate.py         Schema, provenance, hash and manifest validator
catalog.json              Source revisions and deduplication report
LICENSES/                 Licenses retained by generated content
```

## Validate locally

Install [`uv`](https://docs.astral.sh/uv/) and run:

```bash
uv sync --frozen
uv run python tools/validate.py
```

The validator reconstructs supported Cardigann content and compares its
semantic digest, so a generated file cannot be changed without also exposing
the provenance mismatch.

To validate the same checkout using IndexLoom's executable Rust contract:

```bash
cargo run -p indexloom-definitions --example validate_catalog -- \
  /path/to/Indexers/definitions
```

## Rebuild from pinned upstreams

```bash
uv run python tools/import_upstreams.py \
  --jackett-root /path/to/Jackett \
  --jackett-revision "$(git -C /path/to/Jackett rev-parse HEAD)" \
  --prowlarr-root /path/to/Prowlarr-Indexers \
  --prowlarr-revision "$(git -C /path/to/Prowlarr-Indexers rev-parse HEAD)"
```

The converter rejects abbreviated revisions and refuses to overwrite a file
without its generated marker. Review `catalog.json`, the validator output and
the source revisions before committing a refresh.

## Contributing

Changes to generated definitions belong in the converter or upstream source,
not as one-off YAML patches. Schema and importer changes should be paired with
fixtures, deterministic rebuild evidence and an explanation of compatibility
impact. Community-native definitions are planned, but they need a separate
authorship and provenance path before they can coexist safely with generated
content.

## License and provenance

Repository-authored documentation, schemas, examples and tooling are licensed
under `AGPL-3.0-or-later` as described by [LICENSE](LICENSE). Generated files
under `definitions/` retain `GPL-2.0-only` and carry SPDX and provenance
metadata; see [THIRD_PARTY.md](THIRD_PARTY.md) and
[LICENSES/GPL-2.0-only.txt](LICENSES/GPL-2.0-only.txt).
