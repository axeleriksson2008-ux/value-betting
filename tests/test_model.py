import math

import numpy as np
import pandas as pd
import pytest

from src.model import (fair_odds, fit_strengths, kelly_fraction, market_probs,
                       remove_margin, score_matrix, value)


def test_score_matrix_sums_to_one():
    assert score_matrix(1.5, 1.1).sum() == pytest.approx(1.0)


def test_zero_zero_probability_matches_hand_calculation():
    # P(0-0) = e^-1.5 * e^-1.1
    assert score_matrix(1.5, 1.1)[0, 0] == pytest.approx(math.exp(-1.5) * math.exp(-1.1))


def test_1x2_and_totals_consistent():
    p = market_probs(1.5, 1.1)
    assert p["h"] + p["d"] + p["a"] == pytest.approx(1.0)
    assert p["o25"] + p["u25"] == pytest.approx(1.0)
    # Hand calculation: P(total <= 2) for Poisson(2.6) since sum of Poissons is Poisson
    lam = 2.6
    under = sum(math.exp(-lam) * lam**n / math.factorial(n) for n in range(3))
    assert p["u25"] == pytest.approx(under, abs=1e-9)
    # BTTS yes = (1 - P(home 0)) * (1 - P(away 0))
    assert p["btts_yes"] == pytest.approx((1 - math.exp(-1.5)) * (1 - math.exp(-1.1)))


def test_equal_teams_symmetric():
    p = market_probs(1.3, 1.3)
    assert p["h"] == pytest.approx(p["a"])


def test_fair_odds_and_value():
    assert fair_odds(0.5) == 2.0
    assert value(0.5, 2.2) == pytest.approx(0.10)
    assert value(0.5, 2.0) == pytest.approx(0.0)


def test_remove_margin():
    probs = remove_margin([1.9, 1.9])
    assert probs == pytest.approx([0.5, 0.5])
    probs = remove_margin([2.0, 3.5, 4.0])
    assert probs.sum() == pytest.approx(1.0)
    assert probs[0] == pytest.approx((1 / 2.0) / (1 / 2.0 + 1 / 3.5 + 1 / 4.0))


def test_remove_margin_rowwise():
    probs = remove_margin(np.array([[1.9, 1.9], [1.5, 2.5]]))
    assert probs.sum(axis=1) == pytest.approx([1.0, 1.0])


def test_kelly():
    # p=0.5, odds 2.2: full Kelly = 0.1/1.2 = 0.0833, quarter = 0.0208 -> capped at 0.02
    assert kelly_fraction(0.5, 2.2) == pytest.approx(0.02)
    assert kelly_fraction(0.5, 2.2, cap=1.0) == pytest.approx(0.1 / 1.2 / 4)
    assert kelly_fraction(0.4, 2.0) == 0.0  # negative value -> no bet


def test_strengths_average_team_is_one():
    # Two teams, identical results -> both exactly average
    train = pd.DataFrame({"home": ["A", "B"], "away": ["B", "A"], "hg": [2, 2], "ag": [1, 1]})
    s = fit_strengths(train, k=0)
    assert s.home_att["A"] == pytest.approx(1.0)
    assert s.expected_goals("A", "B") == pytest.approx((2.0, 1.0))


def test_strengths_hand_calculation_and_shrinkage():
    train = pd.DataFrame({
        "home": ["A", "B", "A", "B"], "away": ["B", "A", "B", "A"],
        "hg": [3, 1, 3, 1], "ag": [0, 1, 0, 1],
    })
    # avg_hg = 2, avg_ag = 0.5. A scores 3 per home match -> attack 1.5
    s0 = fit_strengths(train, k=0)
    assert s0.home_att["A"] == pytest.approx(1.5)
    # with k=2 phantom matches: (6 + 2*2) / ((2+2)*2) = 1.25
    s2 = fit_strengths(train, k=2)
    assert s2.home_att["A"] == pytest.approx(1.25)
    # unknown team -> average strength
    assert s2.expected_goals("C", "D") == pytest.approx((2.0, 0.5))
