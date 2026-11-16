"""Rolling (walk-forward) backtest of the Poisson model.

For each league and each match day D:
  train = matches in the same league with date < D and date >= D - window
  -> fit strengths -> predict every match on day D.
Nothing from day D or later is ever used for a prediction on day D
(no look-ahead bias). This is checked by tests/test_backtest.py.
"""

from pathlib import Path

import pandas as pd

from src.model import fit_strengths, market_probs

PROB_COLUMNS = ["p_h", "p_d", "p_a", "p_o25", "p_u25", "p_btts_yes", "p_btts_no"]


def predict_rolling(matches: pd.DataFrame, k: float = 5.0, window_days: int = 365,
                    min_team_games: int = 3, min_train_matches: int = 100) -> pd.DataFrame:
    """Return `matches` with model columns lam_h, lam_a and p_* added.

    Rows that could not be predicted (too little history) get NaN.
    """
    out = matches.copy()
    out[["lam_h", "lam_a"] + PROB_COLUMNS] = float("nan")

    for league, lg in out.groupby("league"):
        lg = lg.sort_values("date")
        for day in lg["date"].unique():
            start = day - pd.Timedelta(days=window_days)
            train = lg[(lg["date"] < day) & (lg["date"] >= start)]
            if len(train) < min_train_matches:
                continue
            s = fit_strengths(train[["home", "away", "hg", "ag"]], k=k)
            for idx, row in lg[lg["date"] == day].iterrows():
                if min(s.games.get(row["home"], 0), s.games.get(row["away"], 0)) < min_team_games:
                    continue
                lam_h, lam_a = s.expected_goals(row["home"], row["away"])
                p = market_probs(lam_h, lam_a)
                out.loc[idx, ["lam_h", "lam_a"]] = [lam_h, lam_a]
                out.loc[idx, PROB_COLUMNS] = [p[c[2:]] for c in PROB_COLUMNS]
    return out


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    matches = pd.read_csv(root / "data" / "processed" / "matches.csv", parse_dates=["date"])
    preds = predict_rolling(matches)
    path = root / "data" / "processed" / "predictions.csv"
    preds.to_csv(path, index=False)
    print(f"Predicted {preds['p_h'].notna().sum()} of {len(preds)} matches -> {path}")
