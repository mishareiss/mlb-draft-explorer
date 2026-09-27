# Task 2: Backfill 2012–2016 bonuses from Baseball-Reference and build the school reference table

## Context
Task 1 (staged on `main`, about to be committed) pulled 2012–2025 draft picks, people and WAR, and
wrote `docs/DATA_PROFILE.md`. Two gaps block the dashboard:

1. The MLB Stats API has **no signing bonus for 2012–2016**. Baseball-Reference draft pages have `Signed` and `Bonus` columns for those years.
2. There's **no conference or reliable school type**: `school_school_class` is null for 66% of picks, and school names aren't normalized (`TCU` vs `Texas Christian`).

This task adds both as data sources. It does **not** build the SQL models or `draft_outcomes`; that's Task 3.

Read first: `docs/DATA_PROFILE.md` (especially "Notes for Task 2"), `ingest/http.py`,
`ingest/pull_draft.py`, `ingest/pull_people.py`, `ingest/profile.py`, `tests/test_http.py`.

Branch: `git switch -c task-02-bonus-and-schools` (from `main` once I've committed Task 1; if
`main` still has no commits, stop and tell me).

IMPORTANT: STAGE all changes (`git add -A`) but DO NOT COMMIT. I commit myself. No
`Co-Authored-By` or any AI/session trailers anywhere.

## Scope

### A. Small fixes to Task 1 code
1. **People cache key:** `pull_people.py` caches batches by position (`batch_000.json`), which goes stale if the ID set changes. Name each file by a short hash of its sorted ID list instead (e.g. `batch_<sha1[:12]>.json`). Update its test. Note in the report that I should run `pull_people --force` once, or delete the old batch files.
2. **User-Agent:** add the contact URL `https://github.com/mishareiss/college-draft-explorer`.

### B. Baseball-Reference access in `ingest/http.py` (landmine: read this)
Today's session **auto-retries HTTP 429 with backoff**. That's fine for MLB. Baseball-Reference
temporarily bans IPs that exceed its rate limit, and retrying a 429 makes it worse.
- Add `fetch_text_cached(url, path, force=False, *, min_interval_s, retry_429)`, following the `fetch_json_cached` pattern: a cache hit makes zero calls, and the raw bytes are written verbatim.
- Baseball-Reference calls use **`min_interval_s=7`** (under 10 requests/minute) and **`retry_429=False`**. On a 429, or any 403, raise a dedicated `RateLimitedError` that stops the run immediately with a clear message ("wait an hour, cached pages are kept; re-run to resume").
- Keep the MLB behavior unchanged. All network access still goes through `http.py`.

### C. `ingest/pull_bbref_draft.py`
- Years **2012–2017** by default. 2017 is included only to cross-check against the MLB API's 2017 bonuses. Rounds 1–40.
- URL: `https://www.baseball-reference.com/draft/?year_ID={year}&draft_round={round}&draft_type=junreg&query_type=year_round`. Cache the raw HTML at `data/raw/bbref_draft/{year}_r{round:02d}.html`.
- **Verify, don't assume:** check whether supplemental and competitive-balance picks appear on the numbered-round pages (the 2014 round-1 page appears to include the CB-A picks). Compare total parsed rows per year against the MLB API pick count per year, and report any mismatch.
- Parse with `pandas.read_html` (add `lxml`). If the table is inside an HTML comment, handle that. Use `extract_links="body"` to capture the player-page link where present.
- Output `data/interim/bbref_draft.parquet` with: `draft_year`, `overall_pick` (the `OvPk` column), `round_label`, `team`, `signed` (bool from Y/N), `bonus_usd` (float; `"$6,582,000"` → 6582000.0; blank → NaN), `name`, `pos`, `drafted_out_of` (raw text, e.g. `"Louisiana State University (Baton Rouge, LA)"`), `bbref_player_url`.
- Expect ~240 pages at 7 s each, about 30 minutes on the first run. Log progress (`2014 r12/40`) so a run can be interrupted and resumed from cache.

### D. `ingest/build_bonus_backfill.py` → `data/interim/bonus_backfill.parquet`
- Join Baseball-Reference to MLB picks on **`(draft_year, overall_pick)` = `(draft_year, pick_number)`**.
- Validate each join with a name check: normalize both names (lowercase, strip accents, punctuation, Jr./II/III), then `rapidfuzz.fuzz.token_sort_ratio`. Keep the score. Flag rows below 85 as `name_mismatch=True` and don't use their bonus. Add `rapidfuzz`.
- Output columns: `draft_year`, `pick_number`, `person_id`, `bbref_signed`, `bbref_bonus_usd`, `bbref_drafted_out_of`, `name_match_score`, `name_mismatch`.
- **2017 cross-check:** for 2017 picks with both values, report the % where the Baseball-Reference bonus equals the MLB bonus exactly, the % within 1%, and the 10 largest disagreements.

### E. School reference: `ingest/build_school_ref.py` + `reference/schools.csv`
One row per **non-high-school raw `school_name`** in `draft_picks.parquet`. High schools are classified by rule in Task 3 and aren't listed.

Columns: `school_name_raw`, `school_canonical`, `school_type` (`4YR`|`JC`|`OTHER`), `division` (`D1`|`D2`|`D3`|`NAIA`|`JUCO`|`UNKNOWN`), `conference_pre2024`, `conference_2024`, `state`, `type_source`, `conf_source`, `needs_review` (bool).

1. **School type and HS detection**, in priority order, recording which rule fired in `type_source`:
   1. `school_school_class` prefix for any pick with that name (`4YR`, `JC`, `HS`)
   2. Baseball-Reference `drafted_out_of` text for that pick (`High School`, `Academy`, `Community College`, `Junior College`, `University`, `College`)
   3. Name regex (`\bHS\b`, `High School`, `\bCC\b`, `\bJC\b`, `Community College`)
   4. Otherwise `UNKNOWN` with `needs_review=True`

   The profile shows bare classes like `JR`/`SR`/`SO` with no level prefix; don't use those for type.
2. **Canonical names:** group aliases such as `TCU`/`Texas Christian` and `LSU`/`Louisiana State` under one `school_canonical`. Use the Baseball-Reference full name as evidence when available. List every alias group in the report.
3. **Division and conference, for D1 only:**
   - `conference_2024`: take it from Wikipedia's list of NCAA Division I baseball programs (fetch via `http.py` and cache it). Set `conf_source="wikipedia"`.
   - `conference_pre2024` is the 2023-season alignment. Copy `conference_2024` and override only the schools that switched conferences in 2024 (e.g. the Pac-12 departures to the Big Ten, Big 12 and ACC; Texas and Oklahoma to the SEC; SMU to the ACC). Put each override in a small, commented `reference/conference_moves_2024.csv` so it's reviewable.
   - Schools not found on the Wikipedia list: `division=UNKNOWN`, conference blank, `needs_review=True`. **Do not fill conferences from memory.**
4. The CSV is generated by the script and then committed. Rows I edit by hand later must survive a re-run: the script merges into the existing CSV rather than overwriting rows that are marked `type_source="manual"`.

### F. Profile updates (`ingest/profile.py`)
Add sections: **Bonus backfill** (Baseball-Reference coverage by year × round band after backfill, join match rate, name mismatches, 2017 cross-check), and **School reference** (row counts by type and division, % of college picks mapped to a D1 conference, and the `needs_review` count). Regenerate `docs/DATA_PROFILE.md`.

### Wiring
- Makefile: add `pull-bbref`, `backfill`, `schools`. Keep `make pull` MLB-only so it stays fast, and add `make all-data` that runs everything in order.
- Deps: `lxml`, `rapidfuzz`, plus whatever the Wikipedia table needs (prefer `read_html`, no new parser).

## Testing (offline and deterministic; keep the suite green)
- Fixtures: one real Baseball-Reference round page trimmed to ~6 rows. Include a supplemental pick, an unsigned pick with a blank bonus, and a name with an accent or suffix. Add a trimmed Wikipedia table (~10 rows).
- Tests:
  - bbref parse: row count, `bonus_usd` parsing (`$6,582,000`, blank), `signed` bool, supplemental row kept, `drafted_out_of` preserved.
  - `fetch_text_cached`: a cache hit makes zero calls; `min_interval_s` is respected (mock `time.sleep`/`monotonic`); **a 429 raises `RateLimitedError` after exactly one request** (no retries); the MLB JSON path still retries as before.
  - Backfill join: correct match on `(year, pick)`; a deliberate name mismatch is flagged and its bonus excluded; name normalization (`José Ramírez Jr.` → `jose ramirez`).
  - School type rules: one case per priority level, including `(FL) HS` → HS, `San Jacinto College North (Houston, TX)` → JC, and a bare-`JR` class not being used.
  - `schools.csv` contract: unique `school_name_raw`; enum values valid; every `D1` row has both conference columns; every raw name exists in the draft data; manual rows survive a re-run.
  - People cache: the file name changes when the ID set changes.
- Any live test is `@pytest.mark.live` and deselected by default.

## Constraints
- Be a polite client of Baseball-Reference: 7 s minimum gap, no 429 retries, cache everything, and pull only the pages listed above. Credit Baseball-Reference in the README's data sources section.
- Never invent data. No conferences from memory, no guessed bonuses. Unknown stays unknown and gets flagged.
- Don't touch `draft_picks.parquet` semantics. Backfill is a separate table; Task 3 does the coalescing.
- Raw and interim data stay git-ignored. `reference/*.csv` and fixtures are committed.

## Acceptance criteria
1. `make all-data` completes. A second run makes zero network calls.
2. `bonus_backfill.parquet` exists. The join match rate and the 2017 agreement numbers are in the profile.
3. `reference/schools.csv` and `reference/conference_moves_2024.csv` exist and pass the contract tests.
4. `make lint` and `make test` pass, with no network in tests.
5. On branch `task-02-bonus-and-schools`, everything staged, nothing committed, nothing under `data/` staged except `.gitkeep`.

## Report back with
- `git status --short` and the current branch, confirming staged, not committed
- Baseball-Reference rows per year vs. MLB picks per year, and how supplemental picks were handled
- Bonus coverage by year × round band (before and after backfill) for 2012–2016
- Join match rate, mismatch count, and 5 examples of mismatches
- 2017 cross-check: exact %, within-1% %, and the top 10 disagreements
- School ref: counts by type and division, % of college picks with a D1 conference, `needs_review` count, all alias groups, and **20 random D1 rows** (name, canonical, both conferences) for me to spot-check
- Total runtime of the first `pull-bbref`, and whether any 429/403 occurred
- Deviations from this brief and why; anything to flag for Task 3

Reminder: STAGE with `git add -A`, DO NOT COMMIT, and no AI attribution anywhere.
