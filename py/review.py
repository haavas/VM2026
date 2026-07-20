# -*- coding: utf-8 -*-
"""
review.py
---------
Prints a match-by-match review for a specific participant.

Usage
-----
python py/review.py <abbr_or_name>              # sort by play_order (default)
python py/review.py <abbr_or_name> --match-id   # sort by match id
python py/review.py TC
python py/review.py "Tom Christensen" --match-id

The participant is matched against abbr, full_name, or file stem
(case-insensitive).
"""

import json
import sys
from pathlib import Path

from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root


def project_root() -> Path:
    return find_root(has_dir(".git"), start=Path(__file__).resolve().parent)


def find_player(query: str, deltagere: list, player_keys: list) -> tuple[str, dict] | None:
    """Return (player_key, deltagere_entry) matching query, or None."""
    q = query.strip().lower()
    for e in deltagere:
        stem = Path(e["file"]).stem
        if (e["abbr"].lower() == q
                or e["full_name"].lower() == q
                or stem.lower() == q):
            # find matching player key (case-insensitive stem match)
            for key in player_keys:
                if key.lower() == stem.lower():
                    return key, e
    return None


def main():
    args       = [a for a in sys.argv[1:] if not a.startswith("--")]
    sort_match = "--match-id" in sys.argv

    if not args:
        print("Usage: python py/review.py <abbr|full_name|file_stem> [--match-id]")
        sys.exit(1)

    query = args[0]
    root  = project_root()

    # ── Load data ─────────────────────────────────────────────────────────────
    scores_path    = root / "gData" / "scores.json"
    deltagere_path = root / "gData" / "deltagere.json"
    fasit_path     = root / "gData" / "fasit.json"

    if not scores_path.exists():
        print("scores.json not found — run score.py first.")
        sys.exit(1)

    with open(scores_path, encoding="utf-8") as f:
        scores = json.load(f)
    with open(deltagere_path, encoding="utf-8") as f:
        deltagere = json.load(f)

    fasit_medals = {}
    if fasit_path.exists():
        with open(fasit_path, encoding="utf-8") as f:
            fasit = json.load(f)
        fasit_medals = {
            "champion": fasit.get("world_champion"),
            "silver":   fasit.get("runner_up"),
            "bronze":   fasit.get("third_place"),
        }

    player_keys = list(scores["players"].keys())
    match_result = find_player(query, deltagere, player_keys)

    if match_result is None:
        print(f"No participant found matching '{query}'.")
        print("Available: " + ", ".join(e["abbr"] for e in deltagere))
        sys.exit(1)

    player_key, info = match_result
    player_data      = scores["players"][player_key]

    # ── Collect running entries ───────────────────────────────────────────────
    gs_total     = player_data["group_stage"]["points"]
    qs_total     = player_data.get("questions", {}).get("points", 0)
    ko_total     = player_data["knockout"]["points"]
    medals       = player_data.get("medals", {})
    medals_total = medals.get("points", 0)
    goals        = player_data.get("goals_progress")
    goals_total  = goals.get("points", 0) if goals else 0

    entries = []
    for r in player_data["group_stage"]["running"]:
        entries.append({
            "match":      r["match"],
            "play_order": r.get("play_order", r["match"]),
            "stage":      "Group Stage",
            "pred":       r.get("pred", "—"),
            "actual":     r.get("actual", "—"),
            "match_pts":  r.get("match_pts", 0),
            "cumulative": qs_total + r["cumulative"],
        })

    for r in player_data["knockout"]["running"]:
        mn = r.get("match") or r.get("match_id")
        entries.append({
            "match":      mn,
            "play_order": r.get("play_order", mn),
            "stage":      r.get("stage", "Knockout"),
            "pred":       r.get("pred", "—"),
            "actual":     r.get("actual", "—"),
            "match_pts":  r.get("match_pts", 0),
            "cumulative": qs_total + gs_total + r["cumulative"],
        })

    sort_key = "match" if sort_match else "play_order"
    entries.sort(key=lambda e: e[sort_key] or 0)

    # ── Print ─────────────────────────────────────────────────────────────────
    sort_label = "match id" if sort_match else "play order"
    print(f"\n{'═'*72}")
    print(f"  {info['full_name']}  ({info['abbr']})  —  sorted by {sort_label}")
    print(f"{'═'*72}")

    print("  Scoring breakdown:")
    print(f"    Qualitative questions:  {qs_total:+6d}")
    print(f"    Group stage:            {gs_total:+6d}")
    print(f"    Knockout:               {ko_total:+6d}")
    print(f"    Medals:                 {medals_total:+6d}")
    if goals is not None:
        print(f"    Goals progress:         {goals_total:+6d}"
              f"   (predicted {goals.get('predicted_cumulative_goals')}, "
              f"actual {goals.get('actual_cumulative_goals')})")
    print(f"{'─'*72}")

    # ── Qualitative questions, one row per question ─────────────────────────
    qs_detail = player_data.get("questions", {}).get("detail", {})
    if qs_detail:
        print("  Qualitative questions:")
        print(f"    {'Question':<28}  {'Predicted':>18}  {'Actual':>18}  {'Pts':>4}")
        print(f"    {'─'*28}  {'─'*18}  {'─'*18}  {'─'*4}")
        for q_id, d in qs_detail.items():
            pred   = d.get("predicted")
            actual = d.get("actual")
            pts    = 30 if d.get("correct") else 0
            mark   = "✓" if d.get("correct") else " "
            print(f"  {mark} {q_id:<28}  {str(pred):>18}  {str(actual):>18}  {pts:>4}")
        print(f"{'─'*72}")

    # ── Medal predictions vs actual ─────────────────────────────────────────
    if medals:
        print("  Medals:")
        rows = [
            ("Champion",  player_data.get("world_champion"), fasit_medals.get("champion"), medals.get("champion_pts", 0)),
            ("Runner-up", player_data.get("runner_up"),       fasit_medals.get("silver"),   medals.get("silver_pts", 0)),
            ("3rd place", player_data.get("third_place"),     fasit_medals.get("bronze"),   medals.get("bronze_pts", 0)),
        ]
        print(f"    {'Slot':<10}  {'Predicted':>18}  {'Actual':>18}  {'Pts':>4}")
        print(f"    {'─'*10}  {'─'*18}  {'─'*18}  {'─'*4}")
        for label, pred, actual, pts in rows:
            mark = "✓" if pts else " "
            print(f"  {mark} {label:<10}  {str(pred):>18}  {str(actual):>18}  {pts:>4}")
        print(f"{'─'*72}")

    print(f"  {'PO':>3}  {'M':>3}  {'Stage':<14}  {'Pred':>6}  {'Actual':>6}  {'Pts':>5}  {'Total':>6}")
    print(f"  {'─'*3}  {'─'*3}  {'─'*14}  {'─'*6}  {'─'*6}  {'─'*5}  {'─'*6}")

    for e in entries:
        pts_str = f"{e['match_pts']:+d}" if e["match_pts"] != 0 else "   —"
        print(f"  {e['play_order']:>3}  {e['match']:>3}  {e['stage']:<14}  "
              f"{e['pred']:>6}  {e['actual']:>6}  {pts_str:>5}  {e['cumulative']:>6}")

    print(f"{'─'*72}")
    total        = player_data["total"]
    max_possible = player_data.get("max_possible")
    pct_of_max   = player_data.get("pct_of_max")
    total_str = f"{total:>6}"
    if max_possible is not None:
        total_str += f"  /  {max_possible}  ({pct_of_max}%)"
    print(f"  {'Grand Total':>46}  {total_str}")
    print(f"{'═'*72}\n")


if __name__ == "__main__":
    main()
