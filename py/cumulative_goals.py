"""
cumulative_goals.py
-------------------
Reads predictions.json and computes each player's cumulative total goals
predicted across all 104 matches (in match order).

Output: gData/cumulative_goals.json

Structure:
{
  "players": {
    "alice": {
      "goals_per_match": [1, 2, 3, 0, ...],   // goals in that match (home+away)
      "cumulative":      [1, 3, 6, 6, ...]    // running total after each match
    },
    ...
  },
  "match_labels": ["M1 GS", "M2 GS", ..., "M104 Final"],
  "match_index":  [1, 2, ..., 104]
}
"""

import json
import sys
from pathlib import Path

from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root

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
    """Return total goals in a match, or None if not predicted."""
    if "home_goals" in match:           # group stage
        h, a = match["home_goals"], match["away_goals"]
    else:                               # knockout
        h, a = match["team1_goals"], match["team2_goals"]
    if h is None or a is None:
        return None
    return h + a


def build_cumulative(matches_sorted: list[dict]) -> dict:
    goals_per_match = []
    cumulative      = []
    running         = 0
    for m in matches_sorted:
        g = goals_for_match(m)
        goals = g if g is not None else 0
        running += goals
        goals_per_match.append(goals)
        cumulative.append(running)
    return {"goals_per_match": goals_per_match, "cumulative": cumulative}


def make_label(match: dict) -> str:
    stage = STAGE_SHORT.get(match["stage"], match["stage"])
    return f"M{match['match']} {stage}"


def compute(input_path: str = None, output_path: str = None):
    input_path  = Path(input_path)  if input_path  else HERE / "gData" / "predictions.json"
    output_path = Path(output_path) if output_path else HERE / "gData" / "cumulative_goals.json"
    if not output_path.is_absolute():
        output_path = HERE / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    # Build sorted match list (by match number) for one player — same order for all
    first_player = next(iter(data["players"].values()))
    all_matches  = sorted(
        first_player["group_stage"] + first_player["knockout"],
        key=lambda m: m["match"]
    )
    match_index  = [m["match"]  for m in all_matches]
    match_labels = [make_label(m) for m in all_matches]

    players_out = {}
    for player, pred in data["players"].items():
        matches_sorted = sorted(
            pred["group_stage"] + pred["knockout"],
            key=lambda m: m["match"]
        )
        players_out[player] = build_cumulative(matches_sorted)
        total = players_out[player]["cumulative"][-1]
        print(f"  {player:20s}  total goals predicted: {total}")

    output = {
        "players":      players_out,
        "match_labels": match_labels,
        "match_index":  match_index,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(players_out)} player(s) → {output_path}")
    return output


if __name__ == "__main__":
    input_file  = sys.argv[1] if len(sys.argv) > 1 else None
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    compute(input_file, output_file)
