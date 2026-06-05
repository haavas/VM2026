"""
scan_predictions.py
-------------------
Scans all .xlsx files in the 'xlsx/' folder (relative to this script, or
overridden via CLI) and builds a single JSON file with every player's
predictions for all 104 World Cup 2026 matches.

Usage:
    python scan_predictions.py [xlsx_dir] [output_json]

Defaults:
    xlsx_dir    = xlsx/
    output_json = predictions.json

Output structure
----------------
{
  "players": {
    "alice": {
      "group_stage": [
        {
          "match": 1,
          "stage": "Group Stage",
          "group": "Group A",
          "date": "Jun 11, 2026",
          "time": "19:00:00",
          "home": "Mexico",
          "away": "South Africa",
          "home_goals": 2,
          "away_goals": 1,
          "result": "home"        // "home" | "away" | "draw" | null
        }, ...
      ],
      "knockout": [
        {
          "match": 73,
          "stage": "Round of 32",
          "date": "Jun 28, 2026   19:00",
          "team1": "2A",          // placeholder until group stage resolved
          "team2": "2B",
          "team1_goals": 1,
          "team2_goals": 2,
          "result": "team2"       // "team1" | "team2" | "draw_aet" | null
        }, ...
      ],
      "world_champion": "Brazil"  // or null if not filled in
    },
    "bob": { ... }
  },
  "meta": {
    "xlsx_dir": "xlsx/",
    "files_scanned": ["alice.xlsx", "bob.xlsx"],
    "total_players": 2
  }
}

Column reference (sheet: '2026 World Cup', header=None, 0-indexed)
------------------------------------------------------------------
Group stage (matches 1-72):
  col 0 : match number
  col 4 : home team
  col 5 : home goals  ← PREDICTION
  col 6 : away goals  ← PREDICTION
  col 7 : away team

Knockout (matches 73-104), 2-row pattern per game:
  date_row  → col X       : date+time string
  team1_row → col X       : match number
              col X+1     : team 1 name
              col X+2     : team 1 goals  ← PREDICTION
  team2_row → col X+1     : team 2 name
              col X+2     : team 2 goals  ← PREDICTION

  Stage            match_col (X)
  Round of 32      62
  Round of 16      69
  Quarterfinals    76
  Semi-Finals      83
  3rd-place/Final  90

World champion: row 67, col 88
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd
from pyprojroot.criterion import has_dir, has_file
from pyprojroot.root import find_root

# Walk up from the script's own location to find the project root.
# Recognises .git, pyproject.toml, or setup.py — mirrors R's here::here().
_ROOT_CRITERION = has_dir(".git")
HERE = find_root(_ROOT_CRITERION, start=Path(__file__).resolve().parent)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe(val):
    """Convert NaN / numpy scalars to plain Python types, return None for NaN."""
    if val is None:
        return None
    try:
        if math.isnan(float(val)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, float) and val == int(val):
        return int(val)
    return val


def _goals(val):
    v = _safe(val)
    return int(v) if v is not None else None


# ---------------------------------------------------------------------------
# Extraction helpers (identical logic to extract_wc2026.py)
# ---------------------------------------------------------------------------

KNOCKOUT_STAGES = [
    ("Round of 32",           62, range(73,  89)),
    ("Round of 16",           69, range(89,  97)),
    ("Quarterfinals",         76, range(97, 101)),
    ("Semi-Finals",           83, range(101, 103)),
    ("Third-Place Play-Off",  90, [103]),
    ("Final",                 90, [104]),
]


def _build_group_lookup(df):
    """Return {team_name: 'Group X'} by reading the standings area (col 9, 30)."""
    lookup = {}
    for idx in range(6, df.shape[0]):
        grp_val = df.iloc[idx, 9]
        if isinstance(grp_val, str) and grp_val.startswith("Group "):
            for offset in range(1, 5):
                r = idx + offset
                if r < df.shape[0]:
                    t = df.iloc[r, 30]
                    if pd.notna(t):
                        lookup[str(t)] = grp_val
    return lookup


def extract_group_stage(df, group_lookup):
    matches = []
    for idx in range(6, df.shape[0]):
        raw = _safe(df.iloc[idx, 0])
        if raw is None or not isinstance(raw, int) or not (1 <= raw <= 72):
            continue
        home      = str(df.iloc[idx, 4]) if pd.notna(df.iloc[idx, 4]) else None
        away      = str(df.iloc[idx, 7]) if pd.notna(df.iloc[idx, 7]) else None
        home_g    = _goals(df.iloc[idx, 5])
        away_g    = _goals(df.iloc[idx, 6])

        result = None
        if home_g is not None and away_g is not None:
            result = "home" if home_g > away_g else ("away" if away_g > home_g else "draw")

        matches.append({
            "match":      raw,
            "stage":      "Group Stage",
            "group":      group_lookup.get(home) or group_lookup.get(away),
            "home":       home,
            "away":       away,
            "home_goals": home_g,
            "away_goals": away_g,
            "result":     result,
        })
    return matches


def extract_knockout(df):
    # Collect team1_row for each match number
    matches_by_num = {}
    for stage_label, match_col, match_range in KNOCKOUT_STAGES:
        for idx in range(6, df.shape[0]):
            raw = _safe(df.iloc[idx, match_col])
            if isinstance(raw, int) and raw in match_range:
                matches_by_num[raw] = (idx, stage_label, match_col)

    matches = []
    for match_num, (team1_row, stage_label, mc) in sorted(matches_by_num.items()):
        team2_row   = team1_row + 1
        team1       = str(df.iloc[team1_row, mc + 1]) if pd.notna(df.iloc[team1_row, mc + 1]) else None
        team1_goals = _goals(df.iloc[team1_row, mc + 2])
        team2       = str(df.iloc[team2_row, mc + 1]) if pd.notna(df.iloc[team2_row, mc + 1]) else None
        team2_goals = _goals(df.iloc[team2_row, mc + 2])

        result = None
        if team1_goals is not None and team2_goals is not None:
            result = ("team1" if team1_goals > team2_goals
                      else "team2" if team2_goals > team1_goals
                      else "draw_aet")

        matches.append({
            "match":       match_num,
            "stage":       stage_label,
            "team1":       team1,
            "team2":       team2,
            "team1_goals": team1_goals,
            "team2_goals": team2_goals,
            "result":      result,
        })
    return matches


def extract_champion(df):
    val = df.iloc[67, 88]
    return str(val) if pd.notna(val) else None


# ---------------------------------------------------------------------------
# Per-file extraction
# ---------------------------------------------------------------------------

def extract_player(xlsx_path: Path) -> dict:
    """Read one player's xlsx and return their full prediction dict."""
    df = pd.read_excel(xlsx_path, sheet_name="2026 World Cup", header=None)
    group_lookup = _build_group_lookup(df)
    return {
        "group_stage":     extract_group_stage(df, group_lookup),
        "knockout":        extract_knockout(df),
        "world_champion":  extract_champion(df),
    }


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

def scan(xlsx_dir: str = None, output_path: str = None):
    xlsx_dir = Path(xlsx_dir) if xlsx_dir else HERE / "xlsx"
    output_path = Path(output_path) if output_path else HERE / "gData" / "predictions.json"
    if not output_path.is_absolute():
        output_path = HERE / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not xlsx_dir.exists():
        raise FileNotFoundError(f"Directory not found: {xlsx_dir}")

    files = sorted(xlsx_dir.glob("*.xlsx"))
    if not files:
        raise FileNotFoundError(f"No .xlsx files found in {xlsx_dir}")

    players = {}
    errors  = {}

    for f in files:
        player_name = f.stem          # filename without extension = player name
        print(f"  Reading {f.name} → player '{player_name}' ...", end=" ")
        try:
            players[player_name] = extract_player(f)
            gs_filled = sum(
                1 for m in players[player_name]["group_stage"]
                if m["home_goals"] is not None
            )
            ko_filled = sum(
                1 for m in players[player_name]["knockout"]
                if m["team1_goals"] is not None
            )
            print(f"OK  ({gs_filled}/72 group, {ko_filled}/32 knockout)")
        except Exception as e:
            errors[f.name] = str(e)
            print(f"ERROR: {e}")

    output = {
        "players": players,
        "meta": {
            "xlsx_dir":      str(xlsx_dir),
            "files_scanned": [f.name for f in files],
            "files_ok":      list(players.keys()),
            "files_error":   errors,
            "total_players": len(players),
        },
    }

    out_path = Path(output_path)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(players)} player(s) → {out_path}")
    if errors:
        print(f"WARNING: {len(errors)} file(s) failed: {list(errors.keys())}")
    return output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    xlsx_dir    = sys.argv[1] if len(sys.argv) > 1 else None
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    scan(xlsx_dir, output_file)