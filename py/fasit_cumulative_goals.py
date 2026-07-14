# -*- coding: utf-8 -*-
"""
fasit_cumulative_goals.py
--------------------------
Reads fasit/world_cup_2026_fasit.xlsx (actual results) and computes the
cumulative total goals scored across all 104 matches, in match order.

Only matches with both scores filled in count; matches not yet played
contribute 0 goals so the arrays stay aligned to match numbers 1-104.

Output: gData/fasit_cumulative_goals.json

Structure (mirrors gData/cumulative_goals.json so both can be plotted
on the same axis):
{
  "goals_per_match": [2, 3, 2, 5, ...],   // goals in that match (both teams)
  "cumulative":      [2, 5, 7, 12, ...],  // running total after each match
  "match_labels":    ["M1 GS", "M2 GS", ..., "M104 Final"],
  "match_index":     [1, 2, ..., 104]
}

Usage
-----
python py/fasit_cumulative_goals.py                        # project defaults
python py/fasit_cumulative_goals.py fasit/my_fasit.xlsx     # explicit fasit path
"""

import json
import sys
from pathlib import Path

from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root

from score import read_fasit

HERE = find_root(has_dir(".git"), start=Path(__file__).resolve().parent)

STAGE_SHORT = {
    "Group Stage":           "GS",
    "Round of 32":           "R32",
    "Round of 16":           "R16",
    "Quarterfinals":         "QF",
    "Semi-Finals":           "SF",
    "Third-Place Play-Off":  "3rd",
    "Final":                 "F",
}


def goals_for_match(match: dict) -> int | None:
    """Return total goals in a match, or None if not (fully) played."""
    if "home_goals" in match:           # group stage
        h, a = match["home_goals"], match["away_goals"]
    elif "team1_goals" in match:        # knockout
        h, a = match["team1_goals"], match["team2_goals"]
    else:
        return None
    if h is None or a is None:
        return None
    return h + a


def make_label(match: dict) -> str:
    stage = STAGE_SHORT.get(match.get("stage", "Group Stage"), match.get("stage", "GS"))
    return f"M{match['match']} {stage}"


def compute(fasit_path: str = None, output_path: str = None):
    fasit_path  = Path(fasit_path)  if fasit_path  else HERE / "fasit" / "world_cup_2026_fasit.xlsx"
    output_path = Path(output_path) if output_path else HERE / "gData" / "fasit_cumulative_goals.json"
    if not output_path.is_absolute():
        output_path = HERE / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not fasit_path.exists():
        raise FileNotFoundError(
            f"Fasit file not found: {fasit_path}\n"
            "Place the filled results file at fasit/world_cup_2026_fasit.xlsx"
        )

    fasit = read_fasit(fasit_path)
    all_matches = sorted(fasit["group_stage"] + fasit["knockout"], key=lambda m: m["match"])

    goals_per_match = []
    cumulative      = []
    match_labels    = []
    match_index     = []
    running   = 0
    n_played  = 0
    for m in all_matches:
        g = goals_for_match(m)
        if g is not None:
            n_played += 1
        goals = g if g is not None else 0
        running += goals
        goals_per_match.append(goals)
        cumulative.append(running)
        match_labels.append(make_label(m))
        match_index.append(m["match"])

    output = {
        "goals_per_match": goals_per_match,
        "cumulative":      cumulative,
        "match_labels":    match_labels,
        "match_index":     match_index,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Matches with a result: {n_played} / {len(all_matches)}")
    print(f"Total goals scored so far: {running}")
    print(f"\nWrote -> {output_path}")
    return output


if __name__ == "__main__":
    fasit_arg  = sys.argv[1] if len(sys.argv) > 1 else None
    output_arg = sys.argv[2] if len(sys.argv) > 2 else None
    compute(fasit_arg, output_arg)
