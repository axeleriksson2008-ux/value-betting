import numpy as np
import pandas as pd

from src.backtest import predict_rolling


def _fake_league(n_days=60, seed=0):
    """Round robin-ish fake league: 6 teams, 3 matches per day."""
    rng = np.random.default_rng(seed)
    teams = list("ABCDEF")
    rows = []
    for d in range(n_days):
        order = rng.permutation(teams)
        for i in range(0, 6, 2):
            rows.append({
                "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=d),
                "league": "X", "season": 2020,
                "home": order[i], "away": order[i + 1],
                "hg": int(rng.poisson(1.5)), "ag": int(rng.poisson(1.1)),
            })
    return pd.DataFrame(rows)


def test_no_look_ahead():
    """Changing results on/after a day must not change predictions for that day."""
    df = _fake_league()
    cutoff = df["date"].unique()[45]
    base = predict_rolling(df, min_train_matches=10)

    tampered = df.copy()
    future = tampered["date"] >= cutoff
    tampered.loc[future, "hg"] = 9  # absurd future results
    tampered.loc[future, "ag"] = 0
    after = predict_rolling(tampered, min_train_matches=10)

    on_cutoff = df["date"] == cutoff
    pd.testing.assert_series_equal(base.loc[on_cutoff, "p_h"], after.loc[on_cutoff, "p_h"])
    # sanity: a later day IS affected, so the test can detect leakage
    later = df["date"] == df["date"].unique()[50]
    assert not np.allclose(base.loc[later, "p_h"], after.loc[later, "p_h"])


def test_skips_when_too_little_history():
    df = _fake_league(n_days=5)
    preds = predict_rolling(df, min_train_matches=100)
    assert preds["p_h"].isna().all()
    # first day can never be predicted
    preds = predict_rolling(df, min_train_matches=1, min_team_games=0)
    assert preds.loc[df["date"] == df["date"].min(), "p_h"].isna().all()
