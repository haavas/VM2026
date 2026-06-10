# -*- coding: utf-8 -*-
"""
similarity.py
-------------
Measures how similarly each pair of players predicted the tournament by
using each player's predictions as "ground truth" and scoring every other
player against them.  The resulting N×N matrix is written to gData/.

For player pair (A, B):
  - score(A|B) : how many points A earns if B's predictions were the result
  - score(B|A) : how many points B earns if A's predictions were the result
  - similarity : average of the two (symmetric measure)

The diagonal (self-score) is the maximum possible score a player could
achieve given their own predictions, which serves as a useful normalisation
reference.

Output
------
gData/similarity.json  — full N×N matrix with raw and normalised scores
gData/similarity.csv   — flat table sorted by similarity (descending)

Usage
-----
python py/similarity.py                      # uses project defaults
python py/similarity.py predictions.json     # explicit predictions path
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
# Import scoring functions from score.py
# (score.py lives in the same py/ directory as this script)
# ---------------------------------------------------------------------------

import importlib.util, os

def _load_score_module():
    score_path = Path(__file__).resolve().parent / "score.py"
    spec = importlib.util.spec_from_file_location("score", score_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Build a "results" dict from a player's predictions
# ---------------------------------------------------------------------------

def player_as_results(player_data: dict) -> dict:
    """
    Convert a player's predictions into the same schema that results.json uses,
    so it can be passed directly to score_group_stage / score_knockout.
    """
    return {
        "group_stage":    player_data["group_stage"],
        "knockout":       player_data["knockout"],
        "world_champion": player_data.get("world_champion"),
    }


# ---------------------------------------------------------------------------
# Score one player against another's predictions as ground truth
# ---------------------------------------------------------------------------

def pairwise_score(scorer_data: dict, truth_data: dict, score_mod) -> int:
    gs = score_mod.score_group_stage(
        scorer_data["group_stage"],
        truth_data["group_stage"],
    )
    ko = score_mod.score_knockout(
        scorer_data["knockout"],
        truth_data["knockout"],
    )
    champ = score_mod.score_champion(
        scorer_data.get("world_champion"),
        truth_data.get("world_champion"),
    )
    return gs["points"] + ko["points"] + champ


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def similarity(predictions_path: str = None,
               output_json: str = None,
               output_csv: str = None) -> None:

    root = project_root()

    predictions_path = Path(predictions_path) if predictions_path \
                       else root / "gData" / "predictions.json"
    output_json = Path(output_json) if output_json \
                  else root / "gData" / "similarity.json"
    output_csv  = Path(output_csv)  if output_csv  \
                  else root / "gData" / "similarity.csv"

    if not predictions_path.exists():
        raise FileNotFoundError(
            f"Predictions file not found: {predictions_path}\n"
            "Run scan_predictions.py first."
        )

    score_mod = _load_score_module()

    with open(predictions_path, encoding="utf-8") as f:
        preds = json.load(f)

    players = sorted(preds["players"].keys())
    n       = len(players)
    print(f"Players ({n}): {players}\n")

    # --- Build N×N matrix ---
    # matrix[i][j] = score player[i] gets when player[j] is the "ground truth"
    matrix = [[0] * n for _ in range(n)]

    for i, scorer in enumerate(players):
        for j, truth in enumerate(players):
            s = pairwise_score(
                preds["players"][scorer],
                player_as_results(preds["players"][truth]),
                score_mod,
            )
            matrix[i][j] = s

    # --- Diagonal = self-score (maximum achievable) ---
    self_scores = [matrix[i][i] for i in range(n)]

    # --- Symmetric similarity: average of score(A|B) and score(B|A) ---
    # Normalised: divide by geometric mean of the two self-scores
    similarity_matrix = {}
    pairs = []

    for i, p1 in enumerate(players):
        similarity_matrix[p1] = {}
        for j, p2 in enumerate(players):
            raw_ij    = matrix[i][j]   # p1 scored against p2's truth
            raw_ji    = matrix[j][i]   # p2 scored against p1's truth
            avg_raw   = (raw_ij + raw_ji) / 2

            # Normalise by geometric mean of self-scores (avoids div-by-zero)
            denom = (self_scores[i] * self_scores[j]) ** 0.5
            norm  = avg_raw / denom if denom > 0 else 0.0

            similarity_matrix[p1][p2] = {
                "score_ab":    raw_ij,
                "score_ba":    raw_ji,
                "avg_raw":     avg_raw,
                "normalised":  round(norm, 4),
            }

            if i < j:   # each pair once
                pairs.append({
                    "player_a":   p1,
                    "player_b":   p2,
                    "score_ab":   raw_ij,
                    "score_ba":   raw_ji,
                    "avg_raw":    avg_raw,
                    "normalised": round(norm, 4),
                })

    # Sort pairs by normalised similarity descending
    pairs.sort(key=lambda x: x["normalised"], reverse=True)

    # --- Print summary ---
    col_w = max(len(p) for p in players) + 2
    header = " " * col_w + "".join(f"{p:>{col_w}}" for p in players)
    print("Raw score matrix (row = scorer, col = ground truth):")
    print(header)
    for i, p in enumerate(players):
        row = f"{p:<{col_w}}" + "".join(f"{matrix[i][j]:>{col_w}}" for j in range(n))
        print(row)

    print()
    if pairs:
        print("Pairwise similarity (normalised):")
        for pair in pairs:
            print(f"  {pair['player_a']} ↔ {pair['player_b']}: "
                  f"{pair['normalised']:.4f}  "
                  f"(A→B={pair['score_ab']:+d}, B→A={pair['score_ba']:+d})")

    # --- JSON output ---
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({
            "players":    players,
            "self_scores": {p: self_scores[i] for i, p in enumerate(players)},
            "matrix":     similarity_matrix,
            "pairs":      pairs,
        }, f, ensure_ascii=False, indent=2)

    # --- CSV output ---
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "player_a", "player_b",
            "score_ab", "score_ba", "avg_raw", "normalised",
        ])
        for pair in pairs:
            writer.writerow([
                pair["player_a"], pair["player_b"],
                pair["score_ab"], pair["score_ba"],
                pair["avg_raw"],  pair["normalised"],
            ])

    print(f"\nWrote → {output_json}")
    print(f"Wrote → {output_csv}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    preds_arg = sys.argv[1] if len(sys.argv) > 1 else None
    similarity(preds_arg)
