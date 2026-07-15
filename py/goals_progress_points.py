"""
goals_progress_points.py
-------------------------
Python port of goals_progress_points.R.

Scores each participant's predicted *cumulative* goal total (as of a given
match) against the actual cumulative goal total in the fasit, awarding
partial credit that decays exponentially with the absolute error:

    lambda = fasit_underveis / 10
    poeng  = 30 * exp(-|gjett_underveis - fasit_underveis| / lambda)

with the special case that if fasit_underveis == 0, poeng is 30 if the
guess is also 0, else 0 (avoids division by zero, matches the R logic
exactly).

Reads gData/cumulative_goals_vs_fasit.json, which already contains:
  {
    "match_labels": [...],
    "match_index":  [1, 2, ..., 104],
    "fasit": {
      "goals_per_match": [...],
      "cumulative":      [...],
      "played":          [true, true, ..., false, ...]
    },
    "players": {
      "<stem>": {
        "goals_per_match": [...],
        "cumulative":      [...]
      },
      ...
    }
  }

`this_match` (optional) pins the scoring to a specific value from
match_index instead of the latest played match — same behaviour as the
R function's `this_match` argument.

Output: gData/goals_progress_points.json
  {
    "meta": {
      "this_match":             <int>,    # match_index value scored through
      "fasit_cumulative_goals": <number>,
      "formula": "30 * exp(-|pred - actual| / (actual/10)); 30 if both 0 else 0 if actual==0"
    },
    "players": {
      "<stem>": {
        "full_name": "...",               # from deltagere.json if available
        "predicted_cumulative_goals": <number>,
        "actual_cumulative_goals":    <number>,
        "points": <int>                    # rounded, like R's round()
      },
      ...
    }
  }

This is meant to be read directly by score.py: look up
player["points"] by the same file-stem key used elsewhere in
predictions.json.

Usage:
    python goals_progress_points.py [--this-match N]
                                     [--input PATH] [--deltagere PATH] [--output PATH]
"""

import json
import math
import argparse
from pathlib import Path

try:
    from pyprojroot import here
    HERE = here()
except Exception:
    HERE = Path(__file__).resolve().parent.parent


def _points(gjett, fasit_val):
    if fasit_val == 0:
        return 30.0 if gjett == 0 else 0.0
    lam = fasit_val / 10
    return 30.0 * math.exp(-abs(gjett - fasit_val) / lam)


def _load_full_names(deltagere_path: Path) -> dict:
    """{file_stem: full_name} lookup from deltagere.json, if available."""
    if not deltagere_path.exists():
        return {}
    with open(deltagere_path, encoding="utf-8") as f:
        deltagere = json.load(f)
    lookup = {}
    for entry in deltagere:
        file = entry.get("file", "")
        stem = file[:-5] if file.endswith(".xlsx") else file
        full_name = entry.get("full_name")
        if stem and full_name:
            lookup[stem] = full_name
    return lookup


def compute(input_path=None, deltagere_path=None, output_path=None, this_match=None):
    input_path     = Path(input_path)     if input_path     else HERE / "gData" / "cumulative_goals_vs_fasit.json"
    deltagere_path = Path(deltagere_path) if deltagere_path else HERE / "gData" / "deltagere.json"
    output_path    = Path(output_path)    if output_path    else HERE / "gData" / "goals_progress_points.json"

    with open(input_path, encoding="utf-8") as f:
        raw = json.load(f)

    match_index = raw["match_index"]
    played = raw["fasit"]["played"]

    if this_match is None:
        played_idx = [i for i, p in enumerate(played) if p]
        if not played_idx:
            raise ValueError("No matches are marked as played in fasit.played")
        n_played = max(played_idx)
    else:
        try:
            n_played = match_index.index(this_match)
        except ValueError:
            raise ValueError(f"this_match={this_match} not found in match_index") from None
        if not played[n_played]:
            raise ValueError(f"this_match={this_match} has no result yet (fasit.played is false)")

    fasit_underveis = raw["fasit"]["cumulative"][n_played]
    full_names = _load_full_names(deltagere_path)

    players_out = {}
    for player, pred in raw["players"].items():
        gjett_underveis = pred["cumulative"][n_played]
        pts = round(_points(gjett_underveis, fasit_underveis))
        players_out[player] = {
            "full_name": full_names.get(player, player),
            "predicted_cumulative_goals": gjett_underveis,
            "actual_cumulative_goals": fasit_underveis,
            "points": pts,
        }

    output = {
        "meta": {
            "this_match": match_index[n_played],
            "fasit_cumulative_goals": fasit_underveis,
            "formula": "30 * exp(-|pred - actual| / (actual/10)); 30 if both 0 else 0 if actual==0",
        },
        "players": players_out,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Scored through match {match_index[n_played]} "
          f"(fasit cumulative goals = {fasit_underveis})")
    ranked = sorted(players_out.items(), key=lambda kv: kv[1]["points"], reverse=True)
    for player, d in ranked:
        label = d["full_name"]
        print(f"  {label:25s}  pred={d['predicted_cumulative_goals']:>4}  "
              f"actual={d['actual_cumulative_goals']:>4}  points={d['points']:>3}")
    print(f"\nWrote {len(players_out)} player(s) -> {output_path}")

    return output


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--this-match", type=int, default=None,
                    help="Score as of this match_index value instead of the latest played match")
    ap.add_argument("--input", default=None, help="Path to cumulative_goals_vs_fasit.json")
    ap.add_argument("--deltagere", default=None, help="Path to deltagere.json")
    ap.add_argument("--output", default=None, help="Path to write goals_progress_points.json")
    args = ap.parse_args()

    compute(
        input_path=args.input,
        deltagere_path=args.deltagere,
        output_path=args.output,
        this_match=args.this_match,
    )


if __name__ == "__main__":
    main()
