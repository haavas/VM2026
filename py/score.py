# -*- coding: utf-8 -*-
"""
score.py
--------
Calculates each player's competition score by comparing their predictions
(gData/predictions.json) against the actual results (gData/results.json).

Scoring rules (carried over from the original EM2024 script)
-------------------------------------------------------------
Group stage (per match played so far):
  +25   correct match outcome (win/draw/loss)
  -Δh²  squared error on home goals
  -Δa²  squared error on away goals

Knockout (only counted once all group stage matches are done):
  +5    per team predicted in the correct bracket slot  (correct_spot)
  +25   per team that reached the round, regardless of slot (correct_team)

Champion bonus:
  +200  if world champion predicted correctly

Output
------
gData/scores.json  — per-player breakdown + running totals after each match
gData/scores.csv   — final standings table (sorted by total score)

Usage
-----
python py/score.py                     # uses project defaults
python py/score.py results.json        # explicit results path
"""

import csv
import json
import sys
from pathlib import Path

from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root

# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------

def project_root() -> Path:
    return find_root(has_dir(".git"), start=Path(__file__).resolve().parent)


# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

CORRECT_OUTCOME_PTS  = 25
CORRECT_TEAM_PTS     = 25
CORRECT_SPOT_PTS     = 5
CHAMPION_BONUS       = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _outcome(h: int, a: int) -> int:
    """Return +1 home win, 0 draw, -1 away win."""
    if h > a:
        return 1
    if h < a:
        return -1
    return 0


# ---------------------------------------------------------------------------
# Group stage scoring
# ---------------------------------------------------------------------------

def score_group_stage(player_matches: list, result_matches: list) -> dict:
    """
    Compare player predictions against actual results match by match.

    Only matches present in result_matches (i.e. already played) are scored.
    Returns a dict with running cumulative points after each played match, plus
    component totals.
    """
    # Index results by match_id
    results = {m["match_id"]: m for m in result_matches
               if m.get("home_goals") is not None and m.get("away_goals") is not None}
    predictions = {m["match_id"]: m for m in player_matches}

    correct_outcome  = 0
    home_sq_err      = 0
    away_sq_err      = 0
    running          = []   # cumulative score after each played match (in match_id order)
    cumulative       = 0

    for match_id in sorted(results.keys()):
        r = results[match_id]
        p = predictions.get(match_id)

        r_h, r_a = r["home_goals"], r["away_goals"]

        if p is None or p.get("home_goals") is None or p.get("away_goals") is None:
            # No prediction for this match — contributes 0 but still logged
            running.append({"match_id": match_id, "cumulative": cumulative})
            continue

        p_h, p_a = p["home_goals"], p["away_goals"]

        dh = p_h - r_h
        da = p_a - r_a

        outcome_pts = CORRECT_OUTCOME_PTS if _outcome(p_h, p_a) == _outcome(r_h, r_a) else 0
        correct_outcome += (1 if outcome_pts else 0)
        home_sq_err     += dh * dh
        away_sq_err     += da * da

        match_pts  = outcome_pts - dh * dh - da * da
        cumulative += match_pts

        running.append({
            "match_id":    match_id,
            "pred":        f"{p_h}-{p_a}",
            "actual":      f"{r_h}-{r_a}",
            "outcome_pts": outcome_pts,
            "home_sq_err": dh * dh,
            "away_sq_err": da * da,
            "match_pts":   match_pts,
            "cumulative":  cumulative,
        })

    group_pts = CORRECT_OUTCOME_PTS * correct_outcome - home_sq_err - away_sq_err

    return {
        "points":           group_pts,
        "correct_outcome":  correct_outcome,
        "home_sq_err":      home_sq_err,
        "away_sq_err":      away_sq_err,
        "matches_played":   len(results),
        "running":          running,
    }


# ---------------------------------------------------------------------------
# Knockout scoring
# ---------------------------------------------------------------------------

def _flatten_ko(ko: dict) -> dict[str, list[str]]:
    """Return {round_name: [team, ...]} from a knockout dict."""
    return {
        "r32_right":     ko.get("r32_right", []),
        "r32_left":      ko.get("r32_left", []),
        "quarterfinals": ko.get("quarterfinals", []),
        "semifinal_left":  ko.get("semifinal_left", []),
        "semifinal_right": ko.get("semifinal_right", []),
    }


def score_knockout(player_ko: dict, result_ko: dict) -> dict:
    """
    For each knockout round, compare predicted teams against actual teams.

    correct_spot : team predicted in the exact same list position
    correct_team : team appeared in the round at all (any position)
    """
    pred   = _flatten_ko(player_ko)
    actual = _flatten_ko(result_ko)

    correct_spot = 0
    correct_team = 0
    detail       = {}

    for round_name in pred:
        p_list = [t for t in pred[round_name]   if t]
        a_list = [t for t in actual.get(round_name, []) if t]

        spots  = sum(1 for p, a in zip(p_list, a_list) if p == a)
        teams  = len(set(p_list) & set(a_list))

        correct_spot += spots
        correct_team += teams

        detail[round_name] = {
            "correct_spot": spots,
            "correct_team": teams,
        }

    ko_pts = correct_spot * CORRECT_SPOT_PTS + correct_team * CORRECT_TEAM_PTS

    return {
        "points":        ko_pts,
        "correct_spot":  correct_spot,
        "correct_team":  correct_team,
        "detail":        detail,
    }


# ---------------------------------------------------------------------------
# Champion scoring
# ---------------------------------------------------------------------------

def score_champion(predicted: str | None, actual: str | None) -> int:
    if predicted and actual and predicted == actual:
        return CHAMPION_BONUS
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def score(results_path: str = None,
          predictions_path: str = None,
          output_json: str = None,
          output_csv: str = None) -> None:

    root = project_root()

    results_path     = Path(results_path)     if results_path     else root / "gData" / "results.json"
    predictions_path = Path(predictions_path) if predictions_path else root / "gData" / "predictions.json"
    output_json      = Path(output_json)      if output_json      else root / "gData" / "scores.json"
    output_csv       = Path(output_csv)       if output_csv       else root / "gData" / "scores.csv"

    if not results_path.exists():
        raise FileNotFoundError(
            f"Results file not found: {results_path}\n"
            "Create gData/results.json with actual match scores first."
        )
    if not predictions_path.exists():
        raise FileNotFoundError(
            f"Predictions file not found: {predictions_path}\n"
            "Run scan_predictions.py first."
        )

    with open(results_path, encoding="utf-8") as f:
        results = json.load(f)
    with open(predictions_path, encoding="utf-8") as f:
        preds = json.load(f)

    result_group_stage = results.get("group_stage", [])
    result_knockout    = results.get("knockout", {})
    result_champion    = results.get("world_champion")

    scores = {}

    for player, data in preds["players"].items():
        gs  = score_group_stage(data["group_stage"], result_group_stage)
        ko  = score_knockout(data["knockout"], result_knockout)
        champ_pts = score_champion(data.get("world_champion"), result_champion)

        total = gs["points"] + ko["points"] + champ_pts

        scores[player] = {
            "total":            total,
            "group_stage":      gs,
            "knockout":         ko,
            "champion_pts":     champ_pts,
            "world_champion":   data.get("world_champion"),
        }

        print(
            f"  {player:<20s}  total={total:+6d}  "
            f"group={gs['points']:+6d}  ko={ko['points']:+4d}  "
            f"champ={champ_pts:+4d}  "
            f"[outcomes={gs['correct_outcome']}  "
            f"Δh²={gs['home_sq_err']}  Δa²={gs['away_sq_err']}  "
            f"spot={ko['correct_spot']}  team={ko['correct_team']}]"
        )

    # --- JSON output ---
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({"players": scores}, f, ensure_ascii=False, indent=2)

    # --- CSV output (sorted by total, descending) ---
    sorted_players = sorted(scores.items(), key=lambda x: x[1]["total"], reverse=True)

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "rank", "player", "total",
            "group_pts", "ko_pts", "champion_pts",
            "correct_outcome", "home_sq_err", "away_sq_err",
            "correct_spot", "correct_team", "predicted_champion",
        ])
        for rank, (player, s) in enumerate(sorted_players, 1):
            writer.writerow([
                rank,
                player,
                s["total"],
                s["group_stage"]["points"],
                s["knockout"]["points"],
                s["champion_pts"],
                s["group_stage"]["correct_outcome"],
                s["group_stage"]["home_sq_err"],
                s["group_stage"]["away_sq_err"],
                s["knockout"]["correct_spot"],
                s["knockout"]["correct_team"],
                s["world_champion"] or "",
            ])

    print(f"\nWrote → {output_json}")
    print(f"Wrote → {output_csv}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results_arg     = sys.argv[1] if len(sys.argv) > 1 else None
    predictions_arg = sys.argv[2] if len(sys.argv) > 2 else None
    score(results_arg, predictions_arg)
