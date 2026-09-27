# Task 7b: Review fixes on the redesign (same branch)

Stay on `task-07-app-redesign`. Everything from Tasks 6 and 7 is staged there and uncommitted;
keep it that way.

IMPORTANT: STAGE all changes (`git add -A`) but DO NOT COMMIT OR PUSH. No AI/session trailers.

## Fixes
1. **Overview tier heading must obey the significance rule.** For SEC college arms it currently says "4.7% of this group became regulars or better, vs 3.3% of all draftees" while the tile says "about the same". When the interval includes the baseline, the heading must say so, e.g. "4.7% of this group became regulars or better, about the same as all draftees (3.3%)". Route it through the same helper as the tiles, and add a test.
2. **Rankings value labels.** Remove the value text at the whisker tips; it reads as if the interval end were the value. Show the value in its own right-aligned column just left of the n column (e.g. "+2.8 pts"), colored by the significance rule. Keep the dots and intervals unlabeled.
3. **Trends: realignment marker.** 2025 uses the spring-2025 conference alignment, so conference lines jump (the Pac-12 falls to ~0%).
   - Draw the 2024→2025 segment of every **conference** line dotted.
   - Add a third vertical marker at 2025 labeled "Realigned conferences".
   - Append to the caption: "2025 uses post-2024 conference membership (e.g. the Pac-12 lost most of its members)."
   - School lines are unaffected.
4. **Trends: series palette.** Orange is reserved for "below expected", so series lines must not use it. Add a 4-color categorical palette to `theme.py`: `#1f5fbf` (blue), `#7b4fb3` (purple), `#3c4650` (slate), `#58a6d8` (sky). Use it for trend lines; "All draftees" stays grey dashed where shown.
   - Add a test that no trend trace uses `#d9822b`.
5. **Players strip wording:** when the bonus is unknown, write "bonus unknown" instead of "signed for unknown".

## Then
- Retake `overview-sec-arms.png`, `rankings-default.png` and `trends-default.png`.
- `make lint` and `make test` must pass, offline.
- Report: the new Overview tier heading for SEC college arms, the files changed, and `git status --short` confirming staged, not committed.

Reminder: STAGE with `git add -A`, DO NOT COMMIT OR PUSH, and no AI attribution anywhere.
