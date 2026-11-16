"""Strategy search: select on VALIDATION, evaluate on TEST.

Strategy = (source, market, book, league or ALL, threshold).
Selection rule (fixed before looking at test results):
  validation bets >= 100, lower 95 % bound of ROI > 0, mean CLV > 0.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src.strategies import candidate_bets, model_outputs
from src.walkforward import TEST_START, VAL_START

ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = [0.0, 0.03, 0.05, 0.10]
MIN_BETS = 100


def build_candidates() -> pd.DataFrame:
    m = pd.read_parquet(ROOT / "data" / "processed" / "matches.parquet")
    pred = pd.read_parquet(ROOT / "data" / "processed" / "v2_predictions.parquet")
    sel = m["date"] >= VAL_START
    probs, gd = model_outputs(pred[sel], rho_mode=-0.05)
    bets = candidate_bets(m[sel], probs, gd)
    bets["period"] = np.where(bets["date"] >= TEST_START, "test", "val")
    return bets


def _stats(profit: pd.Series, clv: pd.Series) -> pd.Series:
    n = len(profit)
    roi = profit.mean()
    se = profit.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    return pd.Series({"n": n, "roi": roi, "roi_lo": roi - 1.96 * se, "roi_hi": roi + 1.96 * se,
                      "profit": profit.sum(), "clv": clv.mean()})


def strategy_table(bets: pd.DataFrame) -> pd.DataFrame:
    """Stats for every strategy and period. league = 'ALL' pools all leagues."""
    parts = []
    for th in THRESHOLDS:
        b = bets[bets["value"] >= th]
        for by_league in (False, True):
            keys = ["source", "market", "book"] + (["league"] if by_league else []) + ["period"]
            g = b.groupby(keys)
            t = g.agg(n=("profit", "size"), roi=("profit", "mean"), sd=("profit", "std"),
                      profit=("profit", "sum"), clv=("clv", "mean")).reset_index()
            if not by_league:
                t["league"] = "ALL"
            t["threshold"] = th
            parts.append(t)
    t = pd.concat(parts, ignore_index=True)
    se = t["sd"] / np.sqrt(t["n"])
    t["roi_lo"], t["roi_hi"] = t["roi"] - 1.96 * se, t["roi"] + 1.96 * se
    wide = t.pivot_table(index=["source", "market", "book", "league", "threshold"], columns="period",
                         values=["n", "roi", "roi_lo", "roi_hi", "profit", "clv"])
    wide.columns = [f"{a}_{p}" for a, p in wide.columns]
    return wide.reset_index()


def select(table: pd.DataFrame) -> pd.DataFrame:
    ok = (table["n_val"] >= MIN_BETS) & (table["roi_lo_val"] > 0) & (table["clv_val"] > 0)
    return table[ok].copy()


def selected_test_bets(bets: pd.DataFrame, chosen: pd.DataFrame) -> pd.DataFrame:
    """All test bets of the chosen strategies (a match can appear in several strategies)."""
    test = bets[bets["period"] == "test"]
    frames = []
    for r in chosen.itertuples():
        b = test[(test["source"] == r.source) & (test["market"] == r.market) & (test["book"] == r.book)
                 & (test["value"] >= r.threshold)]
        if r.league != "ALL":
            b = b[b["league"] == r.league]
        frames.append(b.assign(strategy=f"{r.source}|{r.market}|{r.book}|{r.league}|{r.threshold:.2f}"))
    return pd.concat(frames) if frames else test.iloc[:0]


if __name__ == "__main__":
    bets = build_candidates()
    bets.to_parquet(ROOT / "data" / "processed" / "candidate_bets.parquet")
    table = strategy_table(bets)
    table.to_csv(ROOT / "reports" / "strategies_all.csv", index=False)
    chosen = select(table)
    chosen.to_csv(ROOT / "reports" / "strategies_selected.csv", index=False)
    print(f"{len(table)} strategies, {len(chosen)} selected on validation")
