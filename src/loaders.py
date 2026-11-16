"""Load football-data.co.uk CSV files and normalise them to one common table.

Two source formats exist:
- "main" leagues (one file per league and season, e.g. E0_2425.csv):
  HomeTeam, AwayTeam, FTHG, FTAG, early odds (PSH, B365H, MaxH, AvgH)
  and closing odds (PSCH, B365CH, MaxCH, AvgCH), plus over/under 2.5.
- "extra" leagues (one file with all seasons, e.g. SWE.csv):
  Home, Away, HG, AG and only closing 1X2 odds.

Output columns (missing data -> NaN):
  date, league, season, home, away, hg, ag,
  {book}_{timing}_{outcome}
where book in (ps, b365, max, avg), timing in (early, close)
and outcome in (h, d, a, o25, u25).

"early" = odds collected by football-data a few days before kick-off
(often called "opening" but it is really a snapshot, not the first price).
"""

from pathlib import Path
import re

import pandas as pd

BOOKS = ["ps", "b365", "max", "avg"]
TIMINGS = ["early", "close"]
OUTCOMES = ["h", "d", "a", "o25", "u25"]
ODDS_COLUMNS = [f"{b}_{t}_{o}" for b in BOOKS for t in TIMINGS for o in OUTCOMES]
BASE_COLUMNS = ["date", "league", "season", "home", "away", "hg", "ag"]

# Source column prefix per book, for 1X2 and for over/under 2.5.
# 1X2 early: PSH, close: PSCH. O/U early: P>2.5, close: PC>2.5.
_BOOK_1X2 = {"ps": "PS", "b365": "B365", "max": "Max", "avg": "Avg"}
_BOOK_OU = {"ps": "P", "b365": "B365", "max": "Max", "avg": "Avg"}


def _odds_source_name(book: str, timing: str, outcome: str) -> str:
    """Return the football-data column name for one normalised odds column."""
    close = "C" if timing == "close" else ""
    if outcome in ("h", "d", "a"):
        return f"{_BOOK_1X2[book]}{close}{outcome.upper()}"
    sign = ">" if outcome == "o25" else "<"
    return f"{_BOOK_OU[book]}{close}{sign}2.5"


def _add_odds(raw: pd.DataFrame, out: pd.DataFrame) -> pd.DataFrame:
    for col in ODDS_COLUMNS:
        src = _odds_source_name(*col.split("_"))
        out[col] = pd.to_numeric(raw[src], errors="coerce") if src in raw.columns else float("nan")
    return out


def _parse_dates(s: pd.Series) -> pd.Series:
    # football-data uses dd/mm/yyyy (and dd/mm/yy in some old files).
    return pd.to_datetime(s, dayfirst=True, format="mixed")


def read_main_league(path: Path, league: str, season: int) -> pd.DataFrame:
    """Read one main-league file (e.g. E0_2425.csv). `season` = start year."""
    raw = pd.read_csv(path, encoding="utf-8-sig")
    raw = raw.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    out = pd.DataFrame({
        "date": _parse_dates(raw["Date"]),
        "league": league,
        "season": season,
        "home": raw["HomeTeam"].str.strip(),
        "away": raw["AwayTeam"].str.strip(),
        "hg": raw["FTHG"].astype(int),
        "ag": raw["FTAG"].astype(int),
    })
    return _add_odds(raw, out)


def read_extra_league(path: Path, league: str) -> pd.DataFrame:
    """Read an extra-league file (e.g. SWE.csv) containing all seasons."""
    raw = pd.read_csv(path, encoding="utf-8-sig")
    raw = raw.dropna(subset=["Home", "Away", "HG", "AG"])
    out = pd.DataFrame({
        "date": _parse_dates(raw["Date"]),
        "league": league,
        "season": raw["Season"].astype(str).str[:4].astype(int),
        "home": raw["Home"].str.strip(),
        "away": raw["Away"].str.strip(),
        "hg": raw["HG"].astype(int),
        "ag": raw["AG"].astype(int),
    })
    return _add_odds(raw, out)


_MAIN_FILE = re.compile(r"^(?P<league>[A-Z]+\d)_(?P<season>\d{4})\.csv$")


def load_all(raw_dir: Path) -> pd.DataFrame:
    """Read every CSV in raw_dir, return one table sorted by date."""
    frames = []
    for path in sorted(Path(raw_dir).glob("*.csv")):
        m = _MAIN_FILE.match(path.name)
        if m:
            season = 2000 + int(m.group("season")[:2])
            frames.append(read_main_league(path, m.group("league"), season))
        else:
            frames.append(read_extra_league(path, path.stem))
    df = pd.concat(frames, ignore_index=True)
    df = df[BASE_COLUMNS + ODDS_COLUMNS]
    return df.sort_values(["date", "league", "home"], kind="stable").reset_index(drop=True)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    matches = load_all(root / "data" / "raw")
    out_path = root / "data" / "processed" / "matches.csv"
    matches.to_csv(out_path, index=False)
    print(f"Saved {len(matches)} matches to {out_path}")
    print(matches.groupby("league")["season"].agg(["min", "max", "count"]))
