"""Bet log: the bets you actually placed, stored in data/bets.csv.

Columns
  bet_id, placed_at, event_id, sport, match, commence_time,
  outcome (h/d/a for 1X2, otherwise a text such as "Hörnor totalt över 9.5"),
  book, odds, stake, fair_odds (Pinnacle fair price when you bet), status, note
status: open / won / lost / void (void = stake returned)

Profit:  won -> stake * (odds - 1),  lost -> -stake,  void -> 0,  open -> not counted.
CLV:     odds * Pinnacle fair closing probability - 1 (when closing odds exist).
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src import config

COLUMNS = ["bet_id", "placed_at", "event_id", "sport", "match", "commence_time", "outcome",
           "book", "odds", "stake", "fair_odds", "status", "note"]
STATUSES = ["open", "won", "lost", "void"]


def bets_path() -> Path:
    return config.ROOT / "data" / "bets.csv"


def load_bets(path: Path | None = None) -> pd.DataFrame:
    path = Path(path or bets_path())
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    b = pd.read_csv(path, dtype={"bet_id": int, "event_id": str, "note": str})
    b["note"] = b["note"].fillna("")
    for c in ["placed_at", "commence_time"]:
        b[c] = pd.to_datetime(b[c], utc=True)
    return b[COLUMNS]


def save_bets(bets: pd.DataFrame, path: Path | None = None) -> None:
    path = Path(path or bets_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    bad = set(bets["status"]) - set(STATUSES)
    if bad:
        raise ValueError(f"unknown status {bad}")
    bets[COLUMNS].to_csv(path, index=False)


def add_bet(bets: pd.DataFrame, *, event_id, sport, match, commence_time, outcome, book,
            odds: float, stake: float, fair_odds: float | None = None, note: str = "",
            placed_at=None) -> pd.DataFrame:
    if odds <= 1 or stake <= 0:
        raise ValueError("odds must be > 1 and stake > 0")
    if not outcome or not isinstance(outcome, str):
        raise ValueError("outcome must be h, d, a or a description such as 'corners total over 9.5'")
    new_id = int(bets["bet_id"].max()) + 1 if len(bets) else 1
    row = {"bet_id": new_id, "placed_at": pd.Timestamp(placed_at or pd.Timestamp.now(tz="UTC")),
           "event_id": str(event_id), "sport": sport, "match": match,
           "commence_time": pd.Timestamp(commence_time), "outcome": outcome, "book": book,
           "odds": float(odds), "stake": float(stake),
           "fair_odds": np.nan if fair_odds is None else float(fair_odds),
           "status": "open", "note": note}
    return pd.concat([bets, pd.DataFrame([row])], ignore_index=True)[COLUMNS]


def set_status(bets: pd.DataFrame, bet_id: int, status: str) -> pd.DataFrame:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    out = bets.copy()
    out.loc[out["bet_id"] == bet_id, "status"] = status
    return out


def evaluate(bets: pd.DataFrame, closing: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add profit and clv columns. `closing` = live.closing_fair(...) (event_id, close_h/d/a)."""
    b = bets.copy()
    b["profit"] = np.select(
        [b["status"] == "won", b["status"] == "lost", b["status"] == "void"],
        [b["stake"] * (b["odds"] - 1), -b["stake"], 0.0], default=np.nan)
    b["clv"] = np.nan
    if closing is not None and len(closing) and len(b):
        m = b[["event_id", "outcome"]].merge(closing, on="event_id", how="left")
        p = np.select([m["outcome"] == "h", m["outcome"] == "d", m["outcome"] == "a"],
                      [m["close_h"], m["close_d"], m["close_a"]], default=np.nan)
        b["clv"] = b["odds"].to_numpy() * p - 1
    return b


def summary(evaluated: pd.DataFrame, bankroll_start: float) -> dict:
    settled = evaluated.dropna(subset=["profit"])
    staked = settled["stake"].sum()
    profit = settled["profit"].sum()
    return {
        "bets": len(evaluated),
        "open": int((evaluated["status"] == "open").sum()),
        "settled": len(settled),
        "staked": staked,
        "profit": profit,
        "roi": profit / staked if staked else np.nan,
        "avg_clv": evaluated["clv"].mean(),
        "bankroll": bankroll_start + profit,
    }


def bankroll_curve(evaluated: pd.DataFrame, bankroll_start: float) -> pd.DataFrame:
    """Bankroll after each settled bet, ordered by kick-off."""
    s = evaluated.dropna(subset=["profit"]).sort_values("commence_time")
    return pd.DataFrame({"date": s["commence_time"],
                         "bankroll": bankroll_start + s["profit"].cumsum()})
