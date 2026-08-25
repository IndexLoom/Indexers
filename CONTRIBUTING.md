# Contributing

Thank you for improving IndexLoom's definition catalog.

## Generated definitions

Files in `definitions/` are reproducible outputs and must not be edited by
hand. Fix the licensed upstream definition or the converter, pin the intended
upstream commit, regenerate the complete catalog, and include the resulting
`catalog.json` update.

The importer must preserve all executable Cardigann behavior, provenance, and
the source license. New source catalogs require a documented, compatible
license and an explicit deterministic precedence/deduplication rule.

## Required checks

1. Run `uv run python tools/validate.py`.
2. Run the importer twice from the same source revisions and confirm that the
   generated tree and `catalog.json` are byte-for-byte identical.
3. Do not include credentials, cookies, tokens, or user-specific endpoints.
4. Explain any change to canonical selection, aliasing, or ID normalization.

Repository-authored changes to tooling, schemas, examples, and documentation
are submitted under `AGPL-3.0-or-later`. Generated definition files retain the
compatible source license recorded in their SPDX headers and provenance.
