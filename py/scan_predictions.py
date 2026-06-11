# -*- coding: utf-8 -*-
"""
scan_predictions.py
-------------------
Reads all player prediction xlsx-files from xlsx/ and writes
gData/predictions.json.

Group stage scores are read from cols F/G (0-indexed 5/6), rows 7-78.

Knockout predictions are read directly from the dedicated bracket columns,
where each match occupies two consecutive rows (home team, away team):

  BL (col 64) — Round of 32   : rows 10-11, 14-15, ..., 70-71  (16 matches)
  BS (col 71) — Round of 16   : rows 12-13, 20-21, ..., 44-45  ( 8 matches)  [5 shown here, read all non-null]
  BZ (col 78) — Quarter-finals: rows 16-17, 32-33, 48-49       ( up to 4 matches)
  CG (col 85) — Semi-finals   : rows 23-24                      ( 1 match shown; read all)
  CN (col 92) — Final & Bronze: rows 37-38 (final), 48-49 (bronze)

Usage
-----
python py/scan_predictions.py                   # project defaults
python py/scan_predictions.py xlsx/ out.json    # explicit paths
"""

import json
import sys
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string
import pandas as pd
from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root


# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------
def project_root() -> Path:
    return find_root(has_dir(".git"), start=Path(__file__).resolve().parent)


# ---------------------------------------------------------------------------
# Column indices (1-based, as openpyxl uses)
# ---------------------------------------------------------------------------
# Each round: team col, then FT score, ET score, PEN score in the next 3 cols
ROUNDS = {
    "r32":    ("BL", "BM", "BN", "BO", list(range(10, 72, 4))),
    "r16":    ("BS", "BT", "BU", "BV", list(range(12, 48, 8))),
    "qf":     ("BZ", "CA", "CB", "CC", list(range(16, 56, 16))),
    "sf":     ("CG", "CH", "CI", "CJ", [23, 39]),
    "final":  ("CN", "CO", "CP", "CQ", [37]),
    "bronze": ("CN", "CO", "CP", "CQ", [48]),
}
ROUNDS_CI = {
    k: tuple(column_index_from_string(c) if isinstance(c, str) else c for c in v)
    for k, v in ROUNDS.items()
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _val(ws, row, col):
    """Return cell value, or None if empty/zero."""
    v = ws.cell(row=row, column=col).value
    if v is None:
        return None
    if isinstance(v, (int, float)) and v == 0:
        return None
    if isinstance(v, str) and v.strip() in ('', '0'):
        return None
    return str(v).strip() if isinstance(v, str) else v


def _int(v):
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _score(ws, row, col):
    """Read a goal count — allows 0, returns None only for truly empty cells."""
    v = ws.cell(row=row, column=col).value
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _read_matches(ws, col_team, col_ft, col_et, col_pen, first_rows):
    """Read knockout matches: teams + FT/ET/PEN scores."""
    matches = []
    for r in first_rows:
        home = _val(ws, r,     col_team)
        away = _val(ws, r + 1, col_team)
        if not home and not away:
            continue
        ft_h = _score(ws, r,     col_ft)
        ft_a = _score(ws, r + 1, col_ft)
        et_h = _score(ws, r,     col_et)
        et_a = _score(ws, r + 1, col_et)
        pn_h = _score(ws, r,     col_pen)
        pn_a = _score(ws, r + 1, col_pen)
        matches.append({
            "home": home, "away": away,
            "ft": [ft_h, ft_a],
            "et": [et_h, et_a] if et_h is not None else None,
            "pen": [pn_h, pn_a] if pn_h is not None else None,
        })
    return matches


# ---------------------------------------------------------------------------
# Read a single player xlsx
# ---------------------------------------------------------------------------
def read_player_file(path: Path, match_index: dict) -> dict:
    # Use openpyxl with data_only=True to get formula-evaluated values
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb['2026 World Cup']
    warnings = []

    # --- Group stage: rows 7-78, cols F(6)/G(7) for scores ---
    group_stage = []
    for row in range(7, 79):
        raw_id = _val(ws, row, 1)   # col A = match id
        if raw_id is None:
            continue
        match_id = _int(raw_id)
        if match_id is None:
            continue

        home_goals = _score(ws, row, 6)   # col F
        away_goals = _score(ws, row, 7)   # col G

        if home_goals is None or away_goals is None:
            warnings.append(f"M{match_id}: missing score (row {row})")

        fixture = match_index.get(match_id, {})
        group_stage.append({
            "match_id":   match_id,
            "home":       fixture.get("home"),
            "away":       fixture.get("away"),
            "home_goals": home_goals,
            "away_goals": away_goals,
        })

    # --- Knockout ---
    def _rm(key):
        ct, ft, et, pn, rows = ROUNDS_CI[key]
        return _read_matches(ws, ct, ft, et, pn, rows)

    knockout = {
        "r32":    _rm("r32"),
        "r16":    _rm("r16"),
        "qf":     _rm("qf"),
        "sf":     _rm("sf"),
        "final":  _rm("final")[0] if _rm("final") else {},
        "bronze": _rm("bronze")[0] if _rm("bronze") else {},
    }

    # Derive champion from the final result
    f = knockout.get("final", {})
    ft = f.get("ft", [None, None])
    et = f.get("et") or [None, None]
    pn = f.get("pen") or [None, None]

    if ft[0] is not None and ft[1] is not None:
        if ft[0] > ft[1]:
            champion = f["home"]
        elif ft[1] > ft[0]:
            champion = f["away"]
        elif et[0] is not None and et[1] is not None:
            if et[0] > et[1]:
                champion = f["home"]
            elif et[1] > et[0]:
                champion = f["away"]
            elif pn[0] is not None and pn[1] is not None:
                champion = f["home"] if pn[0] > pn[1] else f["away"]
            else:
                champion = None
        else:
            champion = None
    else:
        champion = None

    return {
        "group_stage":    group_stage,
        "knockout":       knockout,
        "world_champion": champion,
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

    match_index = {m["match_id"]: {"home": m["home"], "away": m["away"]}
                   for m in wc_data.get("group_stage", [])}

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
                    print(f"    ⚠  {w}")
            else:
                print("OK")
            players[player_name] = data
        except Exception as exc:
            print(f"ERROR: {exc}")

    output = {
        "meta": {
            "fixture_source": str(fixture_json),
            "n_players":      len(players),
            "players":        sorted(players.keys()),
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
