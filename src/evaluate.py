"""Evaluate predictions: accuracy vs the market, simulated bets, CLV, bootstrap."""

import numpy as np
import pandas as pd

from src.model import remove_margin

MARKETS = {"1x2": ["h", "d", "a"], "ou25": ["o25", "u25"]}


# ---------------------------------------------------------------- helpers

def market_fair_probs(df: pd.DataFrame, book: str, timing: str, market: str,
                      method: str = "power") -> pd.DataFrame:
    """Margin-free probabilities from one bookmaker, columns named by outcome.

    Rows with any missing odds get NaN.
    """
    outcomes = MARKETS[market]
    odds = df[[f"{book}_{timing}_{o}" for o in outcomes]].to_numpy(dtype=float)
    probs = remove_margin(odds, method)  # NaN propagates
    return pd.DataFrame(probs, columns=outcomes, index=df.index)


def outcome_matrix(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """1/0 for what actually happened, columns named by outcome."""
    total = df["hg"] + df["ag"]
    res = {
        "h": df["hg"] > df["ag"], "d": df["hg"] == df["ag"], "a": df["hg"] < df["ag"],
        "o25": total > 2, "u25": total <= 2,
    }
    return pd.DataFrame({o: res[o].astype(int) for o in MARKETS[market]}, index=df.index)


def log_loss(probs: pd.DataFrame, actual: pd.DataFrame) -> float:
    """Mean of -ln(probability given to what happened). Lower is better."""
    p = (probs.to_numpy() * actual.to_numpy()).sum(axis=1)
    return float(-np.log(np.clip(p, 1e-15, 1)).mean())


def brier(probs: pd.DataFrame, actual: pd.DataFrame) -> float:
    """Mean squared error summed over outcomes. Lower is better."""
    return float(((probs.to_numpy() - actual.to_numpy()) ** 2).sum(axis=1).mean())


def max_drawdown(profits: pd.Series) -> float:
    """Largest drop (in units) from a peak of the cumulative profit curve."""
    cum = profits.cumsum()
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum.to_numpy()]))[1:]
    return float((peak - cum).max()) if len(cum) else 0.0


def bootstrap_roi(profits: np.ndarray, n: int = 5000, seed: int = 1) -> tuple[float, float]:
    """95 % interval for ROI (flat 1-unit stakes) by resampling bets."""
    if len(profits) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    samples = rng.choice(profits, size=(n, len(profits)), replace=True).mean(axis=1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


# ---------------------------------------------------------------- accuracy

def accuracy_table(preds: pd.DataFrame, market: str) -> pd.DataFrame:
    """Log loss and Brier: model vs Pinnacle closing (margin removed), same matches."""
    outcomes = MARKETS[market]
    model = preds[[f"p_{o}" for o in outcomes]].set_axis(outcomes, axis=1)
    mkt = market_fair_probs(preds, "ps", "close", market)
    ok = model.notna().all(axis=1) & mkt.notna().all(axis=1)
    rows = []
    for league, idx in preds[ok].groupby("league").groups.items():
        actual = outcome_matrix(preds.loc[idx], market)
        rows.append({
            "league": league, "matches": len(idx),
            "logloss_model": log_loss(model.loc[idx], actual),
            "logloss_pinnacle": log_loss(mkt.loc[idx], actual),
            "brier_model": brier(model.loc[idx], actual),
            "brier_pinnacle": brier(mkt.loc[idx], actual),
        })
    return pd.DataFrame(rows)


def calibration_table(probs: pd.Series, happened: pd.Series, bins=None) -> pd.DataFrame:
    """Group predictions in probability buckets: predicted vs actual frequency."""
    bins = bins if bins is not None else [0, .1, .2, .3, .4, .5, .6, .7, .8, 1]
    ok = probs.notna()
    b = pd.cut(probs[ok], bins)
    t = pd.DataFrame({"p": probs[ok], "y": happened[ok], "bucket": b})
    return t.groupby("bucket", observed=True).agg(
        n=("y", "size"), predicted=("p", "mean"), actual=("y", "mean")).reset_index()


# ---------------------------------------------------------------- betting

def bet_timing(league: str) -> str:
    """Which odds we could realistically have taken: extra leagues only have closing odds."""
    return "close" if league == "SWE" else "early"


def select_bets(preds: pd.DataFrame, prob_source: str, book: str, market: str,
                threshold: float, margin_method: str = "power") -> pd.DataFrame:
    """One bet per match and market: the outcome with highest value, if value >= threshold.

    prob_source: "model" (our Poisson probs) or "pinnacle" (Pinnacle odds, margin removed,
    same timing as the bet). Stake is 1 unit flat. CLV is measured against
    Pinnacle's margin-free closing probability: CLV = odds_taken * p_close - 1.
    """
    outcomes = MARKETS[market]
    frames = []
    for league, lg in preds.groupby("league"):
        timing = bet_timing(league)
        odds = lg[[f"{book}_{timing}_{o}" for o in outcomes]].set_axis(outcomes, axis=1)
        if prob_source == "model":
            probs = lg[[f"p_{o}" for o in outcomes]].set_axis(outcomes, axis=1)
        else:
            probs = market_fair_probs(lg, "ps", timing, market, margin_method)
        close = market_fair_probs(lg, "ps", "close", market, margin_method)
        vals = probs * odds - 1
        ok = vals.notna().all(axis=1)
        if not ok.any():
            continue
        best = vals[ok].idxmax(axis=1)
        pick = pd.DataFrame({"outcome": best}, index=best.index)
        pick["value"] = [vals.at[i, o] for i, o in best.items()]
        pick = pick[pick["value"] >= threshold]
        if pick.empty:
            continue
        actual = outcome_matrix(lg.loc[pick.index], market)
        pick["date"] = lg.loc[pick.index, "date"]
        pick["league"] = league
        pick["p"] = [probs.at[i, o] for i, o in pick["outcome"].items()]
        pick["odds"] = [odds.at[i, o] for i, o in pick["outcome"].items()]
        pick["won"] = [actual.at[i, o] for i, o in pick["outcome"].items()]
        pick["profit"] = np.where(pick["won"] == 1, pick["odds"] - 1, -1.0)
        pick["clv"] = [pick.at[i, "odds"] * close.at[i, o] - 1 for i, o in pick["outcome"].items()]
        frames.append(pick)
    if not frames:
        return pd.DataFrame(columns=["date", "league", "outcome", "p", "odds", "value",
                                     "won", "profit", "clv"])
    return pd.concat(frames).sort_values("date")


def summarize(bets: pd.DataFrame) -> dict:
    """Key numbers for a set of flat-stake bets."""
    n = len(bets)
    if n == 0:
        return {"bets": 0}
    lo, hi = bootstrap_roi(bets["profit"].to_numpy())
    return {
        "bets": n,
        "hit_rate": bets["won"].mean(),
        "avg_odds": bets["odds"].mean(),
        "profit_units": bets["profit"].sum(),
        "roi": bets["profit"].mean(),
        "roi_ci_low": lo,
        "roi_ci_high": hi,
        "max_drawdown": max_drawdown(bets["profit"]),
        "avg_clv": bets["clv"].mean(),
        "clv_positive_share": (bets["clv"].dropna() > 0).mean(),
    }
