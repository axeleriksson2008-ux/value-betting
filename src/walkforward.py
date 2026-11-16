"""Walk-forward (rolling) predictions for model v2, one league at a time.

For each match day D in [start, end):
  train = same league, date < D, date >= D - max_window_days
  weights = 0.5 ** (age_in_days / half_life)
  -> fit ratings (warm-started from the previous day) -> predict day D.
Never uses matches from day D or later (tested in tests/test_walkforward.py).

Periods used for the phase 2 study:
  VALIDATION: 2020-07-01 .. 2023-06-30  (choose parameters and strategies here)
  TEST:       2023-07-01 .. end         (only look once choices are frozen)
"""

from dataclasses import dataclass, asdict
from multiprocessing import Pool

import numpy as np
import pandas as pd

from src.ratings import fit_ratings, fit_rho

VAL_START, TEST_START = pd.Timestamp("2020-07-01"), pd.Timestamp("2023-07-01")


@dataclass(frozen=True)
class Params:
    half_life: float = 180.0      # days
    kappa: float = 5.0            # phantom matches at prior level
    promoted: float = 1.0         # prior att for teams new to the league this season (dfn = 1/x)
    max_window_days: int = 1095
    min_team_games: int = 3
    min_train_matches: int = 100


def predict_league(lg: pd.DataFrame, p: Params, start=None, end=None) -> pd.DataFrame:
    """Return DataFrame (index = lg.index) with lam_h, lam_a, rho for days in [start, end)."""
    lg = lg.sort_values("date")
    teams = pd.Index(sorted(set(lg["home"]) | set(lg["away"])))
    n = len(teams)
    h = teams.get_indexer(lg["home"])
    a = teams.get_indexer(lg["away"])
    hg, ag = lg["hg"].to_numpy(float), lg["ag"].to_numpy(float)
    dates = lg["date"].to_numpy()
    seasons = lg["season"].to_numpy()

    # teams per season, to recognise promoted / new teams
    season_teams = {s: set(np.r_[h[seasons == s], a[seasons == s]]) for s in np.unique(seasons)}

    out = np.full((len(lg), 3), np.nan)
    days = np.unique(dates)
    if start is not None:
        days = days[days >= np.datetime64(start)]
    if end is not None:
        days = days[days < np.datetime64(end)]
    init = None
    for day in days:
        lo = np.searchsorted(dates, day - np.timedelta64(p.max_window_days, "D"))
        hi = np.searchsorted(dates, day)  # first index with date >= day -> excluded
        if hi - lo < p.min_train_matches:
            init = None
            continue
        sl = slice(lo, hi)
        age = (day - dates[sl]) / np.timedelta64(1, "D")
        w = 0.5 ** (age / p.half_life)

        today = np.flatnonzero(dates == day)
        season = seasons[today[0]]
        prior_att = np.ones(n)
        prev = season_teams.get(season - 1)
        if prev is not None and p.promoted != 1.0:
            new = np.array(sorted(season_teams[season] - prev), dtype=int)
            prior_att[new] = p.promoted
        prior_dfn = 1.0 / prior_att

        r = fit_ratings(h[sl], a[sl], hg[sl], ag[sl], w, n, kappa=p.kappa,
                        prior_att=prior_att, prior_dfn=prior_dfn, init=init, n_iter=200)
        init = r
        lam_h_tr, lam_a_tr = r.expected_goals(h[sl], a[sl])
        rho = fit_rho(lam_h_tr, lam_a_tr, hg[sl], ag[sl], w)

        games = np.bincount(h[sl], minlength=n) + np.bincount(a[sl], minlength=n)
        for i in today:
            if min(games[h[i]], games[a[i]]) < p.min_team_games:
                continue
            lh, la = r.expected_goals(h[i], a[i])
            out[i] = (lh, la, rho)
    return pd.DataFrame(out, index=lg.index, columns=["lam_h", "lam_a", "rho"])


def _job(args):
    lg, p, start, end = args
    return predict_league(lg, p, start, end)


def predict_all(matches: pd.DataFrame, p: Params, start=None, end=None, processes=4) -> pd.DataFrame:
    """Run predict_league for every league in parallel."""
    jobs = [(lg, p, start, end) for _, lg in matches.groupby("league")]
    with Pool(processes) as pool:
        parts = pool.map(_job, jobs)
    return pd.concat(parts).reindex(matches.index)


def params_dict(p: Params) -> dict:
    return asdict(p)
