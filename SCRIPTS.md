# Scripts reference — `py/` and `R/`

This document describes every script in `py/` (data extraction, scoring, and
reporting) and `R/` (plots built on top of that data). It is a reference for
the pipeline that sits behind the Quarto site, not part of the site itself.

For the site build itself (`quarto render`, `docs/`, post structure), see
`CLAUDE.md`.

## Pipeline order

The scripts form a dependency chain. Rough run order, with the file each
step reads and writes:

```
extract_wc2026.py        files/world_cup_2026.xlsx      → gData/wc2026.json
scan_predictions.py       xlsx/*.xlsx + wc2026.json      → gData/predictions.json
check_ko_scores.py        xlsx/*.xlsx                    → (validation only, no output)

fasit_cumulative_goals.py fasit/world_cup_2026_fasit.xlsx → gData/fasit_cumulative_goals.json
cumulative_goals.py       gData/predictions.json          → gData/cumulative_goals.json
cumulative_goals_vs_fasit.py  fasit xlsx + predictions.json → gData/cumulative_goals_vs_fasit.json
goals_progress_points.py  gData/cumulative_goals_vs_fasit.json → gData/goals_progress_points.json

score.py                  fasit xlsx + predictions.json
                           (+ qualitative.json, correct_answers.json,
                              goals_progress_points.json if --include-goals-progress)
                                                          → gData/scores.json, scores.csv, fasit.json

standings.py               gData/scores.json              → gData/standings.csv
similarity.py              gData/predictions.json          → gData/similarity.json, similarity.csv
ko_bracket.py               gData/fasit.json + predictions.json + scores.json → gData/ko_bracket.json

review.py / show_match.py                                 (CLI reports, no output files)
```

`generate_predictions.py` and `simulate_tournament.py` are a separate,
self-contained branch used for synthetic/simulated data (testing and
probability estimates), not part of the scoring pipeline above.

Every R script under `R/` reads one or more of the JSON/CSV files produced
above and renders a plot; none of them mutate `gData/`.

---

## `py/`

### `extract_wc2026.py`
Reads the blank tournament template (`files/world_cup_2026.xlsx`) and writes
`gData/wc2026.json`: the 12 groups, the 72 group-stage fixtures (match id,
date, home/away, group), and the knockout bracket's slot labels (e.g. `"1A"`,
`"3ABCDF"`) read straight out of the template's own formulas. This is the
fixture reference every other script joins against for team names and match
numbers.
Usage: `python py/extract_wc2026.py [xlsx_path] [output_path]`

### `scan_predictions.py`
Reads every participant's filled-in prediction spreadsheet from `xlsx/` and
writes `gData/predictions.json`. Group-stage scores come from columns F/G;
knockout predictions are read from fixed bracket columns (`BL`/`BS`/`BZ`/`CG`/`CN`
etc., two rows per match), then normalised into a flat, chronologically
sorted list keyed by fasit match number via `MATCH_ID_MAP`. Also derives each
player's predicted champion/runner-up/third-place from their filled bracket.
Requires `gData/wc2026.json` (run `extract_wc2026.py` first).
Usage: `python py/scan_predictions.py [xlsx_dir] [output_path] [fixture_json]`

### `check_ko_scores.py`
Standalone QA script (not part of the main pipeline) that validates
knockout scores in each participant xlsx: extra-time and penalty columns must
be cumulative (≥ full-time score), and ET/PEN should only be present when the
prior period was drawn. Prints any inconsistencies found; exits cleanly if
none.
Usage: `python check_ko_scores.py [xlsx_dir]` (defaults to `xlsx/`)

### `score.py`
The scoring engine — computes each player's competition score from
predictions vs. the actual fasit results. Reads results directly from
`fasit/world_cup_2026_fasit.xlsx` (`read_fasit()`), which also assigns
`play_order` to group-stage matches by kickoff time (so standings/lag logic
compares matches by when they were actually played, not their fixture
number).

Scoring categories:
- **Qualitative questions** (17 Qs, +30 each, max 510) — from `gData/qualitative.json` + `fasit/correct_answers.json`.
- **Group stage** (72 matches, +25 correct outcome − Δhome²− Δaway², max 1800).
- **Knockout** (32 matches, +25/team reaching the round, +5 bonus for correct bracket slot, max 1920).
- **Medals** (+200 champion, +100 runner-up, +70 third place, max 370).
- **Goals progress** (optional, off by default; +0–30 exponential-decay credit from `gData/goals_progress_points.json`; enable with `--include-goals-progress`).

Theoretical max is 4600 (4630 with goals progress). Writes `gData/scores.json`
(full per-player detail), `gData/scores.csv` (flat, sorted by total), and
`gData/fasit.json` (the parsed actual results, reused by several other
scripts/plots as the "ground truth" reference).
Usage: `python py/score.py [fasit_path] [predictions_path] [--include-goals-progress]`

### `goals_progress_points.py`
Scores each player's predicted *cumulative* goal total (as of the latest
played match, or a specific `--this-match`) against the fasit's actual
cumulative total, with credit decaying exponentially with the absolute error
(`30 * exp(-|pred-actual| / (actual/10))`; special-cased at 0). Reads
`gData/cumulative_goals_vs_fasit.json`, writes
`gData/goals_progress_points.json`, which `score.py --include-goals-progress`
consumes.
Usage: `python py/goals_progress_points.py [--this-match N] [--input PATH] [--deltagere PATH] [--output PATH]`

### `cumulative_goals.py`
Computes each player's *predicted* running total goals across all 104
matches (in match order) from `gData/predictions.json`. Writes
`gData/cumulative_goals.json` — consumed directly by `R/cumulative_goals.R`.
Usage: `python cumulative_goals.py [input_path] [output_path]`

### `fasit_cumulative_goals.py`
The actual-results counterpart to `cumulative_goals.py`: running total goals
scored so far from `fasit/world_cup_2026_fasit.xlsx` (imports
`read_fasit` from `score.py`). Unplayed matches contribute 0 so the array
stays aligned to match numbers 1–104. Writes
`gData/fasit_cumulative_goals.json`.
Usage: `python py/fasit_cumulative_goals.py [fasit_path] [output_path]`

### `cumulative_goals_vs_fasit.py`
Combines the two scripts above into one file so predicted and actual pace can
be plotted on the same match-number axis: predicted cumulative goals per
player (full 1–104) alongside the fasit's actual cumulative goals, with a
`played` flag per match index (false once matches run out). Writes
`gData/cumulative_goals_vs_fasit.json`, which `goals_progress_points.py`
reads.
Usage: `python py/cumulative_goals_vs_fasit.py [fasit_path] [predictions_path] [output_path]`

### `standings.py`
Turns `gData/scores.json` into a long-format CSV — one row per
(player, match) — with cumulative score, rank, and rank change at each
snapshot. Group-stage and knockout running totals are combined into one
timeline ordered by `play_order` (not match number, so out-of-order kickoffs
are handled correctly); qualitative and goals-progress points are folded in
as a constant offset from the start, and medal bonuses are folded in exactly
at match 103 (bronze) and 104 (champion + runner-up) so they show up in the
cumulative total instead of being dropped. Writes `gData/standings.csv`,
consumed by `R/plot_standings.R`, `R/scores.R`, and `R/righteousness_index.R`.
Usage: `python py/standings.py [scores_path] [output_csv] [--no-qs] [--no-goals-progress]`

### `similarity.py`
Measures how similarly every pair of players predicted the tournament, by
scoring each player's predictions against every other player's predictions
used as "ground truth" (reusing `score_group_stage`/`score_knockout`/
`score_champion` from `score.py`). Produces an N×N raw-score matrix, a
symmetric "similarity" per pair (average of both directions, normalised by
the geometric mean of each player's self-score), and a sorted pairs list.
Writes `gData/similarity.json` and `gData/similarity.csv`; consumed by
`R/similarity_network.R` and `R/similarity_network_top3.R`.
Usage: `python py/similarity.py [predictions_path]`

### `ko_bracket.py`
For each knockout stage, shows which teams each participant predicted vs.
the fasit's actual teams, annotating each prediction ✓✓ (correct team *and*
bracket slot), ✓ (correct team, wrong slot), or ✗ (wrong). Also prints a
medal-prediction summary (champion/runner-up/third place vs. actual).
Requires `gData/fasit.json` and `gData/predictions.json`
(run `score.py` and `scan_predictions.py` first). Writes
`gData/ko_bracket.json` (only when run without `--stage`/`--player` filters),
consumed by `R/ko_bracket.R`.
Usage: `python py/ko_bracket.py [--stage r32|r16|qf|sf|final|bronze] [--player NAME]`

### `review.py`
Prints a full match-by-match review for one participant: a scoring
breakdown across all five categories (qualitative, group stage, knockout,
medals, goals progress), every qualitative question with predicted vs.
actual answer and a ✓/✗ mark, predicted vs. actual medal picks, then the
group-stage + knockout match table with running cumulative score, and a
grand total pulled directly from `gData/scores.json["total"]` (so it always
matches the real total, including medals/goals-progress). Requires
`gData/scores.json` and `gData/deltagere.json`; `gData/fasit.json` is
optional (supplies the actual medal winners).
Usage: `python py/review.py <abbr|full_name|file_stem> [--match-id]`

### `show_match.py`
Lists every participant's group-stage prediction for one match, sorted from
biggest home win to biggest away win (blank line between outcome groups).
Requires `gData/predictions.json` and `gData/deltagere.json`.
Usage: `python py/show_match.py <match_number>`

### `generate_predictions.py`
Generates a full, internally-consistent set of predictions for all 104
matches (group stage → knockout, including realistic FIFA-ranking-weighted
score simulation, group tables, and 3rd-place-team bracket assignment).
Writes `gData/generated_<player_name>.json`. Used for testing/synthetic
data, not real participant scoring. Exposes `simulate()`, reused by
`simulate_tournament.py`.
Usage: `python generate_predictions.py [seed] [player_name]`

### `simulate_tournament.py`
Runs `generate_predictions.simulate()` N times (default 10,000) and
aggregates outcome probabilities per team (group win / advance / reach each
knockout round / champion), average group-table stats, and per-match goals
distributions. Writes `gData/simulations.json`, consumed by
`R/goals_distribution.R`.
Usage: `python simulate_tournament.py [n_simulations] [output_name]`

---

## `R/`

### `plot_standings.R`
The main standings chart library. `plot_standings_return()` builds the base
data frame (current cumulative score per player at a given match, plus the
score change over a configurable `lag` of games back) from
`gData/standings.csv`. Three plotting functions build on it:
- `plot_standings()` — horizontal bar chart, colour = points gained over the
  last `lag` games.
- `plot_standings_stacked()` — horizontal bar chart, segments stacked by
  scoring category (Qualitative, Group stage, Knockout, Medals, Goals
  progress), reading category totals from `gData/scores.json`.
- `plot_standings_by_winner()` — horizontal bar chart, colour = each
  player's predicted tournament winner (from `gData/podium_table.csv`).

### `scores.R`
A standalone (non-function) script version of the same "current standings,
coloured by recent change" bar chart as `plot_standings()`, reading directly
from `gData/standings.csv` and printing the plot rather than returning it.

### `podium_table.R`
Derives each participant's predicted Gold/Silver/Bronze from
`gData/predictions.json`'s knockout bracket (winner/loser of the Final,
winner of the bronze match, resolved through FT → ET → penalties). Prints
the table, writes `gData/podium_table.csv` (used by `plot_standings_by_winner()`
in `plot_standings.R`), and renders a styled `ggplot2` table image to
`gData/podium_table.png`.

### `group_stage_scatter.R`
`plot_match(match_no)` plots one group-stage match as a scatter of predicted
scorelines: x/y = away/home goals predicted, dot size = number of
participants who predicted that exact score, colour = the points that
scoreline would earn against the actual result (or, before `fasit.json`
exists, against the modal prediction). Reads `gData/predictions.json` and,
if present, `gData/fasit.json`. `plot_match(n, save = TRUE)` also writes
`gData/match_NNN.png`.

### `cumulative_goals.R`
Plots every player's predicted cumulative goal total across all 104 matches
as a line chart with stage-boundary shading, from `gData/cumulative_goals.json`.
Saves `figures/cumulative_goals.png`.

### `goals_distribution.R`
Two plots from `gData/simulations.json`'s per-match goal-count distributions
(from `simulate_tournament.py`): a faceted bar chart of goal probability by
tournament stage (`figures/goals_by_stage.png`), and a match × goals heatmap
across all 104 matches with the average-goals line overlaid
(`figures/goals_heatmap.png`).

### `similarity_network.R`
Network graph (via `igraph`/`ggraph`) of prediction similarity between all
player pairs, from `gData/similarity.json`. Edges shown only for similarity
≥ 0.6 (solid blue = positive, dashed red = negative), edge thickness =
similarity, node size = self-score. Saves `gData/similarity_network.png`.

### `similarity_network_top3.R`
Same similarity data as above, but keeps only each player's top-3 most
similar partners (union across both endpoints) to declutter a full
pairwise graph. Node colour = predicted world champion; node label =
abbreviation from `gData/deltagere.json`. Saves
`gData/similarity_network_top3.png`.

### `righteousness_index.R`
A satirical "Index of Righteousness": scores each country by the mean of
three V-Dem indicators (electoral democracy, physical-integrity human
rights, and inverted corruption), then scores each *contestant* by the
weighted-mean righteousness of the teams in their bracket (deeper runs —
r32 through champion — count more). The file is explicit that its "editorial
adjustments" are declared, not hidden: a fixed penalty/bonus reorders the
honest V-Dem ranking (Sweden docked, Norway boosted), and several
named per-contestant penalties are applied (time spent on the qualitative
survey, non-participation, and a few individually named adjustments), all
documented inline as intentional, non-scientific flourishes rather than
methodology bugs. Produces `righteous_countries` / `righteous_standings`
tables and three plot functions: `plot_righteousness()`,
`plot_country_righteousness()`, `plot_points_vs_righteousness()` (points vs.
righteousness correlation). `save_righteousness_outputs()` writes the two
tables to CSV — call explicitly, not run on source.

### `ko_bracket.R`
`plot_ko_bracket()` reads `gData/ko_bracket.json` (from `ko_bracket.py`) and
draws a heatmap: rows = players (sorted by total knockout points), columns =
knockout stage, fill = points earned as % of that stage's maximum, cell
label = "correct teams / total slots". `save = TRUE` writes
`img/ko_bracket.png`.

### `worldcup_analysis.R`
Independent statistical analysis, not part of the competition-scoring
pipeline — it doesn't read anything from `gData/`. Pulls historical World
Cup match results (1994–2022, via `worldfootballR`), FIFA pre-tournament
ratings (`Data/fifa_ranking-2024-06-20.csv`), population (`WDI`), and V-Dem
democracy scores, then fits Poisson/negative-binomial mixed models
(`glmmTMB`, match-level random intercept as a "poor man's bivariate
Poisson") of goals scored as a function of FIFA rating, population, V-Dem
score, host advantage, and knockout stage. Includes model diagnostics via
`DHARMa`. See `CLAUDE.md` for the package/data requirements.
