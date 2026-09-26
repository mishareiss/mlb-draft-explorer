# college-draft-explorer

A dashboard for asking how MLB draftees' careers turn out, depending on where and how they were
drafted. It covers draft classes 2012-2025 and looks at whether players reached MLB, how long it
took, and career WAR, broken down by school, conference, school type, position, age at draft, draft
slot and signing bonus. Data comes from the MLB Stats API (draft results, player bios) and
Baseball-Reference WAR (via `pybaseball`).

Status: ingestion and data profiling. See [docs/DATA_PROFILE.md](docs/DATA_PROFILE.md) for
what the raw data contains and how complete it is.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 if needed).

```sh
make setup                # install dependencies
make pull && make profile # download + cache raw data, write docs/DATA_PROFILE.md
make test lint            # offline tests, ruff
```

Raw responses are cached under `data/raw/` and flattened tables are written to `data/interim/`
(both git-ignored). A second `make pull` reads from the cache and makes no network calls. Pass
`--force` to a pull script to re-download.
