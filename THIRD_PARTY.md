# Third-party notices

## Jackett Cardigann definitions

- Repository: <https://github.com/Jackett/Jackett>
- License: `GPL-2.0-only`
- Source revision: recorded in `catalog.json`
- Generated outputs: entries whose `provenance.source.project` is `jackett`

## Prowlarr Indexers Cardigann definitions

- Repository: <https://github.com/Prowlarr/Indexers>
- Source revision: recorded in `catalog.json`
- Generated outputs: entries whose `provenance.source.project` is
  `prowlarr-indexers`

Prowlarr Indexers documents that its Cardigann definitions are automatically
synced from Jackett, with differences and a small number of exceptions. The
only currently selected Prowlarr-only definition, `brasiltracker`, originated
in Jackett and its Prowlarr Git history preserves that provenance through the
repository split and later modifications. Generated definition files retain
`GPL-2.0-only`; their exact source path, revision, byte hash, and semantic hash
are recorded in each file and in the catalog manifest.

IndexLoom does not claim authorship of imported definition behavior. The
conversion adds a versioned envelope and provenance without removing notices
or changing the license governing the source-derived content.
