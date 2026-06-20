# -*- coding: utf-8 -*-
"""
score.py
--------
Calculates each player's competition score by comparing their predictions
(gData/predictions.json) against the actual results read directly from
fasit/world_cup_2026_fasit.xlsx.

Scoring rules
-------------
Qualitative questions (17 questions, including total goals):
  +30   per correct answer
  Max:  510 points

Group stage (72 matches):
  +25   correct match outcome (win / draw / loss)
  -Δh²  squared error on home goals
  -Δa²  squared error on away goals
  Max:  1800 points

Knockout stage (32 matches):
  +25   per team that reached the round (correct_team)
  +5    bonus if team is in the correct bracket slot (correct_spot)
  Max:  1920 points  (60 pts × 32 games)

Final standings bonuses:
  +200  correct World Cup winner
  +100  correct runner-up (Silver)
  +70   correct 3rd place (Bronze)
  Max:  370 points

Theoretical maximum: 4600 points

Usage
-----
python py/score.py                          # uses project defaults
python py/score.py fasit/my_fasit.xlsx      # explicit fasit path
"""

import csv
import json
import math
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
# Scoring constants
# ---------------------------------------------------------------------------

QUESTION_PTS        = 30    # per correct qualitative answer
CORRECT_OUTCOME_PTS = 25    # correct group stage result
CORRECT_TEAM_PTS    = 25    # correct team in knockout round
CORRECT_SPOT_PTS    = 5     # bonus: correct slot in bracket
CHAMPION_BONUS      = 200
SILVER_BONUS        = 100
BRONZE_BONUS        = 70

MAX_POINTS = (
    QUESTION_PTS * 17 +          # 510
    CORRECT_OUTCOME_PTS * 72 +   # 1800
    (CORRECT_TEAM_PTS + CORRECT_SPOT_PTS) * 2 * 32 +  # 1920
    CHAMPION_BONUS + SILVER_BONUS + BRONZE_BONUS       # 370
)  # = 4600


# ---------------------------------------------------------------------------
# Read fasit from xlsx
# ---------------------------------------------------------------------------

KNOCKOUT_STAGES = [
    ("Round of 32",           62, range(73,  89)),
    ("Round of 16",           69, range(89,  97)),
    ("Quarterfinals",         76, range(97, 101)),
    ("Semi-Finals",           83, range(101, 103)),
    ("Third-Place Play-Off",  90, [103]),
    ("Final",                 90, [104]),
]


def _safe(val):
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


def read_fasit(xlsx_path: Path) -> dict:
    """
    Read actual results from the fasit xlsx.
    Returns group_stage, knockout, world_champion, runner_up, third_place.
    Only matches with scores filled in are included.
    """
    df = pd.read_excel(xlsx_path, sheet_name="2026 World Cup", header=None)

    # Group stage (matches 1-72)
    # play_order reflects chronological kickoff time (date in column C,
    # time in column D), not the match number or row position. This lets
    # standings/lag logic compare e.g. match 7 to match 8 correctly when
    # match 8 kicks off earlier than match 7.
    group_stage_raw = []
    for idx in range(6, df.shape[0]):
        raw = _safe(df.iloc[idx, 0])
        if not isinstance(raw, int) or not (1 <= raw <= 72):
            continue
        hg = _goals(df.iloc[idx, 5])
        ag = _goals(df.iloc[idx, 6])
        if hg is None or ag is None:
            continue

        date_val = df.iloc[idx, 2]   # e.g. "Jun 11, 2026"
        time_val = df.iloc[idx, 3]   # datetime.time, e.g. 19:00:00

        try:
            kickoff = pd.to_datetime(str(date_val)) + pd.to_timedelta(str(time_val))
        except (ValueError, TypeError):
            kickoff = None

        group_stage_raw.append({
            "match":      raw,
            "kickoff":    kickoff,
            "home":       str(df.iloc[idx, 4]) if pd.notna(df.iloc[idx, 4]) else None,
            "away":       str(df.iloc[idx, 7]) if pd.notna(df.iloc[idx, 7]) else None,
            "home_goals": hg,
            "away_goals": ag,
        })

    # Assign play_order by sorting on kickoff time. Matches with no parseable
    # kickoff (shouldn't normally happen) sort last, in match-number order.
    group_stage_raw.sort(key=lambda m: (m["kickoff"] is None, m["kickoff"], m["match"]))
    group_stage = []
    for play_order, m in enumerate(group_stage_raw, start=1):
        m = dict(m)
        m["play_order"] = play_order
        del m["kickoff"]
        group_stage.append(m)

    # Knockout (matches 73-104)
    knockout = []
    for stage_label, mc, match_range in KNOCKOUT_STAGES:
        for idx in range(6, df.shape[0]):
            raw = _safe(df.iloc[idx, mc])
            if not isinstance(raw, int) or raw not in match_range:
                continue
            g1 = _goals(df.iloc[idx,   mc + 2])
            g2 = _goals(df.iloc[idx+1, mc + 2])
            if g1 is None or g2 is None:
                continue
            team1 = str(df.iloc[idx,   mc+1]) if pd.notna(df.iloc[idx,   mc+1]) else None
            team2 = str(df.iloc[idx+1, mc+1]) if pd.notna(df.iloc[idx+1, mc+1]) else None
            knockout.append({
                "match":       raw,
                "stage":       stage_label,
                "team1":       team1,
                "team2":       team2,
                "team1_goals": g1,
                "team2_goals": g2,
            })

    # Knockout matches don't have populated date/time columns in this
    # template, but their match numbers are already chronological (Round of
    # 32 → Final), so play_order continues sequentially from the group stage.
    knockout.sort(key=lambda m: m["match"])
    next_play_order = len(group_stage) + 1
    for m in knockout:
        m["play_order"] = next_play_order
        next_play_order += 1

    # Final result (M104)
    world_champion = runner_up = third_place = None
    final = next((m for m in knockout if m["match"] == 104), None)
    if final and final["team1_goals"] is not None:
        if final["team1_goals"] > final["team2_goals"]:
            world_champion, runner_up = final["team1"], final["team2"]
        else:
            world_champion, runner_up = final["team2"], final["team1"]

    third_place_match = next((m for m in knockout if m["match"] == 103), None)
    if third_place_match and third_place_match["team1_goals"] is not None:
        if third_place_match["team1_goals"] > third_place_match["team2_goals"]:
            third_place = third_place_match["team1"]
        else:
            third_place = third_place_match["team2"]

    return {
        "group_stage":    sorted(group_stage, key=lambda m: m["match"]),
        "knockout":       sorted(knockout,    key=lambda m: m["match"]),
        "world_champion": world_champion,
        "runner_up":      runner_up,
        "third_place":    third_place,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _outcome(hg, ag):
    if hg > ag: return  1
    if hg < ag: return -1
    return 0


# ---------------------------------------------------------------------------
# Qualitative questions scoring
# ---------------------------------------------------------------------------

def score_questions(player_answers: dict | None, fasit_answers: dict | None) -> dict:
    """
    Score the 17 qualitative questions (incl. total goals prediction).
    Both dicts are keyed by question id/name → answer.
    Returns points and per-question detail.
    """
    if not player_answers or not fasit_answers:
        return {"points": 0, "correct": 0, "detail": {}}

    correct = 0
    detail  = {}
    for q_id, correct_ans in fasit_answers.items():
        predicted = player_answers.get(q_id)
        is_correct = (predicted is not None and
                      str(predicted).strip().lower() == str(correct_ans).strip().lower())
        if is_correct:
            correct += 1
        detail[q_id] = {
            "predicted":  predicted,
            "actual":     correct_ans,
            "correct":    is_correct,
        }

    return {
        "points":  correct * QUESTION_PTS,
        "correct": correct,
        "detail":  detail,
    }


# ---------------------------------------------------------------------------
# Group stage scoring
# ---------------------------------------------------------------------------

def score_group_stage(player_matches: list, result_matches: list) -> dict:
    def _mn(m): return m.get("match") or m.get("match_id")
    def _hg(m): return m.get("home_goals") if m.get("home_goals") is not None else m.get("h")
    def _ag(m): return m.get("away_goals") if m.get("away_goals") is not None else m.get("b")

    results     = {_mn(m): m for m in result_matches}
    predictions = {_mn(m): m for m in player_matches}

    correct_outcome = 0
    home_sq_err     = 0
    away_sq_err     = 0
    running         = []
    cumulative      = 0

    for mn in sorted(results, key=lambda m: results[m].get("play_order", m)):
        r = results[mn]
        p = predictions.get(mn)

        r_h, r_a = _hg(r), _ag(r)

        if p is None or _hg(p) is None or _ag(p) is None:
            running.append({"match": mn, "play_order": r.get("play_order", mn), "cumulative": cumulative})
            continue

        p_h, p_a = _hg(p), _ag(p)
        dh, da   = p_h - r_h, p_a - r_a

        outcome_pts = CORRECT_OUTCOME_PTS if _outcome(p_h, p_a) == _outcome(r_h, r_a) else 0
        correct_outcome += (1 if outcome_pts else 0)
        home_sq_err     += dh * dh
        away_sq_err     += da * da

        match_pts   = outcome_pts - dh * dh - da * da
        cumulative += match_pts

        running.append({
            "match":       mn,
            "play_order":  r.get("play_order", mn),
            "pred":        f"{p_h}-{p_a}",
            "actual":      f"{r_h}-{r_a}",
            "outcome_pts": outcome_pts,
            "home_sq_err": dh * dh,
            "away_sq_err": da * da,
            "match_pts":   match_pts,
            "cumulative":  cumulative,
        })

    return {
        "points":          CORRECT_OUTCOME_PTS * correct_outcome - home_sq_err - away_sq_err,
        "correct_outcome": correct_outcome,
        "home_sq_err":     home_sq_err,
        "away_sq_err":     away_sq_err,
        "matches_played":  len(results),
        "running":         running,
    }


# ---------------------------------------------------------------------------
# Knockout scoring
# ---------------------------------------------------------------------------

def _normalise_ko(ko) -> list:
    """
    Accept both formats:
      New: flat list of match dicts with 'match', 'team1', 'team2', 'stage'
      Old: dict keyed by round name, values are team lists or match dicts
    Always returns a flat list of dicts with at least 'team1', 'team2', 'stage'.
    Old-format entries won't have match numbers, so they are scored by team name only.
    """
    if isinstance(ko, list):
        return ko
    if not isinstance(ko, dict):
        return []

    # Old format — map round keys to stage names and flatten
    ROUND_MAP = {
        "final":          "Final",
        "semi_final":     "Semi-Finals",
        "semifinal":      "Semi-Finals",
        "quarterfinal":   "Quarterfinals",
        "quarter_final":  "Quarterfinals",
        "final_16":       "Round of 16",
        "round_of_16":    "Round of 16",
        "round_of_32":    "Round of 32",
        "final_32":       "Round of 32",
    }
    flat = []
    for key, val in ko.items():
        stage = ROUND_MAP.get(key.lower(), key)
        teams = val if isinstance(val, list) else [val]
        # Pair up into pseudo-matches (team1, team2)
        for i in range(0, len(teams), 2):
            t1 = teams[i]   if i   < len(teams) else None
            t2 = teams[i+1] if i+1 < len(teams) else None
            flat.append({
                "match":  None,
                "stage":  stage,
                "team1":  t1 if isinstance(t1, str) else None,
                "team2":  t2 if isinstance(t2, str) else None,
            })
    return flat


def score_knockout(player_ko, result_ko) -> dict:
    player_ko = _normalise_ko(player_ko)
    result_ko = _normalise_ko(result_ko)
    def _mn(m): return m.get("match") or m.get("match_id")

    # Build result index — by match number when available, always by stage
    results_by_match = {}
    result_teams_by_stage = {}
    result_pairs_by_stage = {}   # stage → [(t1,t2), ...] for spot checking

    for m in result_ko:
        mn = _mn(m)
        if mn:
            results_by_match[mn] = m
        s = m.get("stage", "")
        result_teams_by_stage.setdefault(s, set())
        result_pairs_by_stage.setdefault(s, [])
        if m.get("team1"): result_teams_by_stage[s].add(m["team1"])
        if m.get("team2"): result_teams_by_stage[s].add(m["team2"])
        result_pairs_by_stage[s].append((m.get("team1"), m.get("team2")))

    # Build prediction index
    pred_by_match = {}
    pred_pairs_by_stage = {}   # stage → [(t1,t2), ...]
    for m in player_ko:
        mn = _mn(m)
        if mn:
            pred_by_match[mn] = m
        s = m.get("stage", "")
        pred_pairs_by_stage.setdefault(s, [])
        pred_pairs_by_stage[s].append((m.get("team1"), m.get("team2")))

    correct_spot = 0
    correct_team = 0
    running      = []
    cumulative   = 0
    detail       = {}

    # Score by match number when possible (new format), else by stage (old format)
    if results_by_match:
        scored_items = [(mn, r, pred_by_match.get(mn)) for mn, r in sorted(results_by_match.items())]
    else:
        # Old format: score stage by stage, pair by pair
        scored_items = []
        for s, r_pairs in result_pairs_by_stage.items():
            p_pairs = pred_pairs_by_stage.get(s, [])
            for i, (r_t1, r_t2) in enumerate(r_pairs):
                p_t1, p_t2 = p_pairs[i] if i < len(p_pairs) else (None, None)
                scored_items.append((None, {"stage": s, "team1": r_t1, "team2": r_t2},
                                     {"stage": s, "team1": p_t1, "team2": p_t2}))

    for mn, r, p in scored_items:
        stage = r.get("stage", "")

        if p is None:
            running.append({"match": mn, "play_order": r.get("play_order", mn), "stage": stage, "cumulative": cumulative})
            continue

        r_t1, r_t2 = r.get("team1"), r.get("team2")
        p_t1, p_t2 = p.get("team1"), p.get("team2")

        spot1 = int(bool(p_t1 and p_t1 == r_t1))
        spot2 = int(bool(p_t2 and p_t2 == r_t2))
        spots = spot1 + spot2

        in_stage = result_teams_by_stage.get(stage, set())
        team1_ok = int(bool(p_t1 and p_t1 in in_stage))
        team2_ok = int(bool(p_t2 and p_t2 in in_stage))
        teams    = team1_ok + team2_ok

        correct_spot += spots
        correct_team += teams

        match_pts   = spots * CORRECT_SPOT_PTS + teams * CORRECT_TEAM_PTS
        cumulative += match_pts

        detail[mn or f"{stage}_{r_t1}"] = {
            "stage":        stage,
            "pred":         f"{p_t1} vs {p_t2}",
            "actual":       f"{r_t1} vs {r_t2}",
            "correct_spot": spots,
            "correct_team": teams,
            "match_pts":    match_pts,
        }
        running.append({
            "match":      mn,
            "play_order": r.get("play_order", mn),
            "stage":      stage,
            "match_pts":  match_pts,
            "cumulative": cumulative,
        })

    return {
        "points":        correct_spot * CORRECT_SPOT_PTS + correct_team * CORRECT_TEAM_PTS,
        "correct_spot":  correct_spot,
        "correct_team":  correct_team,
        "detail":        detail,
        "running":       running,
    }


# ---------------------------------------------------------------------------
# Final standings bonuses
# ---------------------------------------------------------------------------

def score_medals(player: dict, fasit: dict) -> dict:
    champion_pts = CHAMPION_BONUS if (
        player.get("world_champion") and
        fasit["world_champion"] and
        player["world_champion"] == fasit["world_champion"]
    ) else 0

    silver_pts = SILVER_BONUS if (
        player.get("runner_up") and
        fasit["runner_up"] and
        player["runner_up"] == fasit["runner_up"]
    ) else 0

    bronze_pts = BRONZE_BONUS if (
        player.get("third_place") and
        fasit["third_place"] and
        player["third_place"] == fasit["third_place"]
    ) else 0

    return {
        "points":        champion_pts + silver_pts + bronze_pts,
        "champion_pts":  champion_pts,
        "silver_pts":    silver_pts,
        "bronze_pts":    bronze_pts,
    }


# ---------------------------------------------------------------------------
# Backwards-compatible alias (used by similarity.py)
# ---------------------------------------------------------------------------

def score_champion(predicted: str | None, actual: str | None) -> int:
    """Returns champion bonus points. Kept for compatibility with similarity.py."""
    if predicted and actual and predicted == actual:
        return CHAMPION_BONUS
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def score(fasit_path: str = None,
          predictions_path: str = None,
          output_json: str = None,
          output_csv: str = None,
          output_fasit_json: str = None) -> None:

    root = project_root()

    fasit_path        = Path(fasit_path)        if fasit_path        else root / "fasit" / "world_cup_2026_fasit.xlsx"
    predictions_path  = Path(predictions_path)  if predictions_path  else root / "gData" / "predictions.json"
    output_json       = Path(output_json)       if output_json       else root / "gData" / "scores.json"
    output_csv        = Path(output_csv)        if output_csv        else root / "gData" / "scores.csv"
    output_fasit_json = Path(output_fasit_json) if output_fasit_json else root / "gData" / "fasit.json"

    if not fasit_path.exists():
        raise FileNotFoundError(
            f"Fasit file not found: {fasit_path}\n"
            "Place the filled results file at fasit/world_cup_2026_fasit.xlsx"
        )
    if not predictions_path.exists():
        raise FileNotFoundError(
            f"Predictions file not found: {predictions_path}\n"
            "Run scan_predictions.py first."
        )

    print(f"Reading fasit: {fasit_path.name}")
    fasit = read_fasit(fasit_path)
    print(f"  {len(fasit['group_stage']):2d} group stage results, "
          f"{len(fasit['knockout']):2d} knockout results")
    if fasit["world_champion"]:
        print(f"  Winner: {fasit['world_champion']}"
              + (f"  Runner-up: {fasit['runner_up']}" if fasit["runner_up"] else "")
              + (f"  3rd: {fasit['third_place']}"     if fasit["third_place"] else ""))

    with open(predictions_path, encoding="utf-8") as f:
        preds = json.load(f)

    print(f"\nScoring {len(preds['players'])} player(s)...\n")

    correct_answers_path = root / "fasit" / "correct_answers.json"
    correct_answers = None
    if correct_answers_path.exists():
        with open(correct_answers_path, encoding="utf-8") as f:
            ca = json.load(f)
        correct_answers = ca.get("correct_answers")
        filled = sum(1 for v in correct_answers.values() if v is not None)
        print(f"Loaded correct_answers.json ({filled}/{len(correct_answers)} answered)")
    else:
        print("No correct_answers.json found in fasit/ — qualitative scoring skipped")

    # Load qualitative answers keyed by excel_file stem (matches predictions.json player keys)
    qualitative_by_player = {}
    qualitative_path = root / "gData" / "qualitative.json"
    if qualitative_path.exists():
        with open(qualitative_path, encoding="utf-8") as f:
            qual = json.load(f)
        for resp in qual.get("responses", []):
            excel_file = resp.get("excel_file")
            if excel_file:
                stem = Path(excel_file).stem
                qualitative_by_player[stem] = resp
        print(f"Loaded qualitative.json ({len(qualitative_by_player)} responses matched by excel_file)")
    else:
        print("No qualitative.json found in gData/ — qualitative answers unavailable")

    scores = {}

    for player, data in preds["players"].items():
        gs     = score_group_stage(data["group_stage"], fasit["group_stage"])
        ko     = score_knockout(data["knockout"],       fasit["knockout"])
        medals = score_medals(data, fasit)
        abbr   = data.get("abbr")
        player_q_answers = qualitative_by_player.get(player)
        qs     = score_questions(player_q_answers, correct_answers)

        total = qs["points"] + gs["points"] + ko["points"] + medals["points"]

        scores[player] = {
            "total":          total,
            "max_possible":   MAX_POINTS,
            "pct_of_max":     round(total / MAX_POINTS * 100, 1),
            "questions":      qs,
            "group_stage":    gs,
            "knockout":       ko,
            "medals":         medals,
            "world_champion": data.get("world_champion"),
            "runner_up":      data.get("runner_up"),
            "third_place":    data.get("third_place"),
        }

        print(
            f"  {player:<30s}  {total:+6d} / {MAX_POINTS}  "
            f"({total/MAX_POINTS*100:.1f}%)  "
            f"qs={qs['points']:+4d}  "
            f"group={gs['points']:+6d}  "
            f"ko={ko['points']:+5d}  "
            f"medals={medals['points']:+4d}"
        )

    # --- JSON ---
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({"players": scores}, f, ensure_ascii=False, indent=2)

    # --- CSV (sorted by total) ---
    sorted_players = sorted(scores.items(), key=lambda x: -x[1]["total"])

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "rank", "player", "total", "pct_of_max",
            "question_pts", "group_pts", "ko_pts",
            "champion_pts", "silver_pts", "bronze_pts",
            "correct_outcome", "home_sq_err", "away_sq_err",
            "correct_spot", "correct_team",
            "predicted_champion", "predicted_runner_up", "predicted_third",
        ])
        for rank, (player, s) in enumerate(sorted_players, 1):
            writer.writerow([
                rank, player,
                s["total"], s["pct_of_max"],
                s["questions"]["points"],
                s["group_stage"]["points"],
                s["knockout"]["points"],
                s["medals"]["champion_pts"],
                s["medals"]["silver_pts"],
                s["medals"]["bronze_pts"],
                s["group_stage"]["correct_outcome"],
                s["group_stage"]["home_sq_err"],
                s["group_stage"]["away_sq_err"],
                s["knockout"]["correct_spot"],
                s["knockout"]["correct_team"],
                s["world_champion"] or "",
                s["runner_up"]      or "",
                s["third_place"]    or "",
            ])

    # --- fasit JSON ---
    with open(output_fasit_json, "w", encoding="utf-8") as f:
        json.dump(fasit, f, ensure_ascii=False, indent=2)

    print(f"\nWrote → {output_json}")
    print(f"Wrote → {output_csv}")
    print(f"Wrote → {output_fasit_json}")
    print(f"\nMax possible score: {MAX_POINTS} pts")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fasit_arg       = sys.argv[1] if len(sys.argv) > 1 else None
    predictions_arg = sys.argv[2] if len(sys.argv) > 2 else None
    score(fasit_arg, predictions_arg)
