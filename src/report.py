"""Build reports/backtest.md (tables + figures) from data/processed/predictions.csv."""

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.evaluate import (accuracy_table, calibration_table, market_fair_probs,  # noqa: E402
                          outcome_matrix, select_bets, summarize)

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
THRESHOLDS = [0.0, 0.03, 0.05, 0.10]

# Fixed categorical order (validated reference palette), text in neutral ink.
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, INK_MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def _style(ax):
    ax.set_facecolor("#fcfcfb")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def pct(x, digits=1):
    return "–" if pd.isna(x) else f"{x * 100:+.{digits}f} %"


def bets_table(preds, source, market, books):
    rows = []
    for book in books:
        for th in [None] + THRESHOLDS:
            b = select_bets(preds, source, book, market, -np.inf if th is None else th)
            s = summarize(b)
            if s["bets"] == 0:
                rows.append(f"| {book} | {'alla' if th is None else f'≥ {th:.0%}'} | 0 | | | | | | |")
                continue
            rows.append(
                f"| {book} | {'alla' if th is None else f'≥ {th:.0%}'} | {s['bets']} "
                f"| {s['avg_odds']:.2f} | {pct(s['roi'])} "
                f"| {pct(s['roi_ci_low'])} … {pct(s['roi_ci_high'])} "
                f"| {s['profit_units']:+.1f} | {s['max_drawdown']:.1f} | {pct(s['avg_clv'])} |")
    head = ("| Odds | Value-tröskel | Spel | Snittodds | ROI | 95 % KI för ROI | Vinst (enh.) "
            "| Max drawdown | Snitt-CLV |\n|---|---|---|---|---|---|---|---|---|")
    return head + "\n" + "\n".join(rows)


def accuracy_md(preds, market):
    t = accuracy_table(preds, market)
    lines = ["| Liga | Matcher | Log loss modell | Log loss Pinnacle | Brier modell | Brier Pinnacle |",
             "|---|---|---|---|---|---|"]
    for r in t.itertuples():
        lines.append(f"| {r.league} | {r.matches} | {r.logloss_model:.4f} | {r.logloss_pinnacle:.4f} "
                     f"| {r.brier_model:.4f} | {r.brier_pinnacle:.4f} |")
    return "\n".join(lines)


def calibration_figure(preds, path):
    p = preds[preds["p_h"].notna()]
    act = outcome_matrix(p, "1x2")
    mkt = market_fair_probs(p, "ps", "close", "1x2")
    ok = mkt.notna().all(axis=1)
    model_p = pd.concat([p.loc[ok, f"p_{o}"] for o in "hda"], ignore_index=True)
    mkt_p = pd.concat([mkt.loc[ok, o] for o in "hda"], ignore_index=True)
    y = pd.concat([act.loc[ok, o] for o in "hda"], ignore_index=True)
    bins = [0, .1, .15, .2, .25, .3, .35, .4, .45, .5, .55, .6, .65, .7, .8, 1]

    fig, ax = plt.subplots(figsize=(6, 5.2), dpi=150)
    _style(ax)
    ax.plot([0, 1], [0, 1], color=INK_MUTED, linewidth=1, linestyle="--")
    ax.text(0.83, 0.86, "perfekt", color=INK_MUTED, fontsize=8, rotation=40)
    for i, (name, probs) in enumerate([("Poisson-modell", model_p), ("Pinnacle stängning", mkt_p)]):
        c = calibration_table(probs, y, bins)
        c = c[c["n"] >= 30]
        ax.plot(c["predicted"], c["actual"], color=COLORS[i], linewidth=2, marker="o",
                markersize=5, markeredgecolor="#fcfcfb", markeredgewidth=1.5, label=name)
    ax.set_xlim(0, 0.9), ax.set_ylim(0, 0.9)
    ax.set_xlabel("Förutsagd sannolikhet", color=INK, fontsize=10)
    ax.set_ylabel("Faktisk andel som inträffade", color=INK, fontsize=10)
    ax.set_title("Kalibrering 1X2 (alla ligor)", color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def cumulative_figure(preds, strategies, path, title):
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    _style(ax)
    ax.axhline(0, color=INK_MUTED, linewidth=0.8)
    for i, (label, (src, book, market, th)) in enumerate(strategies.items()):
        b = select_bets(preds, src, book, market, th)
        if b.empty:
            continue
        cum = b["profit"].cumsum().to_numpy()
        ax.plot(b["date"], cum, color=COLORS[i], linewidth=2, label=f"{label} ({len(b)} spel)")
        ax.annotate(f"{cum[-1]:+.0f}", (b["date"].iloc[-1], cum[-1]), xytext=(4, 0),
                    textcoords="offset points", fontsize=8, color=INK, va="center")
    ax.set_ylabel("Ackumulerad vinst (enheter, 1 enhet per spel)", color=INK, fontsize=9)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="lower left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    REPORTS.mkdir(exist_ok=True)
    preds = pd.read_csv(ROOT / "data" / "processed" / "predictions.csv", parse_dates=["date"])

    calibration_figure(preds, REPORTS / "calibration.png")
    cumulative_figure(preds, {
        "Modell → B365, value ≥ 5 %": ("model", "b365", "1x2", 0.05),
        "Modell → Max, value ≥ 5 %": ("model", "max", "1x2", 0.05),
    }, REPORTS / "cumulative_model.png", "Egen modell, 1X2")
    cumulative_figure(preds, {
        "Pinnacle → B365, value ≥ 0 %": ("pinnacle", "b365", "1x2", 0.0),
        "Pinnacle → B365, value ≥ 3 %": ("pinnacle", "b365", "1x2", 0.03),
        "Pinnacle → Max, value ≥ 3 %": ("pinnacle", "max", "1x2", 0.03),
    }, REPORTS / "cumulative_pinnacle.png", "Utan modell: Pinnacles rättvisa odds mot andra bolag, 1X2")

    sections = {
        "ACC_1X2": accuracy_md(preds, "1x2"),
        "ACC_OU": accuracy_md(preds, "ou25"),
        "MODEL_1X2": bets_table(preds, "model", "1x2", ["b365", "avg", "max"]),
        "MODEL_OU": bets_table(preds, "model", "ou25", ["b365", "avg", "max"]),
        "PIN_1X2": bets_table(preds, "pinnacle", "1x2", ["b365", "max"]),
        "PIN_OU": bets_table(preds, "pinnacle", "ou25", ["b365", "max"]),
    }
    template = (REPORTS / "backtest_template.md").read_text()
    for key, text in sections.items():
        template = template.replace("{{" + key + "}}", text)
    (REPORTS / "backtest.md").write_text(template)
    print("Wrote reports/backtest.md")


if __name__ == "__main__":
    main()
