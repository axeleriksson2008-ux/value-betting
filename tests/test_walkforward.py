import numpy as np
import pandas as pd

from src.walkforward import Params, predict_league


def _fake_league(n_days=80, seed=0):
    rng = np.random.default_rng(seed)
    teams = list("ABCDEFGH")
    rows = []
    for d in range(n_days):
        order = rng.permutation(teams)
        for i in range(0, 8, 2):
            rows.append({"date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=3 * d),
                         "league": "X", "season": 2020 + (d >= 40),
                         "home": order[i], "away": order[i + 1],
                         "hg": int(rng.poisson(1.5)), "ag": int(rng.poisson(1.1))})
    return pd.DataFrame(rows)


P = Params(min_train_matches=20)


def test_no_look_ahead():
    df = _fake_league()
    cutoff = df["date"].unique()[60]
    base = predict_league(df, P)
    tampered = df.copy()
    future = tampered["date"] >= cutoff
    tampered.loc[future, ["hg", "ag"]] = [9, 0]
    after = predict_league(tampered, P)
    on_cutoff = df["date"] == cutoff
    pd.testing.assert_frame_equal(base[on_cutoff], after[on_cutoff])
    later = df["date"] == df["date"].unique()[65]
    assert not np.allclose(base.loc[later, "lam_h"], after.loc[later, "lam_h"])


def test_period_limits():
    df = _fake_league()
    start, end = df["date"].unique()[30], df["date"].unique()[50]
    out = predict_league(df, P, start, end)
    inside = (df["date"] >= start) & (df["date"] < end)
    assert out.loc[~inside, "lam_h"].isna().all()
    assert out.loc[inside, "lam_h"].notna().any()


def test_promoted_prior_lowers_new_team():
    df = _fake_league()
    # team Z joins in season 2021, replacing H
    df.loc[(df.season == 2021) & (df.home == "H"), "home"] = "Z"
    df.loc[(df.season == 2021) & (df.away == "H"), "away"] = "Z"
    first_z = df.index[(df.home == "Z") | (df.away == "Z")][4]  # after a few Z games
    p1 = predict_league(df, Params(min_train_matches=20, min_team_games=1))
    p2 = predict_league(df, Params(min_train_matches=20, min_team_games=1, promoted=0.7))
    row = df.loc[first_z]
    col = "lam_h" if row.home == "Z" else "lam_a"
    assert p2.loc[first_z, col] < p1.loc[first_z, col]
