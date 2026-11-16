import math

import numpy as np
import pytest

from src.markets import ah_expected_profit, ah_profit
from src.model import market_probs
from src.ratings import (dc_tau, fit_ratings, fit_rho, goal_diff_dist, matrix_probs,
                         score_matrices)


# ------------------------------------------------------------ ratings

def _simulate(n_rounds=60, seed=0):
    """Fake league with known strengths, double round robin repeated."""
    rng = np.random.default_rng(seed)
    true_att = np.array([1.4, 1.2, 1.0, 1.0, 0.8, 0.6])
    true_dfn = np.array([0.7, 0.9, 1.0, 1.0, 1.1, 1.3])
    base, home_adv = 1.2, 1.3
    h, a = [], []
    for _ in range(n_rounds):
        for i in range(6):
            for j in range(6):
                if i != j:
                    h.append(i), a.append(j)
    h, a = np.array(h), np.array(a)
    hg = rng.poisson(base * home_adv * true_att[h] * true_dfn[a])
    ag = rng.poisson(base * true_att[a] * true_dfn[h])
    return h, a, hg, ag, true_att, true_dfn


def test_fit_recovers_true_strengths():
    h, a, hg, ag, true_att, true_dfn = _simulate()
    r = fit_ratings(h, a, hg, ag, np.ones(len(h)), 6, kappa=0.0)
    # Overall scale is shared between base/att/dfn: compare relative strengths
    assert r.att / r.att.mean() == pytest.approx(true_att / true_att.mean(), rel=0.08)
    assert r.dfn / r.dfn.mean() == pytest.approx(true_dfn / true_dfn.mean(), rel=0.08)
    assert r.home_adv == pytest.approx(1.3, rel=0.05)
    lam_h, lam_a = r.expected_goals(h, a)
    assert lam_h.sum() == pytest.approx(hg.sum(), rel=1e-3)  # fitted totals match data
    assert lam_a.sum() == pytest.approx(ag.sum(), rel=1e-3)


def test_prior_pulls_to_prior_mean_with_no_data():
    h, a, hg, ag, *_ = _simulate(n_rounds=2)
    prior_att = np.ones(7)
    prior_att[6] = 0.8  # team 6 never played
    r = fit_ratings(h, a, hg, ag, np.ones(len(h)), 7, kappa=5.0, prior_att=prior_att)
    assert r.att[6] == pytest.approx(0.8)
    assert r.dfn[6] == pytest.approx(1.0)


def test_more_kappa_means_less_extreme():
    h, a, hg, ag, *_ = _simulate(n_rounds=1)
    w = np.ones(len(h))
    spread_low = np.ptp(fit_ratings(h, a, hg, ag, w, 6, kappa=1).att)
    spread_high = np.ptp(fit_ratings(h, a, hg, ag, w, 6, kappa=20).att)
    assert spread_high < spread_low


# ------------------------------------------------------------ Dixon-Coles & matrices

def test_rho_zero_equals_plain_poisson():
    m = score_matrices([1.5], [1.1], rho=0.0, max_goals=10)
    p = matrix_probs(m)
    ref = market_probs(1.5, 1.1)
    for k in ["h", "d", "a", "o25", "btts_yes"]:
        assert p[k][0] == pytest.approx(ref[k])


def test_negative_rho_adds_draws():
    m0 = score_matrices([1.4], [1.1], rho=0.0)
    m1 = score_matrices([1.4], [1.1], rho=-0.1)
    assert m1.sum() == pytest.approx(1.0)
    assert m1[0, 0, 0] > m0[0, 0, 0] and m1[0, 1, 1] > m0[0, 1, 1]
    assert matrix_probs(m1)["d"][0] > matrix_probs(m0)["d"][0]


def test_dc_tau_values():
    assert dc_tau(0, 0, 1.5, 1.0, 0.1) == pytest.approx(1 - 1.5 * 1.0 * 0.1)
    assert dc_tau(1, 1, 1.5, 1.0, 0.1) == pytest.approx(0.9)
    assert dc_tau(2, 1, 1.5, 1.0, 0.1) == pytest.approx(1.0)


def test_fit_rho_finds_negative_rho_when_too_many_draws():
    rng = np.random.default_rng(3)
    n = 4000
    lam_h, lam_a = np.full(n, 1.3), np.full(n, 1.0)
    hg, ag = rng.poisson(lam_h), rng.poisson(lam_a)
    # turn some 1-0 / 0-1 into 0-0 / 1-1 -> more draws than Poisson
    flip = (rng.random(n) < 0.3) & (hg + ag == 1)
    hg[flip] = ag[flip] = (rng.random(flip.sum()) < 0.5).astype(int)
    assert fit_rho(lam_h, lam_a, hg, ag, np.ones(n)) < -0.03


def test_goal_diff_dist():
    m = score_matrices([1.5, 0.8], [1.1, 2.0])
    gd = goal_diff_dist(m)
    p = matrix_probs(m)
    assert gd.sum(axis=1) == pytest.approx([1, 1])
    g = (gd.shape[1] - 1) // 2
    assert gd[:, g] == pytest.approx(p["d"])          # diff 0 = draw
    assert gd[:, g + 1:].sum(axis=1) == pytest.approx(p["h"])


# ------------------------------------------------------------ Asian handicap

@pytest.mark.parametrize("hg,ag,line,side,expected", [
    (1, 0, -0.5, "ahh", 0.9),      # home wins by 1 on -0.5: win
    (1, 1, -0.5, "ahh", -1.0),     # draw on -0.5: lose
    (1, 1, 0.0, "ahh", 0.0),       # draw on 0: push
    (2, 1, -1.0, "ahh", 0.0),      # win by 1 on -1: push
    (2, 1, -0.75, "ahh", 0.45),    # half win (-0.5), half push (-1.0)
    (1, 1, -0.25, "ahh", -0.5),    # half push (0), half lose (-0.5)
    (1, 1, -0.25, "aha", 0.45),    # away gets +0.25: half win, half push
    (0, 2, -0.5, "aha", 0.9),      # away wins
])
def test_ah_profit(hg, ag, line, side, expected):
    assert float(ah_profit(hg, ag, line, 1.9, side)) == pytest.approx(expected)


def test_ah_expected_profit_matches_settlement():
    m = score_matrices([1.6], [1.0], rho=-0.05)
    gd = goal_diff_dist(m)
    for line in [-1.25, -0.75, -0.5, 0.0, 0.25]:
        for side in ["ahh", "aha"]:
            ev = ah_expected_profit(gd, line, 1.95, side)[0]
            i, j = np.indices(m.shape[1:])
            brute = (m[0] * ah_profit(i, j, line, 1.95, side)).sum()
            assert ev == pytest.approx(brute)


def test_ah_level_line_equals_1x2():
    # line -0.5 home bet wins exactly when home wins
    m = score_matrices([1.4], [1.2])
    gd = goal_diff_dist(m)
    p_home = matrix_probs(m)["h"][0]
    assert ah_expected_profit(gd, -0.5, 2.0, "ahh")[0] == pytest.approx(p_home * 2 - 1)


def test_ah_missing_line_or_odds_gives_nan():
    gd = goal_diff_dist(score_matrices([1.4, 1.4], [1.2, 1.2]))
    ev = ah_expected_profit(gd, [np.nan, -0.5], [1.9, np.nan], "ahh")
    assert np.isnan(ev).all()
    assert np.isnan(ah_profit(1, 0, np.nan, 1.9, "ahh"))
