# IndexLoom Indexers

Deterministic, deduplicated indexer catalog for
[`IndexLoom`](https://github.com/IndexLoom/IndexLoom).

> [!IMPORTANT]
> The definition format is pre-stable and currently identified as
> `indexloom.io/v1alpha1`.

## Catalog

The generated catalog currently combines the Cardigann YAML definitions from
Jackett and Prowlarr Indexers. For matching IDs, the Jackett definition is the
canonical source. Definitions for the same site under different IDs are
collapsed, while definitions unique to either catalog are retained.

Every generated file records its exact upstream repository, commit, path,
original ID, source-file SHA-256, and semantic-content SHA-256. `catalog.json`
records the source revisions and the full deduplication report. The importer is
lossless for supported Cardigann fields: the validator reconstructs the source
document and verifies its semantic digest.

## Layout

```text
definitions/              Generated, deduplicated IndexLoom definitions
examples/                 Non-production format examples
schema/v1alpha1/          Current JSON Schema mirror
tools/import_upstreams.py Reproducible upstream converter
tools/validate.py         Schema, provenance, and manifest validator
catalog.json              Revisions, hashes, and deduplication report
LICENSES/                 Licenses for imported/generated content
```

## Validate locally

Install [`uv`](https://docs.astral.sh/uv/) and run:

```bash
uv sync --frozen
uv run python tools/validate.py
```

Validation checks the schema, unique IDs and filenames, generated-file marker,
manifest coverage, source provenance, file hashes, and reconstructed semantic
hashes.

## Rebuild the catalog

Use full 40-character commit IDs so a build cannot silently follow a moving
branch:

```bash
uv run python tools/import_upstreams.py \
  --jackett-root /path/to/Jackett \
  --jackett-revision "$(git -C /path/to/Jackett rev-parse HEAD)" \
  --prowlarr-root /path/to/Prowlarr-Indexers \
  --prowlarr-revision "$(git -C /path/to/Prowlarr-Indexers rev-parse HEAD)"
```

The converter refuses to overwrite files that do not carry its generated-file
marker.

## License

Repository-authored documentation, schemas, examples, and tooling are licensed
under `AGPL-3.0-or-later` as described by the root `LICENSE`. Generated files in
`definitions/` retain `GPL-2.0-only` and carry SPDX headers; see
`LICENSES/GPL-2.0-only.txt` and `THIRD_PARTY.md`.
