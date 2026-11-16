"""Value list for upcoming matches and CLV tracking of earlier signals.

Fair price: Pinnacle's odds with the margin removed (power method). If Pinnacle
is missing for a match, Betfair exchange (after 5 % commission) is used instead.
A signal = a Swedish bookmaker offers odds with value >= VALUE_THRESHOLD
against that fair price, seen in a snapshot before kick-off.

CLV of a signal = signal odds * Pinnacle fair CLOSING probability - 1.
That is the main proof: if Swedish books really are slower than Pinnacle,
average CLV stays positive over hundreds of signals.

Run:  python -m src.live   -> reports/live_value.md and reports/live_clv.md
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src import config, oddsdb
from src.model import kelly_fraction, remove_margin
from src.odds_api import utcnow

OUTCOMES = ["h", "d", "a"]
OUT_NAME = {"h": "1 (hemma)", "d": "X (oavgjort)", "a": "2 (borta)"}


def wide_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """One row per (snapshot, event, book) with columns h, d, a."""
    w = prices.pivot_table(index=["snapshot_id", "sport", "kind", "fetched_at", "event_id",
                                  "commence_time", "home", "away", "book"],
                           columns="outcome", values="price", aggfunc="last").reset_index()
    for o in OUTCOMES:
        if o not in w:
            w[o] = np.nan
    return w


def fair_probs(w: pd.DataFrame) -> pd.DataFrame:
    """Fair h/d/a probabilities per (snapshot, event): Pinnacle, else Betfair exchange."""
    keys = ["snapshot_id", "event_id"]
    rows = []
    for book in ["pinnacle", "betfair_ex_eu"]:
        b = w[w["book"] == book].dropna(subset=OUTCOMES).copy()
        odds = b[OUTCOMES].to_numpy(float)
        c = config.EXCHANGE_COMMISSION.get(book)
        if c:
            odds = 1 + (odds - 1) * (1 - c)
        if len(b):
            b[[f"fair_{o}" for o in OUTCOMES]] = remove_margin(odds)
            b["fair_source"] = book
            rows.append(b[keys + [f"fair_{o}" for o in OUTCOMES] + ["fair_source"]])
    if not rows:
        return pd.DataFrame(columns=keys + [f"fair_{o}" for o in OUTCOMES] + ["fair_source"])
    return pd.concat(rows).drop_duplicates(subset=keys, keep="first")  # Pinnacle first


def signals(prices: pd.DataFrame, threshold: float = config.VALUE_THRESHOLD) -> pd.DataFrame:
    """Every (snapshot, event, outcome) where the best Swedish price has value >= threshold."""
    w = wide_prices(prices)
    w = w[w["fetched_at"] < w["commence_time"]]
    fair = fair_probs(w)
    se = w[w["book"].isin(config.SWEDISH_BOOKS)]
    out = []
    for o in OUTCOMES:
        best = se.dropna(subset=[o]).sort_values(o).groupby(["snapshot_id", "event_id"]).tail(1)
        best = best.merge(fair, on=["snapshot_id", "event_id"])
        best = best.assign(outcome=o, odds=best[o], p_fair=best[f"fair_{o}"])
        out.append(best)
    s = pd.concat(out, ignore_index=True)
    s["value"] = s["p_fair"] * s["odds"] - 1
    s["fair_odds"] = 1 / s["p_fair"]
    s["stake_share"] = [kelly_fraction(p, od, config.KELLY_FRACTION, config.MAX_STAKE_SHARE)
                        for p, od in zip(s["p_fair"], s["odds"])]
    cols = ["snapshot_id", "sport", "kind", "fetched_at", "event_id", "commence_time", "home", "away",
            "outcome", "book", "odds", "fair_odds", "p_fair", "fair_source", "value", "stake_share"]
    return s.loc[s["value"] >= threshold, cols].sort_values(["commence_time", "value"],
                                                             ascending=[True, False])


def closing_fair(prices: pd.DataFrame) -> pd.DataFrame:
    """Pinnacle fair closing probabilities per event (last Pinnacle snapshot before kick-off)."""
    w = wide_prices(prices)
    w = w[(w["book"] == "pinnacle") & (w["fetched_at"] < w["commence_time"])].dropna(subset=OUTCOMES)
    last = w.sort_values("fetched_at").groupby("event_id").tail(1).copy()
    last[[f"close_{o}" for o in OUTCOMES]] = remove_margin(last[OUTCOMES].to_numpy(float))
    last["minutes_before"] = (last["commence_time"] - last["fetched_at"]).dt.total_seconds() / 60
    return last[["event_id", "minutes_before"] + [f"close_{o}" for o in OUTCOMES]]


def clv_table(prices: pd.DataFrame) -> pd.DataFrame:
    """First signal per event/outcome/book (the bet we would have placed) with its CLV."""
    s = signals(prices)
    s = s.sort_values("fetched_at").drop_duplicates(subset=["event_id", "outcome", "book"])
    now = pd.Timestamp(utcnow())
    s = s[s["commence_time"] < now]
    close = closing_fair(prices)
    s = s.merge(close, on="event_id", how="left")
    p_close = np.choose(s["outcome"].map({"h": 0, "d": 1, "a": 2}).to_numpy(),
                        [s["close_h"], s["close_d"], s["close_a"]]) if len(s) else []
    s["clv"] = s["odds"] * np.asarray(p_close, float) - 1
    # signal taken at the closing snapshot itself has no meaningful CLV
    s.loc[s["kind"] == "close", "clv"] = np.nan
    return s


def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_Inga._"
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns)
    rows = ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return head + "\n" + "\n".join(rows)


def value_report(prices: pd.DataFrame, bankroll: float = 1000.0) -> str:
    now = pd.Timestamp(utcnow())
    s = signals(prices)
    latest = s.groupby("event_id")["snapshot_id"].transform("max") == s["snapshot_id"]
    s = s[latest & (s["commence_time"] > now)]
    head = (f"# Value-spel just nu\n\n*Uppdaterad {now:%Y-%m-%d %H:%M} UTC. Rättvist odds = Pinnacle utan "
            f"marginal. Insats = kvarts-Kelly, högst {config.MAX_STAKE_SHARE:.0%} av kassan.*\n\n"
            "**Detta är för uppföljning. Fas 3 handlar om att mäta, inte spela.**\n\n")
    if s.empty:
        return head + "_Inga value-spel i den senaste hämtningen._\n"
    t = pd.DataFrame({
        "Avspark (UTC)": s["commence_time"].dt.strftime("%a %d/%m %H:%M"),
        "Match": s["home"] + " – " + s["away"],
        "Spel": s["outcome"].map(OUT_NAME),
        "Bolag": s["book"],
        "Odds": s["odds"].map("{:.2f}".format),
        "Rättvist odds": s["fair_odds"].map("{:.2f}".format) + " (" + s["fair_source"] + ")",
        "Value": s["value"].map("{:+.1%}".format),
        f"Insats (kassa {bankroll:.0f} kr)": (s["stake_share"] * bankroll).round(0).astype(int).astype(str) + " kr",
        "Hämtat": s["fetched_at"].dt.strftime("%d/%m %H:%M"),
    })
    return head + _md_table(t) + "\n"


def clv_report(prices: pd.DataFrame, api_log: Path | None = None) -> str:
    api_log = api_log or config.API_LOG
    c = clv_table(prices)
    done = c.dropna(subset=["clv"])
    lines = [f"# CLV-uppföljning\n\n*Uppdaterad {pd.Timestamp(utcnow()):%Y-%m-%d %H:%M} UTC.*\n"]
    if done.empty:
        lines.append("Inga avslutade signaler med stängningsodds än.\n")
    else:
        lines.append(f"- Signaler med CLV: **{len(done)}**")
        lines.append(f"- Snitt-CLV: **{done.clv.mean():+.2%}** (andel positiva {(done.clv > 0).mean():.0%})")
        se = done.clv.std(ddof=1) / np.sqrt(len(done)) if len(done) > 1 else np.nan
        lines.append(f"- 95 % intervall för snitt-CLV: {done.clv.mean() - 1.96 * se:+.2%} … "
                     f"{done.clv.mean() + 1.96 * se:+.2%}\n")
        g = done.groupby("book").agg(signaler=("clv", "size"), snitt_clv=("clv", "mean"),
                                     snitt_value=("value", "mean")).reset_index()
        g["snitt_clv"] = g["snitt_clv"].map("{:+.2%}".format)
        g["snitt_value"] = g["snitt_value"].map("{:+.2%}".format)
        lines.append("## Per bolag\n\n" + _md_table(g) + "\n")
        g = done.groupby("sport").agg(signaler=("clv", "size"), snitt_clv=("clv", "mean")).reset_index()
        g["snitt_clv"] = g["snitt_clv"].map("{:+.2%}".format)
        lines.append("## Per liga\n\n" + _md_table(g) + "\n")
    if Path(api_log).exists():
        log = pd.read_csv(api_log)
        odds_calls = log[log["call"].str.startswith("odds:")]
        last = log.dropna(subset=["remaining"]).tail(1)
        rem = int(last["remaining"].iloc[0]) if len(last) else "?"
        lines.append(f"## API-förbrukning\n\n- Odds-anrop totalt: {len(odds_calls)}\n"
                     f"- Credits kvar denna månad: {rem}\n")
    return "\n".join(lines)


def main():
    con = oddsdb.build()
    prices = oddsdb.price_table(con)
    reports = config.ROOT / "reports"
    if prices.empty:
        print("No prices yet")
        return
    (reports / "live_value.md").write_text(value_report(prices))
    (reports / "live_clv.md").write_text(clv_report(prices))
    print("Wrote reports/live_value.md and reports/live_clv.md")


if __name__ == "__main__":
    main()
