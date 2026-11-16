"""Evaluate the match-statistics models and export current ratings for the app.

- Parameters (half-life, kappa) chosen per statistic on VALIDATION (log score).
- Dispersion (alpha) per league and statistic estimated on VALIDATION.
- TEST: log score vs a league-average baseline, calibration of over/under lines.
Writes reports/stats_model.md, reports/stats_calibration.png, data/stat_ratings.json.
"""

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src import config  # noqa: E402
from src import stats_model as sm  # noqa: E402
from src.report import COLORS, INK, INK_MUTED, _style  # noqa: E402
from src.walkforward import TEST_START, VAL_START, Params  # noqa: E402

ROOT = config.ROOT
GRID = [(180, 5), (365, 10), (365, 20), (730, 20), (730, 50)]
BASELINE = Params(half_life=365, kappa=1e6)  # all teams equal: only league average + home advantage


def alphas_by_league(pred: pd.DataFrame) -> dict:
    """Team-level and total-level dispersion per league (+ '_all' fallback)."""
    ok = pred.dropna(subset=["lam_h"])
    out = {}
    for league, g in list(ok.groupby("league")) + [("_all", ok)]:
        y = np.r_[g["hg"], g["ag"]]
        mu = np.r_[g["lam_h"], g["lam_a"]]
        out[league] = {"team": sm.estimate_alpha(y, mu),
                       "total": sm.estimate_alpha(g["hg"] + g["ag"], g["lam_h"] + g["lam_a"])}
    return out


def scored(pred: pd.DataFrame, alphas: dict) -> pd.DataFrame:
    """Add per-match log scores (team-level sum and total)."""
    p = pred.dropna(subset=["lam_h"]).copy()
    at = p["league"].map(lambda l: alphas.get(l, alphas["_all"])["team"])
    aT = p["league"].map(lambda l: alphas.get(l, alphas["_all"])["total"])
    p["ls_team"] = [sm.log_score(h, lh, a) + sm.log_score(aw, la, a)
                    for h, aw, lh, la, a in zip(p["hg"], p["ag"], p["lam_h"], p["lam_a"], at)]
    p["ls_total"] = [float(sm.log_score(h + aw, lh + la, a))
                     for h, aw, lh, la, a in zip(p["hg"], p["ag"], p["lam_h"], p["lam_a"], aT)]
    p["alpha_total"] = aT
    return p


def main():
    m = sm.add_cards(pd.read_parquet(ROOT / "data" / "processed" / "matches.parquet"))
    rows, chosen, alphas_all, test_scores = [], {}, {}, {}
    calib = []
    for stat in sm.STATS:
        # ---- validation: choose parameters
        best = None
        for hl, kappa in GRID:
            p = Params(half_life=hl, kappa=kappa)
            val = sm.walk_forward(m, stat, p, VAL_START, TEST_START)
            val = val[(val.date >= VAL_START) & (val.date < TEST_START)]
            al = alphas_by_league(val)
            ls = scored(val, al)["ls_team"].mean()
            print(stat, hl, kappa, round(ls, 4), flush=True)
            if best is None or ls > best[0]:
                best = (ls, p, al)
        _, p, al = best
        chosen[stat], alphas_all[stat] = p, al
        base_val = sm.walk_forward(m, stat, BASELINE, VAL_START, TEST_START)
        base_al = alphas_by_league(base_val[(base_val.date >= VAL_START) & (base_val.date < TEST_START)])

        # ---- test
        test = scored(sm.walk_forward(m, stat, p, TEST_START, None), al)
        base = scored(sm.walk_forward(m, stat, BASELINE, TEST_START, None), base_al)
        both = test.join(base[["ls_team", "ls_total"]], rsuffix="_base", how="inner")
        d_tot = both["ls_total"] - both["ls_total_base"]
        rows.append({
            "stat": stat, "half_life": p.half_life, "kappa": p.kappa, "matches": len(both),
            "mean_total": (both.hg + both.ag).mean(),
            "pred_total": (both.lam_h + both.lam_a).mean(),
            "mae_model": (both.hg + both.ag - both.lam_h - both.lam_a).abs().mean(),
            "corr_model": np.corrcoef(both.hg + both.ag, both.lam_h + both.lam_a)[0, 1],
            "ls_gain_team": (both["ls_team"] - both["ls_team_base"]).mean(),
            "ls_gain_total": d_tot.mean(),
            "ls_gain_total_se": d_tot.std() / np.sqrt(len(d_tot)),
            "alpha_total": al["_all"]["total"], "alpha_team": al["_all"]["team"],
        })
        # calibration: over-probabilities for three lines around the median total
        med = np.median(both.hg + both.ag)
        for line in [med - 1.5, med - 0.5, med + 0.5, med + 1.5]:
            pr = np.array([sm.over_under(line, mu, a)["over"]
                           for mu, a in zip(both.lam_h + both.lam_a, both.alpha_total)])
            calib.append(pd.DataFrame({"stat": stat, "line": line, "p": pr,
                                       "y": ((both.hg + both.ag) > line).astype(int)}))
    res = pd.DataFrame(rows)
    calib = pd.concat(calib)
    res.to_csv(ROOT / "reports" / "stats_model_results.csv", index=False)
    calib_fig(calib, ROOT / "reports" / "stats_calibration.png")
    write_report(res, calib)

    # ---- ratings for the app: fitted on everything up to today, alphas from validation
    ratings = {"by_stat_params": {s: {"half_life": p.half_life, "kappa": p.kappa} for s, p in chosen.items()}}
    merged = None
    for stat, p in chosen.items():
        r = sm.current_ratings(m[list(m.columns)], p, {stat: alphas_all[stat]})
        r["leagues"] = {lg: {k: v for k, v in d.items() if k in ("teams", stat)} for lg, d in r["leagues"].items()}
        if merged is None:
            merged = r
        else:
            for lg, d in r["leagues"].items():
                merged["leagues"].setdefault(lg, {"teams": d["teams"]}).update({stat: d[stat]} if stat in d else {})
    merged.update(ratings)
    sm.save_ratings(merged)
    print(res.round(4).to_string())


def calib_fig(calib, path):
    fig, axes = plt.subplots(1, 5, figsize=(15, 3.4), dpi=150, sharey=True)
    for ax, (stat, g) in zip(axes, calib.groupby("stat", sort=False)):
        _style(ax)
        ax.plot([0, 1], [0, 1], color=INK_MUTED, linewidth=1, linestyle="--")
        b = pd.cut(g["p"], np.linspace(0, 1, 11))
        t = g.groupby(b, observed=True).agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"))
        t = t[t["n"] >= 50]
        ax.plot(t["p"], t["y"], color=COLORS[0], linewidth=2, marker="o", markersize=4,
                markeredgecolor="#fcfcfb")
        ax.set_title(sm.STAT_NAME[stat], color=INK, fontsize=10, loc="left")
        ax.set_xlim(0, 1), ax.set_ylim(0, 1)
        ax.set_xlabel("Förutsagd P(över)", color=INK, fontsize=8)
    axes[0].set_ylabel("Faktisk andel över", color=INK, fontsize=8)
    fig.suptitle("Kalibrering över/under (matchtotal), testperioden", color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def write_report(res, calib):
    lines = ["# Statistikspel – skott, skott på mål, fouls, hörnor, kort", "",
             "*Genereras av `python -m src.stats_eval`. Parametrar valda på 2020–23, test 2023–26, "
             "21 huvudligor (National League saknar statistik).*", "",
             "## Resultat på testperioden", "",
             "| Statistik | Matcher | Snitt per match (faktiskt / modell) | Medelfel | Korrelation | "
             "Bättre än ligasnitt? (log score per match, total) | Spridning α (total) |",
             "|---|---|---|---|---|---|---|"]
    for r in res.itertuples():
        lo, hi = r.ls_gain_total - 1.96 * r.ls_gain_total_se, r.ls_gain_total + 1.96 * r.ls_gain_total_se
        verdict = "ja" if lo > 0 else ("nej" if hi < 0 else "oklart")
        lines.append(f"| {sm.STAT_NAME[r.stat]} | {r.matches} | {r.mean_total:.2f} / {r.pred_total:.2f} "
                     f"| {r.mae_model:.2f} | {r.corr_model:.2f} | {verdict}: {r.ls_gain_total:+.4f} "
                     f"({lo:+.4f} … {hi:+.4f}) | {r.alpha_total:.3f} |")
    lines += ["", "Log score = hur stor sannolikhet modellen gav det som faktiskt hände (logaritmerat). "
              "Positiv skillnad = modellen är bättre än en modell som bara känner ligans snitt och hemmafördel.",
              "", "![Kalibrering](stats_calibration.png)", "",
              "## Kalibrering per linje (matchtotal)", "",
              "| Statistik | Linje | Förutsagd andel över | Faktisk andel över | Matcher |", "|---|---|---|---|---|"]
    for (stat, line), g in calib.groupby(["stat", "line"], sort=False):
        lines.append(f"| {sm.STAT_NAME[stat]} | {line:.1f} | {g.p.mean():.1%} | {g.y.mean():.1%} | {len(g)} |")
    (ROOT / "reports" / "stats_model_body.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
