"""Model v2: time-weighted Poisson ratings (maximum likelihood with a prior) + Dixon-Coles.

Expected goals:
  lambda_home = base * home_adv * att[home] * dfn[away]
  lambda_away = base *            att[away] * dfn[home]
att > 1 = scores more than average, dfn > 1 = concedes more than average.

Fitting: we maximise the (weighted) Poisson likelihood with a Gamma prior
on every att/dfn that has mean `prior` and weight `kappa` (= kappa phantom
matches at prior level). This gives simple fixed-point updates:
  att_i = (weighted goals scored by i + kappa * prior_att_i)
          / (weighted expected goals for i at att_i = 1 + kappa)
and the same for dfn. Older matches get weight 0.5 ** (age / half_life).

Dixon-Coles: multiplies the probabilities of 0-0, 1-0, 0-1, 1-1 by a factor
depending on rho, because real football has more 0-0/1-1 than pure Poisson.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import poisson

MAX_GOALS = 10


@dataclass
class Ratings:
    att: np.ndarray
    dfn: np.ndarray
    base: float
    home_adv: float
    rho: float = 0.0

    def expected_goals(self, h: np.ndarray, a: np.ndarray):
        lam_h = self.base * self.home_adv * self.att[h] * self.dfn[a]
        lam_a = self.base * self.att[a] * self.dfn[h]
        return lam_h, lam_a


def fit_ratings(h, a, hg, ag, w, n_teams, kappa=5.0, prior_att=None, prior_dfn=None,
                init: Ratings | None = None, n_iter=200, tol=1e-6) -> Ratings:
    """Fit att/dfn/base/home_adv. h, a are team indices 0..n_teams-1."""
    h, a = np.asarray(h), np.asarray(a)
    hg, ag, w = (np.asarray(x, dtype=float) for x in (hg, ag, w))
    p_att = np.ones(n_teams) if prior_att is None else np.asarray(prior_att, float)
    p_dfn = np.ones(n_teams) if prior_dfn is None else np.asarray(prior_dfn, float)

    if init is None:
        att, dfn = p_att.copy(), p_dfn.copy()
        base = (w @ ag) / w.sum()  # away goals per match
        home_adv = (w @ hg) / max(w @ ag, 1e-9)
    else:
        att, dfn, base, home_adv = init.att.copy(), init.dfn.copy(), init.base, init.home_adv

    scored = np.bincount(h, w * hg, n_teams) + np.bincount(a, w * ag, n_teams)
    conceded = np.bincount(h, w * ag, n_teams) + np.bincount(a, w * hg, n_teams)

    for _ in range(n_iter):
        old = att.copy()
        # expected goals with att of the scorer set to 1
        e_att = (np.bincount(h, w * base * home_adv * dfn[a], n_teams)
                 + np.bincount(a, w * base * dfn[h], n_teams))
        att = (scored + kappa * p_att) / (e_att + kappa)
        e_dfn = (np.bincount(a, w * base * home_adv * att[h], n_teams)
                 + np.bincount(h, w * base * att[a], n_teams))
        dfn = (conceded + kappa * p_dfn) / (e_dfn + kappa)
        lam_h = base * home_adv * att[h] * dfn[a]
        lam_a = base * att[a] * dfn[h]
        home_adv *= (w @ hg) / (w @ lam_h)
        lam_h = base * home_adv * att[h] * dfn[a]
        base *= (w @ (hg + ag)) / (w @ (lam_h + lam_a))
        if np.max(np.abs(att - old)) < tol:
            break
    return Ratings(att=att, dfn=dfn, base=base, home_adv=home_adv)


def dc_tau(x, y, lam_h, lam_a, rho):
    """Dixon-Coles correction factor for score (x, y)."""
    tau = np.ones(np.broadcast(x, y, lam_h, lam_a).shape)
    tau = np.where((x == 0) & (y == 0), 1 - lam_h * lam_a * rho, tau)
    tau = np.where((x == 0) & (y == 1), 1 + lam_h * rho, tau)
    tau = np.where((x == 1) & (y == 0), 1 + lam_a * rho, tau)
    tau = np.where((x == 1) & (y == 1), 1 - rho, tau)
    return np.clip(tau, 1e-6, None)


def fit_rho(lam_h, lam_a, hg, ag, w) -> float:
    """Rho maximising the weighted Dixon-Coles part of the likelihood."""
    low = (np.asarray(hg) <= 1) & (np.asarray(ag) <= 1)
    if not low.any():
        return 0.0
    args = (np.asarray(hg)[low], np.asarray(ag)[low], np.asarray(lam_h)[low],
            np.asarray(lam_a)[low])
    wl = np.asarray(w)[low]

    def nll(rho):
        return -(wl * np.log(dc_tau(*args, rho))).sum()

    return float(minimize_scalar(nll, bounds=(-0.25, 0.25), method="bounded").x)


def score_matrices(lam_h, lam_a, rho=0.0, max_goals=MAX_GOALS) -> np.ndarray:
    """Batch of score matrices, shape (n, max_goals+1, max_goals+1).

    Tail (>= max_goals) is put in the last row/column so each matrix sums to 1.
    """
    lam_h = np.atleast_1d(np.asarray(lam_h, float))
    lam_a = np.atleast_1d(np.asarray(lam_a, float))
    rho = np.broadcast_to(np.asarray(rho, float), lam_h.shape)
    g = np.arange(max_goals + 1)
    ph = poisson.pmf(g[None, :], lam_h[:, None])
    pa = poisson.pmf(g[None, :], lam_a[:, None])
    ph[:, -1] += 1 - ph.sum(axis=1)
    pa[:, -1] += 1 - pa.sum(axis=1)
    m = ph[:, :, None] * pa[:, None, :]
    for x, y in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        m[:, x, y] *= dc_tau(x, y, lam_h, lam_a, rho)
    return m / m.sum(axis=(1, 2), keepdims=True)


def matrix_probs(m: np.ndarray) -> dict:
    """1X2, over/under 2.5 and BTTS from a batch of score matrices."""
    n = m.shape[1]
    i, j = np.indices((n, n))
    over = m[:, (i + j) > 2].sum(axis=1)
    btts = m[:, (i > 0) & (j > 0)].sum(axis=1)
    return {
        "h": m[:, i > j].sum(axis=1), "d": m[:, i == j].sum(axis=1), "a": m[:, i < j].sum(axis=1),
        "o25": over, "u25": 1 - over, "btts_yes": btts, "btts_no": 1 - btts,
    }


def goal_diff_dist(m: np.ndarray) -> np.ndarray:
    """P(home goals - away goals = k) for k = -G..G, shape (n, 2G+1)."""
    n = m.shape[1]
    i, j = np.indices((n, n))
    diff = (i - j).ravel() + (n - 1)
    flat = m.reshape(m.shape[0], -1)
    out = np.zeros((m.shape[0], 2 * n - 1))
    for k in range(2 * n - 1):
        out[:, k] = flat[:, diff == k].sum(axis=1)
    return out
