# -*- coding: utf-8 -*-
"""
scan_predictions.py
-------------------
Reads all player prediction xlsx-files from xlsx/ and writes a single
predictions.json to gData/.

Departure point is wc2026.json (written by extract_wc2026.py), which
provides the authoritative fixture list.  The script no longer infers
match metadata from the xlsx cells; it looks up home/away team names
from the JSON and only reads the score/knockout cells from the player files.

Usage
-----
python py/scan_predictions.py                        # uses project defaults
python py/scan_predictions.py myxlsx/ out.json       # explicit paths
"""

import json
import sys
from pathlib import Path

import pandas as pd
from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root

# ---------------------------------------------------------------------------
# Project root — walk up from this script's location to find .git
# ---------------------------------------------------------------------------
def project_root() -> Path:
    return find_root(has_dir(".git"), start=Path(__file__).resolve().parent)


# ---------------------------------------------------------------------------
# Cell coordinates for knockout predictions (0-indexed row, col)
# ---------------------------------------------------------------------------

# Round of 32 – right-side bracket: 12 slots, col 30, rows 79-90
R32_RIGHT_ROWS = list(range(79, 91))   # → 12 team predictions
R32_RIGHT_COL  = 30

# Round of 32 – left-side bracket: 8 slots, col 19, rows 83-90
R32_LEFT_ROWS  = list(range(83, 91))   # → 8 team predictions
R32_LEFT_COL   = 19

# Quarter-finals: 4 slots, col 19, rows 94-97
QF_ROWS = list(range(94, 98))
QF_COL  = 19

# Semi-finals: 2 matches, col 19 (left) and col 28 (right), rows 101-102
SF_ROWS    = [101, 102]
SF_COL_L   = 19
SF_COL_R   = 28

# Champion: col 19, row 110
CHAMP_ROW = 110
CHAMP_COL = 19


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cell(df: pd.DataFrame, row: int, col: int):
    """Return a scalar cell value, or None if out-of-range / NaN / zero."""
    try:
        v = df.iloc[row, col]
    except IndexError:
        return None
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)) and v == 0:
        return None
    return str(v).strip() if isinstance(v, str) else v


def _score(df: pd.DataFrame, row: int, col: int):
    """Return an integer goal count, or None."""
    try:
        v = df.iloc[row, col]
    except IndexError:
        return None
    if pd.isna(v):
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Read a single player xlsx
# ---------------------------------------------------------------------------

def read_player_file(path: Path, match_index: dict) -> dict:
    """
    Parameters
    ----------
    path        : path to the player's xlsx file
    match_index : {match_id: {"home": str, "away": str}} from wc2026.json

    Returns
    -------
    dict with keys: group_stage, knockout, world_champion, warnings
    """
    df = pd.read_excel(path, sheet_name="2026 World Cup", header=None)

    warnings = []

    # --- Group stage (matches 1-72, sheet rows 6-77) ---
    group_stage = []
    for sheet_row in range(6, 78):
        raw_id = _cell(df, sheet_row, 0)
        if raw_id is None:
            continue
        try:
            match_id = int(float(raw_id))
        except (ValueError, TypeError):
            continue

        home_goals = _score(df, sheet_row, 5)
        away_goals = _score(df, sheet_row, 6)

        if home_goals is None or away_goals is None:
            warnings.append(f"M{match_id}: missing score (row {sheet_row})")

        fixture = match_index.get(match_id, {})
        group_stage.append({
            "match_id":   match_id,
            "home":       fixture.get("home"),
            "away":       fixture.get("away"),
            "home_goals": home_goals,
            "away_goals": away_goals,
        })

    # --- Knockout predictions ---

    # R32 – 12 teams from right-side bracket
    r32_right = []
    for row in R32_RIGHT_ROWS:
        team = _cell(df, row, R32_RIGHT_COL)
        if isinstance(team, str):
            r32_right.append(team)
        else:
            r32_right.append(None)
            warnings.append(f"R32-right slot row {row}: empty")

    # R32 – 8 teams from left-side bracket
    r32_left = []
    for row in R32_LEFT_ROWS:
        team = _cell(df, row, R32_LEFT_COL)
        if isinstance(team, str):
            r32_left.append(team)
        else:
            r32_left.append(None)
            warnings.append(f"R32-left slot row {row}: empty")

    # QF – 4 winners
    qf = []
    for row in QF_ROWS:
        team = _cell(df, row, QF_COL)
        if isinstance(team, str):
            qf.append(team)
        else:
            qf.append(None)
            warnings.append(f"QF slot row {row}: empty")

    # SF – 4 participants, 2 winners (col28)
    sf_left  = [_cell(df, r, SF_COL_L) for r in SF_ROWS]
    sf_right = [_cell(df, r, SF_COL_R) for r in SF_ROWS]

    # Champion
    champion = _cell(df, CHAMP_ROW, CHAMP_COL)
    if champion is None:
        warnings.append("Champion cell is empty")

    knockout = {
        "r32_right":  r32_right,   # 12 teams advancing through right side
        "r32_left":   r32_left,    # 8 teams advancing through left side
        "quarterfinals": qf,       # 4 QF winners
        "semifinal_left":  sf_left,   # 2 SF participants (col 19 side)
        "semifinal_right": sf_right,  # 2 SF winners (col 28 side)
    }

    return {
        "group_stage":    group_stage,
        "knockout":       knockout,
        "world_champion": str(champion) if champion else None,
        "warnings":       warnings,
    }


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan(xlsx_dir: str = None, output_path: str = None,
         fixture_json: str = None) -> None:
    root = project_root()

    xlsx_dir     = Path(xlsx_dir)     if xlsx_dir     else root / "xlsx"
    output_path  = Path(output_path)  if output_path  else root / "gData" / "predictions.json"
    fixture_json = Path(fixture_json) if fixture_json else root / "gData" / "wc2026.json"

    if not fixture_json.exists():
        raise FileNotFoundError(
            f"Fixture JSON not found: {fixture_json}\n"
            "Run extract_wc2026.py first."
        )

    with open(fixture_json, encoding="utf-8") as fh:
        wc_data = json.load(fh)

    # Build match_index: {match_id: {home, away}}
    match_index = {}
    for m in wc_data.get("group_stage", []):
        match_index[m["match_id"]] = {"home": m["home"], "away": m["away"]}

    xlsx_files = sorted(xlsx_dir.glob("*.xlsx"))
    if not xlsx_files:
        print(f"No xlsx files found in {xlsx_dir}")
        return

    players = {}
    for path in xlsx_files:
        player_name = path.stem
        print(f"  Scanning {player_name}...", end=" ")
        try:
            data = read_player_file(path, match_index)
            n_warn = len(data["warnings"])
            if n_warn:
                print(f"{n_warn} warning(s)")
                for w in data["warnings"]:
                    print(f"    ⚠ {w}")
            else:
                print("OK")
            players[player_name] = data
        except Exception as exc:
            print(f"ERROR: {exc}")

    output = {
        "meta": {
            "fixture_source": str(fixture_json),
            "n_players": len(players),
            "players": sorted(players.keys()),
        },
        "players": players,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(players)} player(s) → {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    xlsx_arg    = sys.argv[1] if len(sys.argv) > 1 else None
    output_arg  = sys.argv[2] if len(sys.argv) > 2 else None
    fixture_arg = sys.argv[3] if len(sys.argv) > 3 else None
    scan(xlsx_arg, output_arg, fixture_arg)
