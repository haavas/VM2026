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

    if not scores_path.exists():
        print("scores.json not found — run score.py first.")
        sys.exit(1)

    with open(scores_path, encoding="utf-8") as f:
        scores = json.load(f)
    with open(deltagere_path, encoding="utf-8") as f:
        deltagere = json.load(f)

    player_keys = list(scores["players"].keys())
    match_result = find_player(query, deltagere, player_keys)

    if match_result is None:
        print(f"No participant found matching '{query}'.")
        print("Available: " + ", ".join(e["abbr"] for e in deltagere))
        sys.exit(1)

    player_key, info = match_result
    player_data      = scores["players"][player_key]

    # ── Collect running entries ───────────────────────────────────────────────
    gs_total = player_data["group_stage"]["points"]
    qs_total = player_data.get("questions", {}).get("points", 0)

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
    if qs_total:
        print(f"  Qualitative points: {qs_total:+d}")
    print(f"  {'PO':>3}  {'M':>3}  {'Stage':<14}  {'Pred':>6}  {'Actual':>6}  {'Pts':>5}  {'Total':>6}")
    print(f"  {'─'*3}  {'─'*3}  {'─'*14}  {'─'*6}  {'─'*6}  {'─'*5}  {'─'*6}")

    for e in entries:
        pts_str = f"{e['match_pts']:+d}" if e["match_pts"] != 0 else "   —"
        print(f"  {e['play_order']:>3}  {e['match']:>3}  {e['stage']:<14}  "
              f"{e['pred']:>6}  {e['actual']:>6}  {pts_str:>5}  {e['cumulative']:>6}")

    print(f"{'─'*72}")
    total = entries[-1]["cumulative"] if entries else qs_total
    print(f"  {'Total':>46}  {total:>6}")
    print(f"{'═'*72}\n")


if __name__ == "__main__":
    main()
