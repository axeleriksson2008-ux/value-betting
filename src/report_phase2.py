"""Build reports/phase2.md: model v2 vs v1 vs market, and the strategy search."""

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.evaluate import (bootstrap_roi, calibration_table, log_loss, market_fair_probs,  # noqa: E402
                          max_drawdown, outcome_matrix)
from src.report import COLORS, GRID, INK, INK_MUTED, _style, pct  # noqa: E402
from src.search import selected_test_bets  # noqa: E402
from src.tune import probs_from_lams  # noqa: E402
from src.walkforward import TEST_START, VAL_START  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
PROC = ROOT / "data" / "processed"


def load():
    m = pd.read_parquet(PROC / "matches.parquet")
    v1 = pd.read_parquet(PROC / "v1_predictions.parquet")
    v2 = probs_from_lams(pd.read_parquet(PROC / "v2_predictions.parquet"), -0.05)
    mk = pd.concat([market_fair_probs(m, "ps", "close", "1x2").add_prefix("p_"),
                    market_fair_probs(m, "ps", "close", "ou25").add_prefix("p_")], axis=1)
    return m, v1, v2, mk


def _ll(probs, m, rows, outs):
    p = probs.loc[rows, [f"p_{o}" for o in outs]].set_axis(outs, axis=1)
    market = "1x2" if outs[0] == "h" else "ou25"
    return log_loss(p, outcome_matrix(m.loc[rows], market))


def accuracy_tables(m, v1, v2, mk):
    periods = {"Validering 2020–23": (m.date >= VAL_START) & (m.date < TEST_START),
               "Test 2023–26": m.date >= TEST_START}
    lines = ["| Period | Marknad | Matcher | Pinnacle stängning | Modell v1 | Modell v2 |",
             "|---|---|---|---|---|---|"]
    for name, per in periods.items():
        base = per & v1.p_h.notna() & v2.p_h.notna()
        for market, outs in [("1X2", ["h", "d", "a"]), ("Ö/U 2,5", ["o25", "u25"])]:
            rows = base & mk[[f"p_{o}" for o in outs]].notna().all(axis=1)
            vals = [_ll(x, m, rows, outs) for x in (mk, v1, v2)]
            lines.append(f"| {name} | {market} | {rows.sum()} | {vals[0]:.4f} | {vals[1]:.4f} | {vals[2]:.4f} |")
    overall = "\n".join(lines)

    test = (m.date >= TEST_START) & v2.p_h.notna() & mk[["p_h", "p_d", "p_a"]].notna().all(axis=1)
    rows = []
    for league, idx in m[test].groupby("league").groups.items():
        if len(idx) < 150:
            continue
        mask = pd.Series(False, index=m.index)
        mask[idx] = True
        ll_m = _ll(mk, m, mask, ["h", "d", "a"])
        ll_2 = _ll(v2, m, mask, ["h", "d", "a"])
        rows.append((league, len(idx), ll_m, ll_2, ll_2 - ll_m))
    rows.sort(key=lambda r: r[4])
    lg = ["| Liga | Matcher | Pinnacle | Modell v2 | Skillnad (v2 − Pinnacle) |", "|---|---|---|---|---|"]
    lg += [f"| {r[0]} | {r[1]} | {r[2]:.4f} | {r[3]:.4f} | {r[4]:+.4f} |" for r in rows]
    return overall, "\n".join(lg), sum(r[4] < 0 for r in rows), len(rows)


def calibration_figure(m, v1, v2, mk, path):
    test = (m.date >= TEST_START) & v1.p_h.notna() & v2.p_h.notna() & mk.p_h.notna()
    act = outcome_matrix(m[test], "1x2")
    y = pd.concat([act[o] for o in "hda"], ignore_index=True)
    bins = [0, .1, .15, .2, .25, .3, .35, .4, .45, .5, .55, .6, .65, .7, .8, 1]
    fig, ax = plt.subplots(figsize=(6, 5.2), dpi=150)
    _style(ax)
    ax.plot([0, 1], [0, 1], color=INK_MUTED, linewidth=1, linestyle="--")
    for i, (name, src) in enumerate([("Modell v1", v1), ("Modell v2", v2), ("Pinnacle stängning", mk)]):
        p = pd.concat([src.loc[test, f"p_{o}"] for o in "hda"], ignore_index=True)
        c = calibration_table(p, y, bins)
        c = c[c["n"] >= 50]
        ax.plot(c["predicted"], c["actual"], color=COLORS[i], linewidth=2, marker="o", markersize=5,
                markeredgecolor="#fcfcfb", markeredgewidth=1.5, label=name)
    ax.set_xlim(0, 1.0), ax.set_ylim(0, 1.0)
    ax.set_xlabel("Förutsagd sannolikhet", color=INK, fontsize=10)
    ax.set_ylabel("Faktisk andel som inträffade", color=INK, fontsize=10)
    ax.set_title("Kalibrering 1X2, testperioden (alla ligor)", color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def model_bet_table(table):
    t = table[(table.source == "model") & (table.league == "ALL") & (table.threshold == 0.05)
              & table.book.isin(["ps", "b365", "bw", "bfe", "best", "max", "avg"])]
    lines = ["| Marknad | Odds | Spel (test) | ROI test | 95 % KI | CLV test | ROI validering |",
             "|---|---|---|---|---|---|---|"]
    for r in t.sort_values(["market", "book"]).itertuples():
        if pd.isna(r.n_test):
            continue
        lines.append(f"| {r.market} | {r.book} | {int(r.n_test)} | {pct(r.roi_test)} "
                     f"| {pct(r.roi_lo_test)} … {pct(r.roi_hi_test)} | {pct(r.clv_test)} | {pct(r.roi_val)} |")
    return "\n".join(lines)


def selected_table(chosen):
    lines = ["| Källa | Marknad | Odds | Liga | Tröskel | Spel val | ROI val | Spel test | ROI test | 95 % KI test | CLV test |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in chosen.sort_values(["source", "market", "league", "threshold"]).itertuples():
        lines.append(
            f"| {r.source} | {r.market} | {r.book} | {r.league} | {r.threshold:.0%} | {int(r.n_val)} "
            f"| {pct(r.roi_val)} | {int(r.n_test)} | {pct(r.roi_test)} "
            f"| {pct(r.roi_lo_test)} … {pct(r.roi_hi_test)} | {pct(r.clv_test)} |")
    return "\n".join(lines)


def realism_table(table):
    lines = ["| Strategi (1X2, alla ligor) | Tröskel | Spel val | ROI val | Spel test | ROI test | 95 % KI test | CLV test |",
             "|---|---|---|---|---|---|---|---|"]
    names = {"max": "Pinnacle → Max (alla bolag i football-data)",
             "best": "Pinnacle → bästa namngivna bolag", "b365": "Pinnacle → Bet365",
             "bw": "Pinnacle → bwin", "bfe": "Pinnacle → Betfair-börsen (−5 % provision)"}
    for book, label in names.items():
        for th in [0.0, 0.03]:
            r = table[(table.source == "pinnacle") & (table.market == "1x2") & (table.book == book)
                      & (table.league == "ALL") & (table.threshold == th)]
            if r.empty:
                continue
            r = r.iloc[0]
            nv = "–" if pd.isna(r.n_val) else int(r.n_val)
            lines.append(f"| {label} | {th:.0%} | {nv} | {pct(r.roi_val)} | {int(r.n_test)} "
                         f"| {pct(r.roi_test)} | {pct(r.roi_lo_test)} … {pct(r.roi_hi_test)} | {pct(r.clv_test)} |")
    return "\n".join(lines)


def cumulative_figure(bets, path):
    strategies = {
        "Pinnacle → Max, ≥ 0 %": ("pinnacle", "1x2", "max", 0.0),
        "Pinnacle → bästa namngivna, ≥ 0 %": ("pinnacle", "1x2", "best", 0.0),
        "Modell v2 → Max, ≥ 5 %": ("model", "1x2", "max", 0.05),
    }
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    _style(ax)
    ax.axhline(0, color=INK_MUTED, linewidth=0.8)
    ax.axvline(TEST_START, color=INK_MUTED, linewidth=1, linestyle="--")
    ax.text(TEST_START, 1.0, "  testperiod →", transform=ax.get_xaxis_transform(), va="top",
            fontsize=8, color=INK_MUTED)
    for i, (label, (src, mkt, book, th)) in enumerate(strategies.items()):
        b = bets[(bets.source == src) & (bets.market == mkt) & (bets.book == book)
                 & (bets.value >= th)].sort_values("date")
        cum = b["profit"].cumsum().to_numpy()
        ax.plot(b["date"], cum, color=COLORS[i], linewidth=2, label=f"{label} ({len(b)} spel)")
        ax.annotate(f"{cum[-1]:+.0f}", (b["date"].iloc[-1], cum[-1]), xytext=(4, 0),
                    textcoords="offset points", fontsize=8, color=INK, va="center")
    ax.set_ylabel("Ackumulerad vinst (enheter)", color=INK, fontsize=9)
    ax.set_title("1X2, alla 38 ligor, 1 enhet per spel", color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="lower left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    m, v1, v2, mk = load()
    table = pd.read_csv(REPORTS / "strategies_all.csv")
    chosen = pd.read_csv(REPORTS / "strategies_selected.csv")
    bets = pd.read_parquet(PROC / "candidate_bets.parquet")

    overall, per_league, n_close, n_leagues = accuracy_tables(m, v1, v2, mk)
    calibration_figure(m, v1, v2, mk, REPORTS / "phase2_calibration.png")
    cumulative_figure(bets, REPORTS / "phase2_cumulative.png")

    tb = selected_test_bets(bets, chosen)
    # one bet per match/market/outcome even if several selected strategies contain it
    uniq = tb.drop_duplicates(subset=["row", "market", "outcome"])
    lo, hi = bootstrap_roi(uniq["profit"].to_numpy())
    combined = (f"{len(uniq)} unika spel, ROI {pct(uniq.profit.mean())} "
                f"(95 % KI {pct(lo)} … {pct(hi)}), vinst {uniq.profit.sum():+.1f} enheter, "
                f"max drawdown {max_drawdown(uniq.sort_values('date').profit):.1f} enheter, "
                f"snitt-CLV {pct(uniq.clv.mean())}")

    sections = {
        "N_STRATEGIES": str(len(table)), "N_SELECTED": str(len(chosen)),
        "ACCURACY": overall, "PER_LEAGUE": per_league,
        "N_CLOSE": str(n_close), "N_LEAGUES": str(n_leagues),
        "MODEL_BETS": model_bet_table(table), "SELECTED": selected_table(chosen),
        "COMBINED": combined, "REALISM": realism_table(table),
        "N_TEST_POSITIVE": str(int((chosen.roi_test > 0).sum())),
    }
    text = (REPORTS / "phase2_template.md").read_text()
    for k, v in sections.items():
        text = text.replace("{{" + k + "}}", v)
    (REPORTS / "phase2.md").write_text(text)
    print("Wrote reports/phase2.md")
    print(combined)


if __name__ == "__main__":
    main()
