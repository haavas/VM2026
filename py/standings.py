# -*- coding: utf-8 -*-
"""
standings.py
------------
Reads gData/scores.json and produces a long-format CSV with each player's
cumulative score after every match played, plus their rank and rank change
at each snapshot.

Output
------
gData/standings.csv  — long format, one row per (player, match)

Columns
-------
match        : match number (1-104)
stage        : Group Stage / Round of 32 / Round of 16 / ...
player       : player name
cumulative   : total points after this match
rank         : rank at this match (1 = leading)
rank_prev    : rank after the previous match
rank_change  : rank_prev - rank  (positive = moved up)
match_pts    : points earned in this specific match

Usage
-----
python py/standings.py                  # uses project defaults
python py/standings.py scores.json      # explicit scores path
"""

import csv
import json
import sys
from pathlib import Path

from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root


def project_root() -> Path:
    return find_root(has_dir(".git"), start=Path(__file__).resolve().parent)


def load_name_lookup(root: Path) -> dict:
    """Load deltagere.json and return {file_stem: full_name}."""
    path = root / "gData" / "deltagere.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    return {
        Path(e["file"]).stem: e["full_name"]
        for e in entries
    }


def build_standings(scores_path: str = None,
                    output_csv:  str = None) -> None:

    root = project_root()
    scores_path = Path(scores_path) if scores_path else root / "gData" / "scores.json"
    output_csv  = Path(output_csv)  if output_csv  else root / "gData" / "standings.csv"

    if not scores_path.exists():
        raise FileNotFoundError(
            f"Scores file not found: {scores_path}\n"
            "Run score.py first."
        )

    with open(scores_path, encoding="utf-8") as f:
        data = json.load(f)

    name_lookup = load_name_lookup(root)

    players = data["players"]

    # ── Build per-player timeline ────────────────────────────────────────────
    # Combine group stage and knockout running lists into one sorted timeline.
    # Knockout cumulative is relative to 0; add group stage total to offset it.

    timelines = {}   # player → sorted list of {match, stage, cumulative, match_pts}

    for player, s in players.items():
        gs_total = s["group_stage"]["points"]

        events = []

        for r in s["group_stage"]["running"]:
            events.append({
                "match":      r["match"],
                "play_order": r.get("play_order", r["match"]),
                "stage":      "Group Stage",
                "cumulative": r["cumulative"],
                "match_pts":  r.get("match_pts", 0),
            })

        for r in s["knockout"]["running"]:
            events.append({
                "match":      r.get("match") or r.get("match_id"),
                "play_order": r.get("play_order", r.get("match") or r.get("match_id")),
                "stage":      r.get("stage", "Knockout"),
                "cumulative": gs_total + r["cumulative"],
                "match_pts":  r.get("match_pts", 0),
            })

        timelines[player] = sorted(events, key=lambda e: e["play_order"] or 0)

    # ── Collect all match numbers in play order ──────────────────────────────
    # Use play_order for sequencing so out-of-number-order games (e.g. M8
    # played before M5) are processed and lagged correctly.
    seen = {}
    for events in timelines.values():
        for e in events:
            mn = e["match"]
            if mn is not None and mn not in seen:
                seen[mn] = e["play_order"] or mn
    all_matches = [mn for mn, _ in sorted(seen.items(), key=lambda x: x[1])]

    if not all_matches:
        print("No matches found in scores.json — nothing to write.")
        return

    # ── Build standings snapshot after each match ────────────────────────────
    # For each match, carry forward each player's last known cumulative score.

    player_list = sorted(players.keys())

    # Last known cumulative for each player (starts at 0)
    current = {p: 0 for p in player_list}
    prev_rank = {p: None for p in player_list}

    rows = []

    # Index timelines by match number for fast lookup
    by_match = {p: {e["match"]: e for e in events}
                for p, events in timelines.items()}

    for mn in all_matches:
        # Update current scores for players who have an event this match
        match_stage      = "Unknown"
        match_pts_this   = {p: 0 for p in player_list}
        play_order_at_mn = mn

        for p in player_list:
            e = by_match[p].get(mn)
            if e:
                current[p]        = e["cumulative"]
                match_pts_this[p] = e["match_pts"]
                match_stage       = e["stage"]
                play_order_at_mn  = e.get("play_order", mn)

        # Rank players — higher score = better rank; ties share the lower rank number
        sorted_players = sorted(player_list, key=lambda p: -current[p])
        rank_at = {}
        for i, p in enumerate(sorted_players):
            # Tied players get the same rank
            if i > 0 and current[p] == current[sorted_players[i-1]]:
                rank_at[p] = rank_at[sorted_players[i-1]]
            else:
                rank_at[p] = i + 1

        for p in player_list:
            pr = prev_rank[p]
            rk = rank_at[p]
            rows.append({
                "match":       mn,
                "play_order":  play_order_at_mn,
                "stage":       match_stage,
                "player":      p,
                "full_name":   name_lookup.get(p, p),
                "cumulative":  current[p],
                "match_pts":   match_pts_this[p],
                "rank":        rk,
                "rank_prev":   pr if pr is not None else rk,
                "rank_change": (pr - rk) if pr is not None else 0,
            })

        prev_rank = dict(rank_at)

    # ── Write CSV ────────────────────────────────────────────────────────────
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "match", "play_order", "stage", "player", "full_name", "cumulative",
            "match_pts", "rank", "rank_prev", "rank_change",
        ], delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

    n_matches  = len(all_matches)
    n_players  = len(player_list)
    print(f"Standings across {n_matches} matches × {n_players} players "
          f"→ {len(rows)} rows")
    print(f"Wrote → {output_csv}")

    # ── Print current standings ───────────────────────────────────────────────
    last_match = max(all_matches)
    last_rows  = [r for r in rows if r["match"] == last_match]
    last_rows.sort(key=lambda r: r["rank"])

    print(f"\nCurrent standings after M{last_match} ({last_rows[0]['stage']}):")
    print(f"  {'Rank':>4}  {'Name':<30} {'Score':>6}  {'Change':>7}")
    print(f"  {'─'*4}  {'─'*30} {'─'*6}  {'─'*7}")
    for r in last_rows:
        chg = r["rank_change"]
        chg_str = f"({'↑' if chg > 0 else '↓' if chg < 0 else '─'}{abs(chg)})"
        print(f"  {r['rank']:>4}  {r['full_name']:<30} {r['cumulative']:>6}  {chg_str:>7}")


if __name__ == "__main__":
    scores_arg = sys.argv[1] if len(sys.argv) > 1 else None
    output_arg = sys.argv[2] if len(sys.argv) > 2 else None
    build_standings(scores_arg, output_arg)
