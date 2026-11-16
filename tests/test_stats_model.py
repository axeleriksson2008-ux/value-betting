import math

import numpy as np
import pandas as pd
import pytest

from src import stats_model as sm
from src.walkforward import Params


def test_over_under_poisson_hand_calc():
    # alpha 0 -> Poisson(4): P(X <= 4)
    under = sum(math.exp(-4) * 4 ** k / math.factorial(k) for k in range(5))
    p = sm.over_under(4.5, 4.0, 0.0)
    assert p["under"] == pytest.approx(under)
    assert p["over"] == pytest.approx(1 - under)
    assert p["push"] == 0


def test_whole_line_has_push():
    p = sm.over_under(4, 4.0, 0.0)
    assert p["push"] == pytest.approx(math.exp(-4) * 4 ** 4 / 24)
    assert p["over"] + p["under"] + p["push"] == pytest.approx(1)
    # break-even odds with push: (1 - push) / p_over
    assert sm.fair_odds_with_push(p["over"], p["push"]) == pytest.approx((1 - p["push"]) / p["over"])


def test_negative_binomial_mean_and_variance():
    mean, alpha = 10.0, 0.1
    k = np.arange(0, 200)
    probs = sm.pmf(k, mean, alpha)
    assert probs.sum() == pytest.approx(1, abs=1e-9)
    assert (k * probs).sum() == pytest.approx(mean)
    var = ((k - mean) ** 2 * probs).sum()
    assert var == pytest.approx(mean + alpha * mean ** 2)
    # more dispersion -> fatter tails
    assert sm.over_under(15.5, mean, 0.1)["over"] > sm.over_under(15.5, mean, 0.0)["over"]


def test_estimate_alpha_recovers_dispersion():
    rng = np.random.default_rng(0)
    mean = rng.uniform(3, 8, 20000)
    alpha = 0.15
    n = 1 / alpha
    y = rng.negative_binomial(n, n / (n + mean))
    assert sm.estimate_alpha(y, mean) == pytest.approx(alpha, rel=0.15)
    assert sm.estimate_alpha(rng.poisson(mean), mean) == pytest.approx(0, abs=0.01)


def _league(n_rounds=12, seed=1):
    rng = np.random.default_rng(seed)
    teams = list("ABCDEF")
    produce = dict(zip(teams, [7, 6, 5, 5, 4, 3]))  # corners per match, roughly
    rows, day = [], 0
    for _ in range(n_rounds):
        for h in teams:
            for a in teams:
                if h != a:
                    day += 1
                    rows.append({"date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=day // 3),
                                 "league": "X", "season": 2024, "home": h, "away": a,
                                 "corners_h": rng.poisson(produce[h] * 1.1), "corners_a": rng.poisson(produce[a]),
                                 "yellow_h": 1, "yellow_a": 2, "red_h": 0, "red_a": np.nan})
    return pd.DataFrame(rows)


def test_current_ratings_and_market_prob():
    m = _league()
    p = Params(half_life=365, kappa=2, min_train_matches=20)
    r = sm.current_ratings(m, p, {"corners": {"_all": {"team": 0.0, "total": 0.05}}})
    lam_h, lam_a = sm.match_means(r, "X", "corners", "A", "F")
    assert lam_h > lam_a  # strong corner team at home vs weak
    res = sm.market_prob(r, "X", "corners", "A", "F", "total", 9.5)
    assert res["mean"] == pytest.approx(lam_h + lam_a)
    assert res["over"] + res["under"] == pytest.approx(1)
    assert set(r["leagues"]["X"]["teams"]) == set("ABCDEF")


def test_cards_and_stat_frame():
    m = sm.add_cards(_league(1))
    assert (m["cards_h"] == 1).all() and (m["cards_a"] == 2).all()  # NaN red counts as 0
    d = sm.stat_frame(m, "corners")
    assert (d["hg"] == d["corners_h"]).all()
