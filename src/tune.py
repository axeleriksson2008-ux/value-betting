"""Choose model v2 parameters on the VALIDATION period only (log loss, 1X2 and O/U 2.5).

Writes reports/tuning_validation.csv and data/processed/v1_predictions.parquet.
"""

import itertools
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest import predict_rolling
from src.evaluate import log_loss, market_fair_probs, outcome_matrix
from src.ratings import matrix_probs, score_matrices
from src.walkforward import TEST_START, VAL_START, Params, predict_all

ROOT = Path(__file__).resolve().parents[1]
DC_VARIANTS = {"off": None, "fitted": "fitted", "fixed-0.05": -0.05}


def probs_from_lams(pred: pd.DataFrame, dc) -> pd.DataFrame:
    """Turn lam_h/lam_a/rho into 1X2 and O/U probabilities."""
    ok = pred["lam_h"].notna()
    rho = 0.0 if dc is None else (pred.loc[ok, "rho"].to_numpy() if dc == "fitted" else dc)
    out = pd.DataFrame(index=pred.index, columns=["p_h", "p_d", "p_a", "p_o25", "p_u25"], dtype=float)
    if ok.any():
        pr = matrix_probs(score_matrices(pred.loc[ok, "lam_h"], pred.loc[ok, "lam_a"], rho))
        for k in ["h", "d", "a", "o25", "u25"]:
            out.loc[ok, f"p_{k}"] = pr[k]
    return out


def scores(probs: pd.DataFrame, matches: pd.DataFrame, rows) -> dict:
    res = {}
    for market, outs in [("1x2", ["h", "d", "a"]), ("ou25", ["o25", "u25"])]:
        sub = rows[market]
        p = probs.loc[sub, [f"p_{o}" for o in outs]].set_axis(outs, axis=1)
        res[f"ll_{market}"] = log_loss(p, outcome_matrix(matches.loc[sub], market))
    return res


def _v1_job(lg):
    return predict_rolling(lg)[["p_h", "p_d", "p_a", "p_o25", "p_u25"]]


def v1_predictions(matches: pd.DataFrame) -> pd.DataFrame:
    path = ROOT / "data" / "processed" / "v1_predictions.parquet"
    if path.exists():
        return pd.read_parquet(path)
    cols = ["date", "league", "season", "home", "away", "hg", "ag"]
    with Pool(4) as pool:
        parts = pool.map(_v1_job, [lg[cols] for _, lg in matches.groupby("league")])
    v1 = pd.concat(parts).reindex(matches.index)
    v1.to_parquet(path)
    return v1


def main():
    m = pd.read_parquet(ROOT / "data" / "processed" / "matches.parquet")
    val = (m["date"] >= VAL_START) & (m["date"] < TEST_START)

    v1 = v1_predictions(m)
    grid = list(itertools.product([90, 180, 365, 730], [2, 5, 10, 20], [1.0, 0.9, 0.8]))
    preds = {}
    for hl, kappa, promoted in grid:
        p = Params(half_life=hl, kappa=kappa, promoted=promoted)
        preds[p] = predict_all(m, p, VAL_START, TEST_START)
        print("done", p, flush=True)

    # Same matches for every model: predicted by all, with Pinnacle closing odds
    any_pred = next(iter(preds.values()))
    common = val & any_pred["lam_h"].notna() & v1["p_h"].notna()
    rows = {
        "1x2": common & market_fair_probs(m, "ps", "close", "1x2").notna().all(axis=1),
        "ou25": common & market_fair_probs(m, "ps", "close", "ou25").notna().all(axis=1),
    }
    results = []
    mk = pd.concat([market_fair_probs(m, "ps", "close", "1x2").add_prefix("p_"),
                    market_fair_probs(m, "ps", "close", "ou25").add_prefix("p_")], axis=1)
    results.append({"model": "pinnacle_close", **scores(mk, m, rows)})
    results.append({"model": "v1", **scores(v1, m, rows)})
    for p, pred in preds.items():
        for dc_name, dc in DC_VARIANTS.items():
            results.append({"model": "v2", "half_life": p.half_life, "kappa": p.kappa,
                            "promoted": p.promoted, "dc": dc_name,
                            **scores(probs_from_lams(pred, dc), m, rows)})
    res = pd.DataFrame(results)
    res["n_1x2"], res["n_ou25"] = rows["1x2"].sum(), rows["ou25"].sum()
    res.to_csv(ROOT / "reports" / "tuning_validation.csv", index=False)
    print(res.sort_values("ll_1x2").head(15).to_string())
    print(res[res.model != "v2"].to_string())


if __name__ == "__main__":
    main()
