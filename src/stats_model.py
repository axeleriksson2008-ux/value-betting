"""Models for match statistics: shots, shots on target, fouls, corners and cards.

Team level:  count for a team ~ Negative Binomial(mean = lambda, dispersion alpha)
  lambda_home = base * home_adv * att[home] * dfn[away]
  lambda_away = base *            att[away] * dfn[home]
  att = how much a team produces (e.g. its own shots / fouls committed)
  dfn = how much opponents produce against it (shots conceded / fouls drawn)
  Fitted with the same time-weighted, regularised method as goal model v2.
Match total: total ~ Negative Binomial(mean = lambda_home + lambda_away, alpha_total).
  A separate alpha_total because the two teams' counts are correlated
  (an aggressive match gives both teams more cards).

Negative binomial: variance = mean + alpha * mean^2 (alpha = 0 -> Poisson).
Cards = yellow + red (how bookmakers count cards differs, check their rules).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

from src import config
from src.ratings import fit_ratings
from src.walkforward import Params, predict_all

STATS = {
    "shots": ("shots_h", "shots_a"),
    "sot": ("sot_h", "sot_a"),
    "fouls": ("fouls_h", "fouls_a"),
    "corners": ("corners_h", "corners_a"),
    "cards": ("cards_h", "cards_a"),
}
STAT_NAME = {"shots": "Skott", "sot": "Skott på mål", "fouls": "Fouls (frisparkar)",
             "corners": "Hörnor", "cards": "Kort (gula + röda)"}
RATINGS_PATH = config.ROOT / "data" / "stat_ratings.json"


def add_cards(m: pd.DataFrame) -> pd.DataFrame:
    m = m.copy()
    m["cards_h"] = m["yellow_h"] + m["red_h"].fillna(0)
    m["cards_a"] = m["yellow_a"] + m["red_a"].fillna(0)
    return m


def stat_frame(m: pd.DataFrame, stat: str) -> pd.DataFrame:
    """Matches with this statistic, the counts placed in hg/ag so the goal machinery can be reused."""
    hcol, acol = STATS[stat]
    d = m.dropna(subset=[hcol, acol])
    return d.assign(hg=d[hcol].astype(float), ag=d[acol].astype(float))


# ---------------------------------------------------------------- distributions

def _nb(mean, alpha):
    """scipy nbinom parameters (n, p) for mean and dispersion alpha."""
    alpha = max(float(alpha), 1e-9)
    n = 1.0 / alpha
    return n, n / (n + np.asarray(mean, float))


def pmf(k, mean, alpha):
    if alpha <= 1e-9:
        return poisson.pmf(k, mean)
    n, p = _nb(mean, alpha)
    return nbinom.pmf(k, n, p)


def cdf(k, mean, alpha):
    if alpha <= 1e-9:
        return poisson.cdf(k, mean)
    n, p = _nb(mean, alpha)
    return nbinom.cdf(k, n, p)


def over_under(line: float, mean: float, alpha: float) -> dict:
    """P(over), P(under) and P(push) for a line like 4.5 (no push) or 10 (push possible)."""
    if float(line).is_integer():
        k = int(line)
        p_under = float(cdf(k - 1, mean, alpha))
        p_push = float(pmf(k, mean, alpha))
    else:
        p_under = float(cdf(int(np.floor(line)), mean, alpha))
        p_push = 0.0
    return {"over": 1 - p_under - p_push, "under": p_under, "push": p_push}


def fair_odds_with_push(p_win: float, p_push: float) -> float:
    """Odds at which the bet breaks even when a push returns the stake."""
    return (1 - p_push) / p_win if p_win > 0 else float("inf")


def estimate_alpha(y, mean) -> float:
    """Method of moments: E[(y - mu)^2 - mu] = alpha * E[mu^2]. Negative -> 0 (Poisson)."""
    y, mean = np.asarray(y, float), np.asarray(mean, float)
    ok = ~(np.isnan(y) | np.isnan(mean))
    y, mean = y[ok], mean[ok]
    if len(y) < 50:
        return 0.0
    return float(max(((y - mean) ** 2 - mean).sum() / (mean ** 2).sum(), 0.0))


# ---------------------------------------------------------------- walk-forward

def walk_forward(m: pd.DataFrame, stat: str, p: Params, start=None, end=None) -> pd.DataFrame:
    """Rolling expected counts (lam_h, lam_a) for every match with this statistic."""
    d = stat_frame(m, stat)
    pred = predict_all(d, p, start, end)
    out = d[["date", "league", "home", "away", "hg", "ag"]].copy()
    out[["lam_h", "lam_a"]] = pred[["lam_h", "lam_a"]].to_numpy()
    return out


def log_score(y, mean, alpha) -> np.ndarray:
    return np.log(np.clip(pmf(np.asarray(y), np.asarray(mean), alpha), 1e-12, None))


# ---------------------------------------------------------------- current ratings for the app

def current_ratings(m: pd.DataFrame, p: Params, alphas: dict, as_of=None) -> dict:
    """Ratings per league and statistic using all matches up to `as_of` (default: latest)."""
    as_of = pd.Timestamp(as_of) if as_of is not None else m["date"].max() + pd.Timedelta(days=1)
    out = {"as_of": str(as_of.date()), "half_life": p.half_life, "kappa": p.kappa, "leagues": {}}
    for stat in STATS:
        if not set(STATS[stat]) <= set(m.columns):
            continue
        d = stat_frame(m, stat)
        for league, lg in d.groupby("league"):
            lg = lg[(lg["date"] < as_of) & (lg["date"] >= as_of - pd.Timedelta(days=p.max_window_days))]
            if len(lg) < p.min_train_matches:
                continue
            teams = sorted(set(lg["home"]) | set(lg["away"]))
            idx = {t: i for i, t in enumerate(teams)}
            age = (as_of - lg["date"]).dt.days.to_numpy()
            w = 0.5 ** (age / p.half_life)
            r = fit_ratings(lg["home"].map(idx).to_numpy(), lg["away"].map(idx).to_numpy(),
                            lg["hg"].to_numpy(), lg["ag"].to_numpy(), w, len(teams), kappa=p.kappa)
            last_season = lg["season"].max()
            current = set(lg.loc[lg["season"] == last_season, "home"]) | set(lg.loc[lg["season"] == last_season, "away"])
            a = alphas.get(stat, {}).get(league) or alphas.get(stat, {}).get("_all", {})
            L = out["leagues"].setdefault(league, {"teams": sorted(current)})
            L[stat] = {
                "base": r.base, "home_adv": r.home_adv,
                "att": {t: float(r.att[idx[t]]) for t in teams},
                "dfn": {t: float(r.dfn[idx[t]]) for t in teams},
                "alpha_team": a.get("team", 0.0), "alpha_total": a.get("total", 0.0),
            }
    return out


def save_ratings(ratings: dict, path: Path | None = None) -> None:
    Path(path or RATINGS_PATH).write_text(json.dumps(ratings, indent=1, ensure_ascii=False))


def load_ratings(path: Path | None = None) -> dict | None:
    path = Path(path or RATINGS_PATH)
    return json.loads(path.read_text()) if path.exists() else None


def match_means(r: dict, league: str, stat: str, home: str, away: str) -> tuple[float, float]:
    s = r["leagues"][league][stat]
    lam_h = s["base"] * s["home_adv"] * s["att"].get(home, 1.0) * s["dfn"].get(away, 1.0)
    lam_a = s["base"] * s["att"].get(away, 1.0) * s["dfn"].get(home, 1.0)
    return lam_h, lam_a


def market_prob(r: dict, league: str, stat: str, home: str, away: str, scope: str,
                line: float) -> dict:
    """scope: 'total', 'home' or 'away'. Returns over/under/push probabilities and the mean."""
    s = r["leagues"][league][stat]
    lam_h, lam_a = match_means(r, league, stat, home, away)
    if scope == "total":
        mean, alpha = lam_h + lam_a, s["alpha_total"]
    else:
        mean, alpha = (lam_h if scope == "home" else lam_a), s["alpha_team"]
    return {"mean": mean, **over_under(line, mean, alpha)}
