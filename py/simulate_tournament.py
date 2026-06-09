"""
simulate_tournament.py
----------------------
Runs the World Cup 2026 simulation N times and aggregates probabilities.

Usage:
    python simulate_tournament.py [n_simulations] [output_name]

Defaults:
    n_simulations = 10000
    output_name   = "simulations"

Output:
    gData/simulations.json

Output structure:
{
  "n_simulations": 10000,
  "champion": {"France": 0.142, "Argentina": 0.138, ...},
  "finalist": {"France": 0.241, ...},
  "semi_finalist": {...},
  "quarter_finalist": {...},
  "round_of_16": {...},
  "round_of_32": {...},
  "group_advance": {...},        // % reaching R32 (top 2 + best 3rd)
  "group_winner": {...},         // % finishing 1st in group
  "group_tables": {              // average pts/gd/gf per team
      "A": [{"team": ..., "avg_pts": ..., "avg_gd": ..., "avg_gf": ...}, ...]
  }
}
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root

HERE = find_root(has_dir(".git"), start=Path(__file__).resolve().parent)
sys.path.insert(0, str(HERE / "py"))

from generate_predictions import simulate, GROUPS


def run(n=10000, output_name="simulations"):
    # Counters
    champion        = defaultdict(int)
    finalist        = defaultdict(int)
    semi_finalist   = defaultdict(int)
    quarter_finalist= defaultdict(int)
    round_of_16     = defaultdict(int)
    round_of_32     = defaultdict(int)
    group_advance   = defaultdict(int)   # reached R32 (top-2 or best 3rd)
    group_winner    = defaultdict(int)   # finished 1st in group

    # For group table averages
    pts_sum = defaultdict(float)
    gd_sum  = defaultdict(float)
    gf_sum  = defaultdict(float)

    # Goal distributions per match
    goals_dist = defaultdict(list)  # match_num → list of total goals (one per sim)

    print(f"Running {n:,} simulations...", flush=True)

    for seed in range(n):
        if seed % 1000 == 0:
            print(f"  {seed:>6,} / {n:,}", flush=True)

        matches, champ, tables = simulate(seed)

        # Champion & path through knockout rounds
        ko = {m["match"]: m for m in matches if "team1" in m}

        champion[champ] += 1

        # Record goals per match
        for m in matches:
            if "home_goals" in m:
                goals_dist[m["match"]].append(m["home_goals"] + m["away_goals"])
            else:
                goals_dist[m["match"]].append(m["team1_goals"] + m["team2_goals"])

        # Final (M104)
        if 104 in ko:
            for t in (ko[104]["team1"], ko[104]["team2"]):
                finalist[t] += 1

        # Semi-finals (M101, M102)
        for mn in (101, 102):
            if mn in ko:
                for t in (ko[mn]["team1"], ko[mn]["team2"]):
                    semi_finalist[t] += 1

        # Quarter-finals (M97-M100)
        for mn in range(97, 101):
            if mn in ko:
                for t in (ko[mn]["team1"], ko[mn]["team2"]):
                    quarter_finalist[t] += 1

        # Round of 16 (M89-M96)
        for mn in range(89, 97):
            if mn in ko:
                for t in (ko[mn]["team1"], ko[mn]["team2"]):
                    round_of_16[t] += 1

        # Round of 32 (M73-M88) — all 32 participants = group advancers
        for mn in range(73, 89):
            if mn in ko:
                for t in (ko[mn]["team1"], ko[mn]["team2"]):
                    round_of_32[t] += 1
                    group_advance[t] += 1

        # Group stage stats
        for gid, rows in tables.items():
            group_winner[rows[0]["team"]] += 1
            for row in rows:
                pts_sum[row["team"]] += row["pts"]
                gd_sum[row["team"]]  += row["gd"]
                gf_sum[row["team"]]  += row["gf"]

    def to_pct(counter):
        return dict(sorted(
            {t: round(v / n, 4) for t, v in counter.items()}.items(),
            key=lambda x: -x[1]
        ))

    # Average group table per group
    all_teams = {t for teams in GROUPS.values() for t in teams}
    avg_group_tables = {}
    for gid, teams in GROUPS.items():
        avg_group_tables[gid] = sorted([
            {
                "team":     t,
                "avg_pts":  round(pts_sum[t] / n, 3),
                "avg_gd":   round(gd_sum[t]  / n, 3),
                "avg_gf":   round(gf_sum[t]  / n, 3),
            }
            for t in teams
        ], key=lambda x: -x["avg_pts"])

    # Goals per match — average and full distribution
    match_goals = {
        mn: {
            "avg":  round(sum(goals_dist[mn]) / n, 3),
            "dist": sorted(set(goals_dist[mn])),
            "freq": {
                str(g): round(goals_dist[mn].count(g) / n, 4)
                for g in sorted(set(goals_dist[mn]))
            },
        }
        for mn in sorted(goals_dist)
    }
    grand_total_avg = round(sum(v["avg"] for v in match_goals.values()), 3)

    all_teams = sorted({t for teams in GROUPS.values() for t in teams})
    team_stats = {
        t: {
            "group":            next(g for g, ts in GROUPS.items() if t in ts),
            "group_winner":     round(group_winner[t]    / n, 4),
            "group_advance":    round(group_advance[t]   / n, 4),
            "round_of_32":      round(round_of_32[t]     / n, 4),
            "round_of_16":      round(round_of_16[t]     / n, 4),
            "quarter_finalist": round(quarter_finalist[t]/ n, 4),
            "semi_finalist":    round(semi_finalist[t]   / n, 4),
            "finalist":         round(finalist[t]        / n, 4),
            "champion":         round(champion[t]        / n, 4),
        }
        for t in all_teams
    }
    # Sort by champion probability descending
    team_stats = dict(sorted(team_stats.items(), key=lambda x: -x[1]["champion"]))

    output = {
        "n_simulations":    n,
        "team_stats":       team_stats,
        "champion":         to_pct(champion),
        "finalist":         to_pct(finalist),
        "semi_finalist":    to_pct(semi_finalist),
        "quarter_finalist": to_pct(quarter_finalist),
        "round_of_16":      to_pct(round_of_16),
        "round_of_32":      to_pct(round_of_32),
        "group_advance":    to_pct(group_advance),
        "group_winner":     to_pct(group_winner),
        "group_tables":     avg_group_tables,
        "match_goals":      match_goals,
        "grand_total_goals_avg": grand_total_avg,
    }

    out_path = HERE / "gData" / f"{output_name}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\n{'─'*100}")
    print(f"Results from {n:,} simulations")
    print(f"{'─'*100}")
    header = f"  {'Team':<25} {'Grp':>3}  {'GrpW':>5} {'R32':>5} {'R16':>5} {'QF':>5} {'SF':>5} {'Final':>6} {'Win':>6}"
    print(f"\n{header}")
    print(f"  {'─'*25} {'─'*3}  {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*6} {'─'*6}")
    for team, s in output["team_stats"].items():
        print(
            f"  {team:<25} {s['group']:>3}  "
            f"{s['group_winner']*100:5.1f} "
            f"{s['round_of_32']*100:5.1f} "
            f"{s['round_of_16']*100:5.1f} "
            f"{s['quarter_finalist']*100:5.1f} "
            f"{s['semi_finalist']*100:5.1f} "
            f"{s['finalist']*100:6.1f} "
            f"{s['champion']*100:6.1f}"
        )

    print(f"\n⚽ Average goals per match:")
    stage_ranges = [
        ("Group Stage",       range(1,   73)),
        ("Round of 32",       range(73,  89)),
        ("Round of 16",       range(89,  97)),
        ("Quarterfinals",     range(97,  101)),
        ("Semi-Finals",       range(101, 103)),
        ("3rd Place / Final", range(103, 105)),
    ]
    for stage, r in stage_ranges:
        sg = [match_goals[mn]["avg"] for mn in r if mn in match_goals]
        if sg:
            print(f"  {stage:<22}  avg/game: {sum(sg)/len(sg):5.2f}   stage total: {sum(sg):7.2f}")
    print(f"  {'─'*55}")
    print(f"  {'Grand total (avg over all sims)':<22}  {grand_total_avg:>13.2f} goals")
    print(f"\nSaved → {out_path}")
    return output


if __name__ == "__main__":
    n            = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    output_name  = sys.argv[2]      if len(sys.argv) > 2 else "simulations"
    run(n, output_name)
