import math

import numpy as np
import pandas as pd
import pytest

from src.evaluate import (bootstrap_roi, brier, log_loss, max_drawdown,
                          outcome_matrix, select_bets)


def test_log_loss_and_brier_hand_calc():
    probs = pd.DataFrame({"h": [0.5, 0.2], "d": [0.3, 0.3], "a": [0.2, 0.5]})
    actual = pd.DataFrame({"h": [1, 0], "d": [0, 0], "a": [0, 1]})
    assert log_loss(probs, actual) == pytest.approx(-math.log(0.5))
    # (0.5^2 + 0.3^2 + 0.2^2) for both rows
    assert brier(probs, actual) == pytest.approx(0.25 + 0.09 + 0.04)


def test_max_drawdown():
    # cum: 1, 0, -2, -1, 3 -> peak 1, worst -2 -> drawdown 3
    assert max_drawdown(pd.Series([1.0, -1, -2, 1, 4])) == pytest.approx(3.0)
    # starting with a loss counts from 0
    assert max_drawdown(pd.Series([-1.0, -1])) == pytest.approx(2.0)


def test_bootstrap_contains_mean():
    profits = np.array([1.0, -1, 1, -1, 0.5, -1, 2, -1])
    lo, hi = bootstrap_roi(profits)
    assert lo < profits.mean() < hi


def test_outcome_matrix():
    df = pd.DataFrame({"hg": [2, 1, 0], "ag": [1, 1, 3]})
    m = outcome_matrix(df, "1x2")
    assert m.to_numpy().tolist() == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert outcome_matrix(df, "ou25")["o25"].tolist() == [1, 0, 1]


def test_select_bets_picks_value_and_settles():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01"]), "league": ["E0"], "hg": [2], "ag": [0],
        "p_h": [0.6], "p_d": [0.25], "p_a": [0.15],
        "b365_early_h": [2.0], "b365_early_d": [3.5], "b365_early_a": [6.0],
        "ps_close_h": [1.8], "ps_close_d": [3.8], "ps_close_a": [5.5],
    })
    bets = select_bets(df, "model", "b365", "1x2", threshold=0.05)
    assert len(bets) == 1
    b = bets.iloc[0]
    assert b["outcome"] == "h" and b["value"] == pytest.approx(0.2)
    assert b["profit"] == pytest.approx(1.0)
    from src.model import remove_margin
    assert b["clv"] == pytest.approx(2.0 * remove_margin([1.8, 3.8, 5.5])[0] - 1)
    # threshold too high -> no bet
    assert select_bets(df, "model", "b365", "1x2", threshold=0.5).empty
