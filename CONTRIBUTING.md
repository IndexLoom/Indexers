# Contributing

Thank you for improving IndexLoom's definition catalog.

## Definition requirements

1. Start with the current schema in `schema/v1alpha1/indexer.schema.json`.
2. Use a lowercase kebab-case ID and save the file as `<id>.yml`.
3. Prefer HTTPS base URLs and do not embed credentials, cookies, tokens, or
   user-specific endpoints.
4. Include only selectors and request behavior you personally verified.
5. Run `uv run python tools/validate.py` before opening a pull request.

## Provenance

Do not copy or mechanically translate third-party definitions unless their
license is compatible, attribution is preserved, and maintainers explicitly
approve the import. A site being supported by another project is useful
research context, but its implementation is not automatically reusable here.

By submitting a contribution, you certify that you have the right to license it
under `AGPL-3.0-or-later`.
