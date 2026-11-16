"""Poisson model for football matches + betting helpers.

Model (same idea as the Excel sheet):
  league averages:  avg_hg = home goals per match, avg_ag = away goals per match
  home attack   = (home goals scored per home match)    / avg_hg
  home defence  = (home goals conceded per home match)  / avg_ag
  away attack   = (away goals scored per away match)    / avg_ag
  away defence  = (away goals conceded per away match)  / avg_hg
  lambda_home = avg_hg * home_attack(home team) * away_defence(away team)
  lambda_away = avg_ag * away_attack(away team) * home_defence(home team)

Regression to the league average (k): each team gets k extra "phantom"
matches played exactly at league average, so
  strength = (goals + k * avg) / ((games + k) * avg)
With 0 games -> 1.0 (average team), with many games -> the team's own rate.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import poisson

MAX_GOALS = 10  # score matrix covers 0..10 goals per team


# ---------------------------------------------------------------- probabilities

def score_matrix(lam_home: float, lam_away: float, max_goals: int = MAX_GOALS) -> np.ndarray:
    """P(home scores i, away scores j) assuming independent Poisson goals.

    The last row/column absorbs the tail (>= max_goals) so the matrix sums to 1.
    """
    goals = np.arange(max_goals + 1)
    ph = poisson.pmf(goals, lam_home)
    pa = poisson.pmf(goals, lam_away)
    ph[-1] += 1 - ph.sum()
    pa[-1] += 1 - pa.sum()
    return np.outer(ph, pa)


def market_probs(lam_home: float, lam_away: float) -> dict:
    """1X2, over/under 2.5 and BTTS probabilities from the expected goals."""
    m = score_matrix(lam_home, lam_away)
    i, j = np.indices(m.shape)
    over = m[(i + j) > 2].sum()
    return {
        "h": m[i > j].sum(),
        "d": m[i == j].sum(),
        "a": m[i < j].sum(),
        "o25": over,
        "u25": 1 - over,
        "btts_yes": m[(i > 0) & (j > 0)].sum(),
        "btts_no": 1 - m[(i > 0) & (j > 0)].sum(),
    }


# ---------------------------------------------------------------- team strengths

@dataclass
class LeagueStrengths:
    avg_hg: float
    avg_ag: float
    home_att: dict
    home_def: dict
    away_att: dict
    away_def: dict
    games: dict  # total matches per team in the training data

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        """Expected goals; unknown teams (e.g. promoted) get average strength 1.0."""
        lam_h = self.avg_hg * self.home_att.get(home, 1.0) * self.away_def.get(away, 1.0)
        lam_a = self.avg_ag * self.away_att.get(away, 1.0) * self.home_def.get(home, 1.0)
        return lam_h, lam_a


def fit_strengths(train: pd.DataFrame, k: float = 5.0) -> LeagueStrengths:
    """Estimate strengths from past matches (columns home, away, hg, ag).

    `train` must only contain matches played BEFORE the match we predict.
    """
    avg_hg = train["hg"].mean()
    avg_ag = train["ag"].mean()

    home = train.groupby("home").agg(n=("hg", "size"), scored=("hg", "sum"), conceded=("ag", "sum"))
    away = train.groupby("away").agg(n=("ag", "size"), scored=("ag", "sum"), conceded=("hg", "sum"))

    def shrink(goals, n, avg):
        return (goals + k * avg) / ((n + k) * avg)

    games = home["n"].add(away["n"], fill_value=0)
    return LeagueStrengths(
        avg_hg=avg_hg,
        avg_ag=avg_ag,
        home_att=shrink(home["scored"], home["n"], avg_hg).to_dict(),
        home_def=shrink(home["conceded"], home["n"], avg_ag).to_dict(),
        away_att=shrink(away["scored"], away["n"], avg_ag).to_dict(),
        away_def=shrink(away["conceded"], away["n"], avg_hg).to_dict(),
        games=games.to_dict(),
    )


# ---------------------------------------------------------------- betting helpers

def fair_odds(p: float) -> float:
    """Odds with no margin: 1 / probability."""
    return 1.0 / p


def remove_margin(odds) -> np.ndarray:
    """Bookmaker odds -> fair probabilities (proportional method).

    Implied probabilities 1/odds sum to more than 1 (the margin);
    divide each by the sum so they sum to exactly 1.
    """
    implied = 1.0 / np.asarray(odds, dtype=float)
    return implied / implied.sum(axis=-1, keepdims=True)


def value(p: float, odds: float) -> float:
    """Expected profit per unit staked: p * odds - 1 (0.05 = +5 %)."""
    return p * odds - 1.0


def kelly_fraction(p: float, odds: float, fraction: float = 0.25, cap: float = 0.02) -> float:
    """Share of bankroll to stake: fractional Kelly, never negative, capped.

    Full Kelly = (p * odds - 1) / (odds - 1). We use a quarter of it
    and at most `cap` (2 %) of the bankroll.
    """
    full = (p * odds - 1.0) / (odds - 1.0)
    return float(min(max(full * fraction, 0.0), cap))
