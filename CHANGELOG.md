# Changelog

All notable catalog and schema changes will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and schema/tooling releases follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Database-first distribution

- Migrated generated definitions out of Git; releases now provide SQLite,
  compressed SQLite, JSONL, TSV and a gzip transport export.
- Added deterministic daily upstream imports, revision checks, per-release
  manifests and SHA256SUMS.
- Indexed complete Cardigann settings, capabilities, modes, categories, URLs
  and provenance while retaining the full original YAML in the database.


### Added

- Deterministic Jackett and Prowlarr Cardigann converter.
- Deduplicated catalog manifest with pinned revisions and per-file hashes.
- Lossless `indexloom.io/v1alpha1` Cardigann implementation envelope.
- Provenance and reconstructed semantic-content validation.

### Changed

- Definition contributions now use a generated-catalog workflow.
- Imported definition files retain their `GPL-2.0-only` source license.
