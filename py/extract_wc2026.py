# -*- coding: utf-8 -*-
"""
extract_wc2026.py
-----------------
Reads the blank World Cup 2026 xlsx template and writes gData/wc2026.json,
which serves as the authoritative fixture reference for all downstream scripts
(scan_predictions.py, simulate_tournament.py, etc.).

Output schema
-------------
{
  "groups": {
    "Group A": ["Mexico", "Korea Republic", "Czech Republic", "South Africa"],
    ...
  },
  "group_stage": [
    {
      "match_id": 1,
      "date": "Jun 11, 2026",
      "home": "Mexico",
      "away": "South Africa",
      "group": "Group A"
    },
    ...
  ],
  "knockout_slots": {
    "r32_right": ["3A", "3B", ..., "1F"],   // 12 slots, col 30 rows 79-90
    "r32_left":  ["1E", "2F", ...],          // 8 slots,  col 19 rows 83-90
    "qf":        [...],                      // 4 slots,  col 19 rows 94-97
    "sf_left":   [...],                      // 2 slots,  col 19 rows 101-102
    "sf_right":  [...],                      // 2 slots,  col 28 rows 101-102
    "champion":  "..."                       // col 19 row 110
  }
}

Usage
-----
python py/extract_wc2026.py                              # uses project defaults
python py/extract_wc2026.py world_cup_2026.xlsx out.json # explicit paths
"""

import json
import sys
from pathlib import Path

import pandas as pd
from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root


# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------

def project_root() -> Path:
    return find_root(has_dir(".git"), start=Path(__file__).resolve().parent)


# ---------------------------------------------------------------------------
# Cell coordinate constants (0-indexed row, col)
# ---------------------------------------------------------------------------

# Group stage: match rows 6–77
GS_FIRST_ROW = 6
GS_LAST_ROW  = 77        # inclusive
COL_MATCH_ID = 0
COL_DATE     = 2
COL_HOME     = 4
COL_AWAY     = 7

# Group standings header: col 9, value starts with "Group "
COL_GROUP_HEADER = 9

# Knockout slot columns
R32_RIGHT_COL = 30       # 12 rows: 79–90
R32_LEFT_COL  = 19       # 8 rows:  83–90
QF_COL        = 19       # 4 rows:  94–97
SF_LEFT_COL   = 19       # 2 rows:  101–102
SF_RIGHT_COL  = 28       # 2 rows:  101–102
CHAMP_COL     = 19       # row 110

R32_RIGHT_ROWS = list(range(79, 91))
R32_LEFT_ROWS  = list(range(83, 91))
QF_ROWS        = list(range(94, 98))
SF_ROWS        = [101, 102]
CHAMP_ROW      = 110


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _str(val) -> str | None:
    """Return a stripped string, or None for NaN / 0 / empty."""
    if val is None:
        return None
    if isinstance(val, float):
        if pd.isna(val) or val == 0.0:
            return None
        # whole-number float → int string
        if val == int(val):
            return str(int(val))
    s = str(val).strip()
    return s if s else None


def _cell(df: pd.DataFrame, row: int, col: int) -> str | None:
    try:
        return _str(df.iloc[row, col])
    except IndexError:
        return None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_groups(df: pd.DataFrame) -> dict[str, list[str]]:
    """Read the standings sidebar (col 9) to build group → team list."""
    groups: dict[str, list[str]] = {}
    current = None
    for i in range(GS_FIRST_ROW, GS_LAST_ROW + 1):
        v = _cell(df, i, COL_GROUP_HEADER)
        if v and v.startswith("Group "):
            current = v
            groups[current] = []
        elif current and v and not v.startswith("Group "):
            groups[current].append(v)
    return groups


def _team_to_group(groups: dict[str, list[str]]) -> dict[str, str]:
    return {team: grp for grp, teams in groups.items() for team in teams}


def extract_group_stage(df: pd.DataFrame,
                        t2g: dict[str, str]) -> list[dict]:
    matches = []
    for i in range(GS_FIRST_ROW, GS_LAST_ROW + 1):
        raw_id = _cell(df, i, COL_MATCH_ID)
        if raw_id is None:
            continue
        try:
            match_id = int(raw_id)
        except ValueError:
            continue
        if not 1 <= match_id <= 72:
            continue

        home = _cell(df, i, COL_HOME)
        away = _cell(df, i, COL_AWAY)
        date = _cell(df, i, COL_DATE)

        group = t2g.get(home) or t2g.get(away)

        matches.append({
            "match_id": match_id,
            "date":     date,
            "home":     home,
            "away":     away,
            "group":    group,
        })

    matches.sort(key=lambda m: m["match_id"])
    return matches


def extract_knockout_slots(df: pd.DataFrame) -> dict:
    """
    Read the formula-evaluated slot labels from the bracket cells.
    In the blank template these cells already contain values like
    "1A", "2B", "3E" etc., populated by the sheet's own formulas.
    A value of 0 or NaN means the slot is still unresolved.
    """
    def _slots(rows, col):
        return [_cell(df, r, col) for r in rows]

    return {
        "r32_right": _slots(R32_RIGHT_ROWS, R32_RIGHT_COL),  # 12 entries
        "r32_left":  _slots(R32_LEFT_ROWS,  R32_LEFT_COL),   # 8 entries
        "qf":        _slots(QF_ROWS,        QF_COL),          # 4 entries
        "sf_left":   _slots(SF_ROWS,        SF_LEFT_COL),     # 2 entries
        "sf_right":  _slots(SF_ROWS,        SF_RIGHT_COL),    # 2 entries
        "champion":  _cell(df, CHAMP_ROW,   CHAMP_COL),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(xlsx_path: str = None, output_path: str = None) -> dict:
    root = project_root()

    xlsx_path   = Path(xlsx_path)   if xlsx_path   else root / "files" / "world_cup_2026.xlsx"
    output_path = Path(output_path) if output_path else root / "gData" / "wc2026.json"

    print(f"Reading {xlsx_path} ...")
    df = pd.read_excel(xlsx_path, sheet_name="2026 World Cup", header=None)

    groups     = extract_groups(df)
    t2g        = _team_to_group(groups)
    group_stage = extract_group_stage(df, t2g)
    ko_slots    = extract_knockout_slots(df)

    data = {
        "source":          str(xlsx_path.name),
        "groups":          groups,
        "group_stage":     group_stage,
        "knockout_slots":  ko_slots,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

    print(f"Groups:        {len(groups)} ({sum(len(v) for v in groups.values())} teams)")
    print(f"Group stage:   {len(group_stage)} matches")
    print(f"Knockout slots: r32_right={len([x for x in ko_slots['r32_right'] if x])}"
          f"  r32_left={len([x for x in ko_slots['r32_left'] if x])}"
          f"  qf={len([x for x in ko_slots['qf'] if x])}")
    print(f"Wrote → {output_path}")

    return data


if __name__ == "__main__":
    xlsx_arg   = sys.argv[1] if len(sys.argv) > 1 else None
    output_arg = sys.argv[2] if len(sys.argv) > 2 else None
    main(xlsx_arg, output_arg)
