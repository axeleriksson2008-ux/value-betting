"""Generate every candidate bet for every (probability source, market, bookmaker).

One bet per match, market, bookmaker and source: the outcome with the highest
value, kept if value >= 0 (thresholds are applied later).

Probability sources:
  model     our v2 model
  pinnacle  Pinnacle odds at the same time as the bet, margin removed (power method)
  combo     Pinnacle says value AND the model agrees (model value >= 0);
            value is the Pinnacle-based one
Book "best" = best price among named bookmakers (not the Max/Avg aggregates).

Bet timing: main leagues use the "early" odds (a few days before the match),
extra leagues only have closing odds. Betfair exchange (bfe) odds are reduced
for 5 % commission on winnings. CLV = odds * Pinnacle fair closing prob - 1
(for Asian handicap only when the closing line equals the bet line).
Odds more than 25 % above the average odds for the same outcome are treated
as data errors (e.g. a Max AH price of 22.0 where every book has 1.9).
"""

import numpy as np
import pandas as pd

from src.loaders import MARKET_BOOKS, MARKET_OUTCOMES
from src.markets import ah_expected_profit, ah_profit
from src.model import remove_margin
from src.ratings import goal_diff_dist, matrix_probs, score_matrices

EXCHANGE_COMMISSION = {"bfe": 0.05}
EXTRA_LEAGUES = {"ARG", "AUT", "BRA", "CHN", "DNK", "FIN", "IRL", "JPN", "MEX", "NOR",
                 "POL", "ROU", "RUS", "SWE", "SWZ", "USA"}


def model_outputs(pred: pd.DataFrame, rho_mode="fitted") -> tuple[pd.DataFrame, np.ndarray]:
    """1X2/OU probabilities and goal-difference distribution from lam_h, lam_a, rho."""
    ok = pred["lam_h"].notna().to_numpy()
    probs = pd.DataFrame(np.nan, index=pred.index, columns=["h", "d", "a", "o25", "u25"])
    gd = np.full((len(pred), 21), np.nan)
    if ok.any():
        rho = pred["rho"].to_numpy()[ok] if rho_mode == "fitted" else float(rho_mode)
        mats = score_matrices(pred["lam_h"].to_numpy()[ok], pred["lam_a"].to_numpy()[ok], rho)
        pr = matrix_probs(mats)
        for k in probs.columns:
            probs.loc[ok, k] = pr[k]
        gd[ok] = goal_diff_dist(mats)
    return probs, gd


def _timing(m: pd.DataFrame) -> np.ndarray:
    return np.where(m["league"].isin(EXTRA_LEAGUES), "close", "early")


OUTLIER_RATIO = 1.25  # odds > 25 % above the market average are treated as data errors


NAMED_BOOKS = {
    "1x2": ["b365", "bw", "iw", "wh", "vc", "bf", "bfe", "1xb", "bfd", "bmgm", "bv", "cl", "lb"],
    "ou25": ["b365", "bfe"],
    "ah": ["b365", "bfe"],
}


def _pick_best_named(m, timing, market, outcomes):
    """Best odds among named bookmakers (not the Max/Avg aggregates), per outcome."""
    stack = np.stack([_pick(m, timing, b, outcomes).to_numpy() for b in NAMED_BOOKS[market]])
    filled = np.where(np.isnan(stack), -np.inf, stack)
    best = filled.max(axis=0)
    best = np.where(np.isinf(best), np.nan, best)
    return pd.DataFrame(best, index=m.index, columns=outcomes)


def _pick(m, timing, book, outcomes):
    """Odds for this book at the bet timing, per row (data errors removed)."""
    out = {}
    for o in outcomes:
        early, close = m[f"{book}_early_{o}"].to_numpy(), m[f"{book}_close_{o}"].to_numpy()
        odds = np.where(timing == "early", early, close)
        avg = np.where(timing == "early", m[f"avg_early_{o}"], m[f"avg_close_{o}"])
        out[o] = np.where(odds > OUTLIER_RATIO * avg, np.nan, odds)  # NaN avg -> kept
    df = pd.DataFrame(out, index=m.index)
    c = EXCHANGE_COMMISSION.get(book)
    return 1 + (df - 1) * (1 - c) if c else df


def _fair(m, timing, outcomes):
    ps = _pick(m, timing, "ps", outcomes)
    return pd.DataFrame(remove_margin(ps.to_numpy()), index=m.index, columns=outcomes)


def _fair_close(m, outcomes):
    ps = m[[f"ps_close_{o}" for o in outcomes]].to_numpy()
    return pd.DataFrame(remove_margin(ps), index=m.index, columns=outcomes)


def candidate_bets(m: pd.DataFrame, probs: pd.DataFrame, gd: np.ndarray) -> pd.DataFrame:
    timing = _timing(m)
    frames = []
    for market, outcomes in MARKET_OUTCOMES.items():
        fair = _fair(m, timing, outcomes)
        fair_close = _fair_close(m, outcomes)
        if market == "ah":
            line = np.where(timing == "early", m["ah_line_early"], m["ah_line_close"])
            same_line = np.where(timing == "early", m["ah_line_early"] == m["ah_line_close"], True)
        for book in list(MARKET_BOOKS[market]) + ["best"]:
            if book == "best":
                odds = _pick_best_named(m, timing, market, outcomes)
            else:
                odds = _pick(m, timing, book, outcomes)
            if odds.isna().all().all():
                continue
            # value per outcome for each source
            if market == "ah":
                model_val = pd.DataFrame(
                    {o: ah_expected_profit(gd, line, odds[o].to_numpy(), o) for o in outcomes},
                    index=m.index)
            else:
                model_val = probs[outcomes] * odds - 1
            pin_val = fair * odds - 1
            sources = {"model": model_val}
            if book != "ps":
                sources["pinnacle"] = pin_val
                sources["combo"] = pin_val.where(model_val >= 0)
            for src, val in sources.items():
                v = val.to_numpy(dtype=float)
                valid = ~np.isnan(v).all(axis=1)
                if not valid.any():
                    continue
                best = np.full(len(v), -1)
                best[valid] = np.nanargmax(v[valid], axis=1)
                rows = np.flatnonzero(valid)
                bv = v[rows, best[rows]]
                keep = bv >= 0
                rows, cols, bv = rows[keep], best[rows][keep], bv[keep]
                if len(rows) == 0:
                    continue
                o_arr = np.array(outcomes)[cols]
                od = odds.to_numpy()[rows, cols]
                hg, ag = m["hg"].to_numpy()[rows], m["ag"].to_numpy()[rows]
                if market == "ah":
                    profit = np.array([ah_profit(hg[k], ag[k], line[rows[k]], od[k], o_arr[k])
                                       for k in range(len(rows))], dtype=float)
                    clv = od * fair_close.to_numpy()[rows, cols] - 1
                    clv = np.where(same_line[rows], clv, np.nan)
                else:
                    won = _won(hg, ag, o_arr)
                    profit = np.where(won, od - 1, -1.0)
                    clv = od * fair_close.to_numpy()[rows, cols] - 1
                frames.append(pd.DataFrame({
                    "row": m.index[rows], "date": m["date"].to_numpy()[rows],
                    "league": m["league"].to_numpy()[rows], "source": src, "market": market,
                    "book": book, "outcome": o_arr, "odds": od, "value": bv,
                    "profit": profit, "clv": clv,
                }))
    return pd.concat(frames, ignore_index=True)


def _won(hg, ag, outcome):
    total = hg + ag
    return np.select(
        [outcome == "h", outcome == "d", outcome == "a", outcome == "o25", outcome == "u25"],
        [hg > ag, hg == ag, hg < ag, total > 2, total <= 2], default=False)
