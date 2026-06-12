"""
show_match.py
-------------
Lists every participant's prediction for a given group stage match,
sorted from largest home win to largest away win.

Usage:
    python py/show_match.py 4
"""

import sys
import json
from pathlib import Path
from pyprojroot import find_root, has_dir


def project_root() -> Path:
    return find_root(has_dir(".git"), start=Path(__file__).resolve().parent)


def main():
    if len(sys.argv) < 2:
        print("Usage: python show_match.py <match_number>")
        sys.exit(1)

    match_no = int(sys.argv[1])
    root = project_root()

    preds_path     = root / "gData" / "predictions.json"
    deltagere_path = root / "gData" / "deltagere.json"

    with open(preds_path,     encoding="utf-8") as f:
        preds = json.load(f)
    with open(deltagere_path, encoding="utf-8") as f:
        deltagere = json.load(f)

    # Build file-stem → abbr + full_name lookup
    label = {
        Path(e["file"]).stem: (e["abbr"], e["full_name"])
        for e in deltagere
    }

    rows = []
    home_team = away_team = None

    for player_key, player in preds["players"].items():
        for m in player["group_stage"]:
            if m["match_id"] != match_no:
                continue

            home_team = m["home"]
            away_team = m["away"]
            hg = m["home_goals"]
            ag = m["away_goals"]

            if hg is None or ag is None:
                continue

            abbr, full_name = label.get(player_key, (player_key, player_key))
            rows.append({
                "abbr":      abbr,
                "full_name": full_name,
                "home_g":    int(hg),
                "away_g":    int(ag),
                "diff":      int(hg) - int(ag),
            })
            break   # found this match for this player

    if not rows:
        print(f"No predictions found for match {match_no}.")
        sys.exit(1)

    # Sort: largest home win first (diff desc), then by home goals desc as tiebreak
    rows.sort(key=lambda r: (-r["diff"], -r["home_g"]))

    # Print
    col_w = max(len(r["full_name"]) for r in rows)
    header = (
        f"  {'Name':<{col_w}}  {'Abbr':>6}  "
        f"{'':>4}{home_team:^5}  {away_team:^5}"
    )
    print(f"\nMatch {match_no}: {home_team} vs {away_team}")
    print("-" * len(header))
    print(header)
    print("-" * len(header))

    prev_diff = None
    for r in rows:
        if prev_diff is not None and r["diff"] != prev_diff:
            print()   # blank line between outcome groups
        result = f"{r['home_g']} - {r['away_g']}"
        print(f"  {r['full_name']:<{col_w}}  {r['abbr']:>6}  {result:>9}")
        prev_diff = r["diff"]

    print("-" * len(header))
    print(f"  {len(rows)} predictions\n")


if __name__ == "__main__":
    main()
