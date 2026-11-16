"""Daily update of data/stat_ratings.json with the latest results (used by GitHub Actions).

Downloads the last three seasons of the main leagues from football-data.co.uk,
refits the team ratings for shots, shots on target, fouls, corners and cards
with the parameters and dispersions chosen in src.stats_eval (kept in the JSON).
"""

import tempfile
from datetime import date
from pathlib import Path

import requests

from src import stats_model as sm
from src.loaders import load_all
from src.walkforward import Params

LEAGUES = ["E0", "E1", "E2", "E3", "SC0", "SC1", "SC2", "SC3", "D1", "D2", "I1", "I2", "SP1", "SP2",
           "F1", "F2", "N1", "B1", "P1", "T1", "G1"]


def season_codes(today: date, n: int = 3) -> list[str]:
    """football-data season folders, e.g. 2627 for 2026/27 (season starts in July)."""
    start = today.year if today.month >= 7 else today.year - 1
    return [f"{(y % 100):02d}{((y + 1) % 100):02d}" for y in range(start - n + 1, start + 1)]


def download(folder: Path, today: date) -> None:
    for code in season_codes(today):
        for lg in LEAGUES:
            r = requests.get(f"https://www.football-data.co.uk/mmz4281/{code}/{lg}.csv", timeout=60)
            if r.ok and not r.content.lstrip().startswith(b"<"):
                (folder / f"{lg}_{code}.csv").write_bytes(r.content)


def main():
    old = sm.load_ratings()
    if not old:
        raise SystemExit("Run python -m src.stats_eval first (it chooses parameters and dispersion).")
    with tempfile.TemporaryDirectory() as tmp:
        download(Path(tmp), date.today())
        m = sm.add_cards(load_all(Path(tmp)))
    merged = None
    for stat, prm in old["by_stat_params"].items():
        alphas = {stat: {lg: {"team": d[stat]["alpha_team"], "total": d[stat]["alpha_total"]}
                         for lg, d in old["leagues"].items() if stat in d}}
        r = sm.current_ratings(m, Params(half_life=prm["half_life"], kappa=prm["kappa"]), alphas)
        r["leagues"] = {lg: {k: v for k, v in d.items() if k in ("teams", stat)} for lg, d in r["leagues"].items()}
        if merged is None:
            merged = r
        else:
            for lg, d in r["leagues"].items():
                merged["leagues"].setdefault(lg, {"teams": d["teams"]}).update({stat: d[stat]} if stat in d else {})
    merged["by_stat_params"] = old["by_stat_params"]
    sm.save_ratings(merged)
    print(f"Updated ratings as of {merged['as_of']} for {len(merged['leagues'])} leagues")


if __name__ == "__main__":
    main()
