# IndexLoom Indexers

Community-maintained indexer definitions for
[`IndexLoom`](https://github.com/IndexLoom/IndexLoom).

> [!IMPORTANT]
> The definition format is pre-stable and currently identified as
> `indexloom.io/v1alpha1`.

## Repository boundary

This repository contains definitions written for IndexLoom. It is not a mirror
of Jackett, Prowlarr, Cardigann, or any other definition repository. Automated
bulk conversion and copying are intentionally excluded from the contribution
workflow. Runtime importers belong to the main IndexLoom application and act
only when a user explicitly imports a supported external format.

## Layout

```text
definitions/           Reviewed community definitions
examples/              Non-production format examples
schema/v1alpha1/        Current JSON Schema mirror
tools/                  Validation tooling
```

## Validate locally

Install [`uv`](https://docs.astral.sh/uv/) and run:

```bash
uv sync --frozen
uv run python tools/validate.py
```

Every pull request runs the same validation. A definition filename must match
its `metadata.id`, and IDs must be unique across the repository.

## License

Repository-authored content and tooling are licensed under the GNU Affero
General Public License v3.0 or later. Contributors must submit only content they
have the right to license under those terms.
