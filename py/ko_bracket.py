# -*- coding: utf-8 -*-
"""
ko_bracket.py
-------------
For each knockout stage, shows which teams each participant predicted
would appear, contrasted with the actual teams from the fasit.

Each predicted team is annotated:
  ✓✓  correct team AND correct bracket slot  (+25 +5 pts)
  ✓   correct team, wrong slot               (+25 pts)
  ✗   wrong team                             (0 pts)

Output (one block per stage):
  - Actual match pairings from fasit
  - Per-participant: predicted pairings with per-team annotation
  - Points earned in that stage

Usage
-----
python py/ko_bracket.py                        # all stages, all participants
python py/ko_bracket.py --stage qf             # one stage only
python py/ko_bracket.py --player TC            # one participant only
python py/ko_bracket.py --stage sf --player TC

Stage keys: r32, r16, qf, sf, final, bronze
"""

import json
import sys
from pathlib import Path

from pyprojroot.criterion import has_dir
from pyprojroot.root import find_root


# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------
def project_root() -> Path:
    return find_root(has_dir(".git"), start=Path(__file__).resolve().parent)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STAGE_LABEL = {
    "r32":    "Round of 32",
    "r16":    "Round of 16",
    "qf":     "Quarterfinals",
    "sf":     "Semi-Finals",
    "final":  "Final",
    "bronze": "Third-Place Play-Off",
}
STAGE_MATCH_IDS = {
    "r32":    set(range(73, 89)),
    "r16":    set(range(89, 97)),
    "qf":     set(range(97, 101)),
    "sf":     {101, 102},
    "final":  {104},
    "bronze": {103},
}
STAGE_ORDER = ["r32", "r16", "qf", "sf", "final", "bronze"]

CORRECT_TEAM_PTS = 25
CORRECT_SPOT_PTS =  5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _matches_in_stage(ko_list: list, stage_key: str) -> list[dict]:
    """Return matches (sorted by match id) for a given stage."""
    ids = STAGE_MATCH_IDS[stage_key]
    return sorted(
        [m for m in ko_list if m.get("match") in ids],
        key=lambda m: m["match"]
    )


def _stage_teams(fasit_matches: list) -> set[str]:
    """All teams that actually appeared in these fasit matches."""
    teams = set()
    for m in fasit_matches:
        if m.get("team1"): teams.add(m["team1"])
        if m.get("team2"): teams.add(m["team2"])
    return teams


def _abbr(player_key: str, deltagere: list) -> str:
    stem = Path(player_key).stem
    for d in deltagere:
        if Path(d.get("file", "")).stem == stem:
            return d.get("abbr", stem)
    return stem[:8]


def _find_players(query: str, players: dict, deltagere: list) -> list[str]:
    if not query:
        return sorted(players.keys())
    q = query.strip().lower()
    stem_to_abbr = {}
    stem_to_name = {}
    for d in deltagere:
        stem = Path(d.get("file", "")).stem.lower()
        stem_to_abbr[stem] = d.get("abbr", "").lower()
        stem_to_name[stem] = d.get("full_name", "").lower()
    matched = []
    for key in players:
        stem = Path(key).stem.lower()
        if (stem == q
                or stem_to_abbr.get(stem) == q
                or stem_to_name.get(stem) == q
                or q in stem_to_name.get(stem, "")):
            matched.append(key)
    return matched


def _annotate_team(team: str | None,
                   slot: str,           # "team1" or "team2"
                   match_id: int,
                   fasit_by_match: dict,
                   fasit_stage_teams: set) -> str:
    """
    Return annotated team string:
      ✓✓ <name>  — correct team, correct slot
      ✓  <name>  — correct team, wrong slot
      ✗  <name>  — wrong team
      (empty)    — no prediction
    """
    if not team:
        return "—"
    fasit_match = fasit_by_match.get(match_id, {})
    correct_slot = (fasit_match.get(slot) == team)
    correct_team = (team in fasit_stage_teams)
    if correct_slot:           # correct_slot implies correct_team
        return f"✓✓ {team}"
    elif correct_team:
        return f"✓  {team}"
    else:
        return f"✗  {team}"


def _stage_pts(pred_matches: list, fasit_by_match: dict, fasit_stage_teams: set) -> int:
    """Compute points earned in a stage for one participant."""
    pts = 0
    for m in pred_matches:
        mid = m.get("match")
        fasit_m = fasit_by_match.get(mid, {})
        for slot in ("team1", "team2"):
            t = m.get(slot)
            if not t:
                continue
            if fasit_m.get(slot) == t:
                pts += CORRECT_TEAM_PTS + CORRECT_SPOT_PTS
            elif t in fasit_stage_teams:
                pts += CORRECT_TEAM_PTS
    return pts


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
def print_stage(stage_key: str,
                fasit_matches: list,
                players_to_show: dict,
                deltagere: list,
                scores_by_player: dict):

    label      = STAGE_LABEL[stage_key]
    n_matches  = len(fasit_matches)
    fasit_by_match    = {m["match"]: m for m in fasit_matches}
    fasit_stage_teams = _stage_teams(fasit_matches)
    max_pts    = n_matches * 2 * (CORRECT_TEAM_PTS + CORRECT_SPOT_PTS)

    print(f"\n{'═' * 80}")
    print(f"  {label}  —  {n_matches} match(es)  "
          f"[max {max_pts} pts: ✓✓ = +{CORRECT_TEAM_PTS+CORRECT_SPOT_PTS} pts, "
          f"✓ = +{CORRECT_TEAM_PTS} pts]")
    print(f"{'═' * 80}")

    if not fasit_matches:
        print("  (no fasit results yet for this stage)")
        return

    # --- Actual pairings ---
    print("  Actual:")
    for m in fasit_matches:
        print(f"    M{m['match']:>3}  {m.get('team1', '?')}  vs  {m.get('team2', '?')}")

    print(f"  {'─' * 76}")

    # --- Build per-participant rows ---
    # Each row: (abbr, pts, [(m_id, t1_annotated, t2_annotated), ...])
    rows = []
    for player_key, data in players_to_show.items():
        abbr = _abbr(player_key, deltagere)
        pred_ko = data.get("knockout", [])
        pred_matches = _matches_in_stage(pred_ko if isinstance(pred_ko, list) else [], stage_key)
        pred_by_match = {m["match"]: m for m in pred_matches}

        match_rows = []
        for fasit_m in fasit_matches:
            mid = fasit_m["match"]
            pred_m = pred_by_match.get(mid, {})
            t1 = _annotate_team(pred_m.get("team1"), "team1", mid, fasit_by_match, fasit_stage_teams)
            t2 = _annotate_team(pred_m.get("team2"), "team2", mid, fasit_by_match, fasit_stage_teams)
            match_rows.append((mid, t1, t2))

        pts = _stage_pts(pred_matches, fasit_by_match, fasit_stage_teams)
        rows.append((abbr, pts, match_rows))

    # Sort by pts desc, then abbr
    rows.sort(key=lambda r: (-r[1], r[0]))

    col_w = max((len(r[0]) for r in rows), default=6)
    print(f"  {'Participant':<{col_w}}  {'Pts':>4}  Predicted (✓✓=right slot  ✓=right team  ✗=wrong)")
    print(f"  {'─' * col_w}  {'─' * 4}  {'─' * 56}")

    for abbr, pts, match_rows in rows:
        # First match on same line as participant name; subsequent matches indented
        for i, (mid, t1, t2) in enumerate(match_rows):
            name_col = f"{abbr:<{col_w}}" if i == 0 else " " * col_w
            pts_col  = f"{pts:>4}"        if i == 0 else " " * 4
            print(f"  {name_col}  {pts_col}  M{mid:>3}  {t1}  vs  {t2}")

    print(f"{'─' * 80}")


# ---------------------------------------------------------------------------
# Medal summary
# ---------------------------------------------------------------------------
def print_medals(players_to_show: dict, fasit: dict,
                 scores_by_player: dict, deltagere: list):
    actual_ch  = fasit.get("world_champion")
    actual_ru  = fasit.get("runner_up")
    actual_3rd = fasit.get("third_place")

    if not any([actual_ch, actual_ru, actual_3rd]):
        return

    print(f"\n{'═' * 80}")
    print(f"  Medal predictions  "
          f"[🥇 +200 pts  🥈 +100 pts  🥉 +70 pts]")
    print(f"{'═' * 80}")
    print(f"  Actual:  🥇 {actual_ch or '?'}   🥈 {actual_ru or '?'}   🥉 {actual_3rd or '?'}")
    print(f"  {'─' * 76}")

    rows = []
    for player_key, data in players_to_show.items():
        abbr     = _abbr(player_key, deltagere)
        pred_ch  = data.get("world_champion")
        pred_ru  = data.get("runner_up")
        pred_3rd = data.get("third_place")
        medal_pts = scores_by_player.get(player_key, {}).get("medals", {}).get("points", 0)
        rows.append((abbr, pred_ch, pred_ru, pred_3rd, medal_pts))

    rows.sort(key=lambda r: (-r[4], r[0]))

    col_w = max((len(r[0]) for r in rows), default=6)

    def _fmt(pred, actual):
        if pred is None:
            return f"{'—':<22}"
        mark = "✓" if (actual and pred == actual) else "✗"
        return f"{mark}  {pred:<20}"

    print(f"  {'Participant':<{col_w}}  {'Pts':>4}  {'🥇':<22}  {'🥈':<22}  {'🥉':<22}")
    print(f"  {'─' * col_w}  {'─' * 4}  {'─' * 22}  {'─' * 22}  {'─' * 22}")

    for abbr, ch, ru, third, pts in rows:
        print(f"  {abbr:<{col_w}}  {pts:>4}  {_fmt(ch, actual_ch)}"
              f"  {_fmt(ru, actual_ru)}  {_fmt(third, actual_3rd)}")

    print(f"{'─' * 80}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    stage_filter  = None
    player_filter = None
    args = list(argv)
    i = 0
    while i < len(args):
        if args[i] == "--stage" and i + 1 < len(args):
            stage_filter = args[i + 1].lower()
            i += 2
        elif args[i] == "--player" and i + 1 < len(args):
            player_filter = args[i + 1]
            i += 2
        else:
            i += 1

    if stage_filter and stage_filter not in STAGE_LABEL:
        print(f"Unknown stage '{stage_filter}'. Valid keys: {', '.join(STAGE_ORDER)}")
        sys.exit(1)

    root = project_root()

    fasit_path       = root / "gData" / "fasit.json"
    predictions_path = root / "gData" / "predictions.json"
    scores_path      = root / "gData" / "scores.json"
    deltagere_path   = root / "gData" / "deltagere.json"

    if not fasit_path.exists():
        print(f"fasit.json not found at {fasit_path}. Run score.py first.")
        sys.exit(1)
    if not predictions_path.exists():
        print(f"predictions.json not found. Run scan_predictions.py first.")
        sys.exit(1)

    with open(fasit_path,        encoding="utf-8") as f: fasit = json.load(f)
    with open(predictions_path,  encoding="utf-8") as f: preds = json.load(f)

    scores_by_player = {}
    if scores_path.exists():
        with open(scores_path, encoding="utf-8") as f:
            scores_by_player = json.load(f).get("players", {})

    deltagere = []
    if deltagere_path.exists():
        with open(deltagere_path, encoding="utf-8") as f:
            deltagere = json.load(f)

    all_players = preds.get("players", {})
    if player_filter:
        matched = _find_players(player_filter, all_players, deltagere)
        if not matched:
            print(f"No participant found matching '{player_filter}'.")
            sys.exit(1)
        players_to_show = {k: all_players[k] for k in matched}
    else:
        players_to_show = all_players

    fasit_ko = fasit.get("knockout", [])
    stages   = [stage_filter] if stage_filter else STAGE_ORDER

    for stage_key in stages:
        fasit_matches = _matches_in_stage(fasit_ko, stage_key)
        print_stage(stage_key, fasit_matches, players_to_show, deltagere, scores_by_player)

    if not stage_filter:
        print_medals(players_to_show, fasit, scores_by_player, deltagere)


if __name__ == "__main__":
    main()
