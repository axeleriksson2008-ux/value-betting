"""Asian handicap: settlement and expected profit.

The line is given for the HOME team (football-data's AHh), e.g. -0.5 means
home starts one half goal behind. For the away bet the handicap is -line.

Settlement of one unit at decimal odds o, with x = goal difference + handicap:
  x > 0: win (o - 1)   x == 0: push (0)   x < 0: lose (-1)
Quarter lines (e.g. -0.75) split the stake in two halves on the two
neighbouring lines (-0.5 and -1.0).
"""

import numpy as np


def _single_line(x, odds):
    return np.where(x > 0, odds - 1, np.where(x < 0, -1.0, 0.0))


def _split(line):
    """Quarter line -> two half-stake lines; other lines -> same line twice."""
    line = np.asarray(line, float)
    quarter = np.isclose((line * 4) % 2, 1)
    return np.where(quarter, line - 0.25, line), np.where(quarter, line + 0.25, line)


def ah_profit(hg, ag, line, odds, side):
    """Realised profit of 1 unit on the home ('ahh') or away ('aha') handicap."""
    diff = np.asarray(hg, float) - np.asarray(ag, float)
    if side == "aha":
        diff, line = -diff, -np.asarray(line, float)
    l1, l2 = _split(line)
    profit = 0.5 * _single_line(diff + l1, odds) + 0.5 * _single_line(diff + l2, odds)
    return np.where(np.isnan(line) | np.isnan(odds), np.nan, profit)


def ah_expected_profit(diff_dist, line, odds, side):
    """Expected profit per unit given P(goal diff = k), k = -G..G (from goal_diff_dist)."""
    diff_dist = np.atleast_2d(diff_dist)
    g = (diff_dist.shape[1] - 1) // 2
    k = np.arange(-g, g + 1)[None, :]
    line = np.asarray(line, float).reshape(-1, 1)
    odds = np.asarray(odds, float).reshape(-1, 1)
    if side == "aha":
        k, line = -k, -line
    l1, l2 = _split(line)
    pay = 0.5 * _single_line(k + l1, odds) + 0.5 * _single_line(k + l2, odds)
    ev = (diff_dist * pay).sum(axis=1)
    missing = np.isnan(line[:, 0]) | np.isnan(odds[:, 0]) | np.isnan(diff_dist).any(axis=1)
    return np.where(missing, np.nan, ev)
