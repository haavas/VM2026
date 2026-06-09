"""
generate_predictions.py
-----------------------
Generates realistic predictions for all 104 World Cup 2026 matches
and writes them to gData/generated_<player_name>.json.

Usage:
    python generate_predictions.py [seed] [player_name]
"""

import json
import random
import sys
from pathlib import Path

from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root

HERE = find_root(has_dir(".git"), start=Path(__file__).resolve().parent)

# ---------------------------------------------------------------------------
# FIFA points — April 1, 2026
# ---------------------------------------------------------------------------
FIFA_POINTS = {
    "France":                 1877.32,
    "Spain":                  1876.40,
    "Argentina":              1874.81,
    "England":                1825.97,
    "Portugal":               1763.83,
    "Brazil":                 1761.16,
    "Netherlands":            1757.87,
    "Morocco":                1755.87,
    "Belgium":                1734.71,
    "Germany":                1730.37,
    "Croatia":                1717.07,
    "Colombia":               1693.09,
    "Senegal":                1688.99,
    "Mexico":                 1681.03,
    "United States":          1673.13,
    "Uruguay":                1673.07,
    "Japan":                  1660.43,
    "Switzerland":            1649.40,
    "Iran":                   1615.00,
    "Turkey":                 1599.00,
    "Ecuador":                1594.00,
    "Austria":                1593.00,
    "Korea Republic":         1588.00,
    "Australia":              1580.00,
    "Algeria":                1564.00,
    "Egypt":                  1563.00,
    "Canada":                 1556.00,
    "Norway":                 1550.00,
    "Panama":                 1540.00,
    "Ivory Coast":            1532.00,
    "Sweden":                 1510.00,
    "Paraguay":               1502.00,
    "Czech Republic":         1498.00,
    "Scotland":               1488.00,
    "Tunisia":                1484.00,
    "DR Congo":               1472.00,
    "Uzbekistan":             1451.00,
    "Qatar":                  1422.00,
    "Iraq":                   1415.00,
    "South Africa":           1401.00,
    "Saudi Arabia":           1397.00,
    "Jordan":                 1389.00,
    "Bosnia and Herzegovina": 1381.00,
    "Cape Verde":             1362.00,
    "Ghana":                  1340.00,
    "Curaçao":                1298.00,
    "Haiti":                  1294.00,
    "New Zealand":            1286.00,
}

_MAX = max(FIFA_POINTS.values())
_MIN = min(FIFA_POINTS.values())

def strength(team):
    return (FIFA_POINTS.get(team, (_MAX+_MIN)/2) - _MIN) / (_MAX - _MIN)

def goals(s, rng):
    return max(0, round(rng.gauss(0.5 + s * 1.4, 0.9)))

def predict(t1, t2, rng, knockout=False):
    g1 = goals(strength(t1) * (1.08 if not knockout else 1.0), rng)
    g2 = goals(strength(t2), rng)
    if knockout and g1 == g2:
        if strength(t1) >= strength(t2): g1 += 1
        else: g2 += 1
    return g1, g2

# ---------------------------------------------------------------------------
# Tournament structure
# ---------------------------------------------------------------------------
GROUPS = {
    "A": ["Mexico",       "South Africa", "Korea Republic",         "Czech Republic"],
    "B": ["Canada",       "Bosnia and Herzegovina", "Qatar",         "Switzerland"],
    "C": ["Haiti",        "Scotland",     "Brazil",                  "Morocco"],
    "D": ["United States","Paraguay",     "Australia",               "Turkey"],
    "E": ["Ivory Coast",  "Ecuador",      "Germany",                 "Curaçao"],
    "F": ["Netherlands",  "Japan",        "Sweden",                  "Tunisia"],
    "G": ["Iran",         "New Zealand",  "Belgium",                 "Egypt"],
    "H": ["Saudi Arabia", "Uruguay",      "Spain",                   "Cape Verde"],
    "I": ["France",       "Senegal",      "Iraq",                    "Norway"],
    "J": ["Argentina",    "Algeria",      "Austria",                 "Jordan"],
    "K": ["Ghana",        "Panama",       "England",                 "Croatia"],
    "L": ["Portugal",     "DR Congo",     "Uzbekistan",              "Colombia"],
}

# Per-group schedules derived from the actual fixture list in the template.
# Each tuple is (home_team_index, away_team_index) within the group's team list.
GROUP_SCHEDULES = {
    "A": [(0,1),(2,3),(3,1),(0,2),(3,0),(1,2)],
    "B": [(0,1),(2,3),(3,1),(0,2),(3,0),(1,2)],
    "C": [(0,1),(2,3),(2,0),(1,3),(1,2),(3,0)],
    "D": [(0,1),(2,3),(0,2),(3,1),(3,0),(1,2)],
    "E": [(0,1),(2,3),(2,0),(1,3),(3,0),(1,2)],
    "F": [(0,1),(2,3),(0,2),(3,1),(1,2),(3,0)],
    "G": [(0,1),(2,3),(2,0),(1,3),(3,0),(1,2)],
    "H": [(0,1),(2,3),(1,3),(2,0),(3,0),(1,2)],
    "I": [(0,1),(2,3),(3,1),(0,2),(3,0),(1,2)],
    "J": [(0,1),(2,3),(0,2),(3,1),(1,2),(3,0)],
    "K": [(0,1),(2,3),(2,0),(1,3),(1,2),(3,0)],
    "L": [(0,1),(2,3),(0,2),(3,1),(3,0),(1,2)],
}
MATCH_NUMS = {
    "A":[1,2,25,28,53,54], "B":[3,8,26,27,51,52], "C":[5,7,29,30,49,50],
    "D":[4,6,31,32,59,60], "E":[9,10,33,34,55,56],"F":[11,12,35,36,57,58],
    "G":[15,16,39,40,63,64],"H":[13,14,37,38,65,66],"I":[17,18,41,42,61,62],
    "J":[19,20,43,44,69,70],"K":[21,22,45,46,67,68],"L":[23,24,47,48,71,72],
}

R32 = {
    73:("2A","2B"), 74:("1E","3ABCDF"), 75:("1F","2C"), 76:("1C","2F"),
    77:("1I","3CDFGH"), 78:("2E","2I"), 79:("1A","3CEFHI"), 80:("1L","3EHIJK"),
    81:("1D","3BEFIJ"), 82:("1G","3AEHIJ"), 83:("2K","2L"), 84:("1H","2J"),
    85:("1B","3EFGIJ"), 86:("1J","2H"), 87:("1K","3DEIJL"), 88:("2D","2G"),
}
R16 = {89:(74,77),90:(73,75),91:(76,78),92:(79,80),93:(83,84),94:(81,82),95:(86,88),96:(85,87)}
QF  = {97:(89,90),98:(93,94),99:(91,92),100:(95,96)}
SF  = {101:(97,98),102:(99,100)}


def simulate(seed=42):
    rng = random.Random(seed)
    matches = []   # final output list, match objects in match-number order

    # --- Group stage ---
    standings = {}   # group → [1st,2nd,3rd,4th]
    third_stats = {} # group → {pts,gd,gf,team}
    group_tables = {} # group → list of {pos,team,pts,gf,ga,gd}

    for gid, teams in GROUPS.items():
        stats = {t: {"pts":0,"w":0,"d":0,"l":0,"gf":0,"ga":0} for t in teams}
        for i, (hi,ai) in enumerate(GROUP_SCHEDULES[gid]):
            h, a = teams[hi], teams[ai]
            hg, ag = predict(h, a, rng)
            mn = MATCH_NUMS[gid][i]
            result = "home" if hg>ag else "away" if ag>hg else "draw"
            matches.append({"match":mn,"stage":"Group Stage","group":gid,
                            "home":h,"away":a,"home_goals":hg,"away_goals":ag,"result":result})
            if hg>ag:
                stats[h]["pts"]+=3; stats[h]["w"]+=1; stats[a]["l"]+=1
            elif ag>hg:
                stats[a]["pts"]+=3; stats[a]["w"]+=1; stats[h]["l"]+=1
            else:
                stats[h]["pts"]+=1; stats[h]["d"]+=1
                stats[a]["pts"]+=1; stats[a]["d"]+=1
            stats[h]["gf"]+=hg; stats[h]["ga"]+=ag
            stats[a]["gf"]+=ag; stats[a]["ga"]+=hg

        ranked = sorted(teams, key=lambda t: (
            -stats[t]["pts"], -(stats[t]["gf"]-stats[t]["ga"]),
            -stats[t]["gf"], -FIFA_POINTS.get(t,1300)))
        standings[gid] = ranked
        s = stats[ranked[2]]
        third_stats[gid] = {"team":ranked[2],"pts":s["pts"],
                             "gd":s["gf"]-s["ga"],"gf":s["gf"]}
        group_tables[gid] = [
            {"pos": i+1, "team": t,
             "pts": stats[t]["pts"], "w": stats[t]["w"],
             "d": stats[t]["d"],     "l": stats[t]["l"],
             "gf": stats[t]["gf"],   "ga": stats[t]["ga"],
             "gd": stats[t]["gf"]-stats[t]["ga"]}
            for i, t in enumerate(ranked)
        ]

    # --- Rank 3rd-place teams ---
    thirds_ranked = sorted(third_stats.keys(),
        key=lambda g: (-third_stats[g]["pts"],-third_stats[g]["gd"],
                       -third_stats[g]["gf"],-FIFA_POINTS.get(third_stats[g]["team"],1300)))

    # --- Assign 3rd-place teams to R32 slots (each team used exactly once) ---
    # FIFA's Annex C defines the exact mapping for all 495 group combinations.
    # We approximate it with a constraint-satisfaction approach: sort slots by
    # fewest eligible qualifying groups (most constrained first), then assign
    # greedily. If a slot has no eligible group remaining (can happen with
    # certain seeds), fall back to the best unassigned qualifying group.
    THIRD_SLOTS = {
        74: set("ABCDF"), 77: set("CDFGH"), 79: set("CEFHI"), 80: set("EHIJK"),
        81: set("BEFIJ"), 82: set("AEHIJ"), 85: set("EFGIJ"), 87: set("DEIJL"),
    }
    qualifying_groups = set(thirds_ranked[:8])
    third_assignment = {}  # match_num → team
    assigned_groups  = set()

    for mn in sorted(THIRD_SLOTS, key=lambda m: len(THIRD_SLOTS[m] & qualifying_groups)):
        eligible = (THIRD_SLOTS[mn] & qualifying_groups) - assigned_groups
        # Fall back to any remaining unassigned qualifying group if no eligible match
        if not eligible:
            eligible = qualifying_groups - assigned_groups
        best_group = next(g for g in thirds_ranked if g in eligible)
        third_assignment[mn] = third_stats[best_group]["team"]
        assigned_groups.add(best_group)

    def resolve_fixed(slot, mn=None):
        """Resolve a bracket slot to a team name.
        Regular slots: '1A', '2B' etc. (digit + single letter)
        3rd-place slots: '3ABCDF' etc. (digit + multiple letters)
        """
        if slot[0].isdigit() and len(slot) == 2:
            return standings[slot[1]][int(slot[0])-1]
        return third_assignment[mn]

    # --- Knockout stages ---
    winner = {}
    loser  = {}

    def ko(mn, t1, t2, stage):
        g1, g2 = predict(t1, t2, rng, knockout=True)
        res = "team1" if g1>g2 else "team2"
        matches.append({"match":mn,"stage":stage,
                        "team1":t1,"team2":t2,"team1_goals":g1,"team2_goals":g2,"result":res})
        winner[mn] = t1 if g1>g2 else t2
        loser[mn]  = t2 if g1>g2 else t1

    for mn, (s1,s2) in sorted(R32.items()):
        ko(mn, resolve_fixed(s1, mn), resolve_fixed(s2, mn), "Round of 32")
    for mn,(m1,m2) in sorted(R16.items()):
        ko(mn, winner[m1], winner[m2], "Round of 16")
    for mn,(m1,m2) in sorted(QF.items()):
        ko(mn, winner[m1], winner[m2], "Quarterfinals")
    for mn,(m1,m2) in sorted(SF.items()):
        ko(mn, winner[m1], winner[m2], "Semi-Finals")
    ko(103, loser[101],  loser[102],  "Third-Place Play-Off")
    ko(104, winner[101], winner[102], "Final")

    matches.sort(key=lambda m: m["match"])
    return matches, winner[104], group_tables


def generate(seed=42, player_name="generated"):
    matches, champion, group_tables = simulate(seed)

    out_dir = HERE / "gData"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"generated_{player_name}.json"

    output = {
        "player":         player_name,
        "seed":           seed,
        "world_champion": champion,
        "group_tables":   group_tables,
        "group_stage":    [m for m in matches if m["stage"]=="Group Stage"],
        "knockout":       [m for m in matches if m["stage"]!="Group Stage"],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print summary
    stage_order = ["Group Stage","Round of 32","Round of 16",
                   "Quarterfinals","Semi-Finals","Third-Place Play-Off","Final"]
    current_stage = None
    group_printed = False
    for m in matches:
        if m["stage"] != current_stage:
            # Print group tables when leaving the group stage
            if current_stage == "Group Stage" and not group_printed:
                print("\n── Group Tables ──")
                for gid in "ABCDEFGHIJKL":
                    print(f"\n  Group {gid}")
                    print(f"  {'Team':<25} {'Pts':>3} {'W':>2} {'D':>2} {'L':>2} {'GF':>3} {'GA':>3} {'GD':>4}")
                    print(f"  {'─'*25} {'─'*3} {'─'*2} {'─'*2} {'─'*2} {'─'*3} {'─'*3} {'─'*4}")
                    for row in group_tables[gid]:
                        print(f"  {row['team']:<25} {row['pts']:>3} {row['w']:>2} {row['d']:>2} {row['l']:>2} {row['gf']:>3} {row['ga']:>3} {row['gd']:>4}")
                group_printed = True
            current_stage = m["stage"]
            print(f"\n── {current_stage} ──")
        if "home" in m:
            print(f"  M{m['match']:>3}  {m['home']:<25} {m['home_goals']}-{m['away_goals']}  {m['away']}")
        else:
            print(f"  M{m['match']:>3}  {m['team1']:<25} {m['team1_goals']}-{m['team2_goals']}  {m['team2']}")

    print(f"\n🏆 Champion: {champion}")
    print(f"\nSaved → {out_path}")
    return output


if __name__ == "__main__":
    seed        = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    player_name = sys.argv[2]      if len(sys.argv) > 2 else "generated"
    generate(seed, player_name)
