# -*- coding: utf-8 -*-
"""
cumulative_goals_vs_fasit.py
-----------------------------
Combines cumulative_goals.py (each participant's predicted cumulative
goals, from gData/predictions.json) with fasit_cumulative_goals.py
(actual cumulative goals scored so far, from
fasit/world_cup_2026_fasit.xlsx) into a single comparable series, so
predicted pace and actual pace can be plotted on the same match-number
axis (1-104).

The "fasit" series only advances for matches that have an actual result;
for matches not yet played its cumulative total simply holds at the last
known value, and "played" is False for those points so a consumer can
decide whether to draw/truncate the line there.

Output: gData/cumulative_goals_vs_fasit.json

Structure:
{
  "match_labels": ["M1 GS", "M2 GS", ..., "M104 Final"],
  "match_index":  [1, 2, ..., 104],
  "fasit": {
    "goals_per_match": [2, 3, ...],
    "cumulative":      [2, 5, ...],
    "played":          [true, true, ..., false, false]
  },
  "players": {
    "alice": {
      "goals_per_match": [1, 2, ...],
      "cumulative":      [1, 3, ...]
    },
    ...
  }
}

Usage
-----
python py/cumulative_goals_vs_fasit.py                                          # project defaults
python py/cumulative_goals_vs_fasit.py fasit/my_fasit.xlsx gData/predictions.json out.json
"""

import json
import sys
from pathlib import Path

from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root

from score import read_fasit
from cumulative_goals import goals_for_match as player_goals_for_match, match_number, make_label
from fasit_cumulative_goals import goals_for_match as fasit_goals_for_match

HERE = find_root(has_dir(".git"), start=Path(__file__).resolve().parent)


def compute(fasit_path: str = None, predictions_path: str = None, output_path: str = None):
    fasit_path       = Path(fasit_path)       if fasit_path       else HERE / "fasit" / "world_cup_2026_fasit.xlsx"
    predictions_path = Path(predictions_path) if predictions_path else HERE / "gData" / "predictions.json"
    output_path       = Path(output_path)       if output_path       else HERE / "gData" / "cumulative_goals_vs_fasit.json"
    if not output_path.is_absolute():
        output_path = HERE / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not fasit_path.exists():
        raise FileNotFoundError(
            f"Fasit file not found: {fasit_path}\n"
            "Place the filled results file at fasit/world_cup_2026_fasit.xlsx"
        )
    if not predictions_path.exists():
        raise FileNotFoundError(
            f"Predictions file not found: {predictions_path}\n"
            "Run scan_predictions.py first."
        )

    fasit = read_fasit(fasit_path)
    fasit_by_match = {m["match"]: m for m in fasit["group_stage"] + fasit["knockout"]}

    with open(predictions_path, encoding="utf-8") as f:
        predictions = json.load(f)

    # Master 1-104 match order/labels come from a player's predictions,
    # which always cover the full tournament (unlike fasit, which only
    # has entries for matches played/decided so far).
    first_player = next(iter(predictions["players"].values()))
    all_matches  = sorted(
        first_player["group_stage"] + first_player["knockout"],
        key=match_number
    )
    match_index  = [match_number(m) for m in all_matches]
    match_labels = [make_label(m) for m in all_matches]

    # --- Fasit (actual) cumulative, aligned to match_index ---
    fasit_goals_per_match = []
    fasit_cumulative      = []
    fasit_played          = []
    running = 0
    for mn in match_index:
        fm = fasit_by_match.get(mn)
        g  = fasit_goals_for_match(fm) if fm is not None else None
        if g is not None:
            running += g
            fasit_goals_per_match.append(g)
            fasit_played.append(True)
        else:
            fasit_goals_per_match.append(0)
            fasit_played.append(False)
        fasit_cumulative.append(running)

    # --- Each participant's predicted cumulative, full 1-104 ---
    players_out = {}
    for player, pred in predictions["players"].items():
        matches_sorted = sorted(
            pred["group_stage"] + pred["knockout"],
            key=match_number
        )
        goals_per_match = []
        cumulative      = []
        running = 0
        for m in matches_sorted:
            g = player_goals_for_match(m)
            goals = g if g is not None else 0
            running += goals
            goals_per_match.append(goals)
            cumulative.append(running)
        players_out[player] = {"goals_per_match": goals_per_match, "cumulative": cumulative}
        n_played = sum(fasit_played)
        pace = cumulative[n_played - 1] if n_played else 0
        print(f"  {player:20s}  predicted so far: {pace:4d}   actual so far: {fasit_cumulative[n_played-1] if n_played else 0:4d}")

    output = {
        "match_labels": match_labels,
        "match_index":  match_index,
        "fasit": {
            "goals_per_match": fasit_goals_per_match,
            "cumulative":      fasit_cumulative,
            "played":          fasit_played,
        },
        "players": players_out,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(players_out)} player(s) + fasit -> {output_path}")
    return output


if __name__ == "__main__":
    fasit_arg       = sys.argv[1] if len(sys.argv) > 1 else None
    predictions_arg = sys.argv[2] if len(sys.argv) > 2 else None
    output_arg      = sys.argv[3] if len(sys.argv) > 3 else None
    compute(fasit_arg, predictions_arg, output_arg)
