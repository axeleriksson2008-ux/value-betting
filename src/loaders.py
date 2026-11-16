"""Load football-data.co.uk CSV files and normalise them to one common table.

Two source formats exist:
- "main" leagues (one file per league and season, e.g. E0_2425.csv):
  HomeTeam, AwayTeam, FTHG, FTAG, early odds (PSH, B365H, ...) and
  closing odds (PSCH, B365CH, ...), over/under 2.5 and Asian handicap.
- "extra" leagues (one file with all seasons, e.g. SWE.csv):
  Home, Away, HG, AG and only closing 1X2 odds.

Output columns (missing data -> NaN):
  date, league, season, home, away, hg, ag,
  {book}_{timing}_{outcome}      odds
  ah_line_{timing}               Asian handicap line for the HOME team (e.g. -0.5)
where timing in (early, close) and outcome in
  h, d, a        1X2
  o25, u25       over/under 2.5 goals
  ahh, aha       Asian handicap home / away

"early" = odds collected by football-data a few days before kick-off.
"""

from pathlib import Path
import re

import pandas as pd

TIMINGS = ["early", "close"]

# book -> source prefix, per market. Close odds insert "C" after the prefix.
BOOKS_1X2 = {
    "ps": "PS", "b365": "B365", "bw": "BW", "iw": "IW", "wh": "WH", "vc": "VC",
    "bf": "BF", "bfe": "BFE", "1xb": "1XB", "bfd": "BFD", "bmgm": "BMGM", "bv": "BV",
    "cl": "CL", "lb": "LB", "max": "Max", "avg": "Avg",
}
BOOKS_OU = {"ps": "P", "b365": "B365", "bfe": "BFE", "max": "Max", "avg": "Avg"}
BOOKS_AH = BOOKS_OU

MARKET_OUTCOMES = {"1x2": ["h", "d", "a"], "ou25": ["o25", "u25"], "ah": ["ahh", "aha"]}
MARKET_BOOKS = {"1x2": BOOKS_1X2, "ou25": BOOKS_OU, "ah": BOOKS_AH}


def _source_name(prefix: str, timing: str, outcome: str) -> str:
    c = "C" if timing == "close" else ""
    if outcome in ("h", "d", "a"):
        return f"{prefix}{c}{outcome.upper()}"
    if outcome in ("o25", "u25"):
        return f"{prefix}{c}{'>' if outcome == 'o25' else '<'}2.5"
    return f"{prefix}{c}AH{'H' if outcome == 'ahh' else 'A'}"


def odds_columns() -> list[str]:
    cols = []
    for market, books in MARKET_BOOKS.items():
        for book in books:
            for t in TIMINGS:
                cols += [f"{book}_{t}_{o}" for o in MARKET_OUTCOMES[market]]
    return cols


ODDS_COLUMNS = odds_columns()
AH_LINE_COLUMNS = ["ah_line_early", "ah_line_close"]
BASE_COLUMNS = ["date", "league", "season", "home", "away", "hg", "ag"]


def _add_odds(raw: pd.DataFrame, out: pd.DataFrame) -> pd.DataFrame:
    new = {}
    for market, books in MARKET_BOOKS.items():
        for book, prefix in books.items():
            for t in TIMINGS:
                for o in MARKET_OUTCOMES[market]:
                    src = _source_name(prefix, t, o)
                    col = pd.to_numeric(raw[src], errors="coerce") if src in raw.columns else float("nan")
                    new[f"{book}_{t}_{o}"] = col
    for t, src in [("early", "AHh"), ("close", "AHCh")]:
        new[f"ah_line_{t}"] = pd.to_numeric(raw[src], errors="coerce") if src in raw.columns else float("nan")
    odds = pd.DataFrame(new, index=out.index)
    # Odds <= 1 are data errors
    odds[ODDS_COLUMNS] = odds[ODDS_COLUMNS].where(odds[ODDS_COLUMNS] > 1.0)
    return pd.concat([out, odds], axis=1)


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except UnicodeDecodeError:  # a few files are Windows-1252
        return pd.read_csv(path, encoding="cp1252", low_memory=False)


def _parse_dates(s: pd.Series) -> pd.Series:
    # football-data uses dd/mm/yyyy (and dd/mm/yy in some old files).
    return pd.to_datetime(s, dayfirst=True, format="mixed")


def read_main_league(path: Path, league: str, season: int) -> pd.DataFrame:
    """Read one main-league file (e.g. E0_2425.csv). `season` = start year."""
    raw = _read_csv(path).dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
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
    """Read an extra-league file (e.g. SWE.csv) containing all seasons.

    Season labels are "2012" or "2012/2013"; we keep the start year.
    """
    raw = _read_csv(path).dropna(subset=["Home", "Away", "HG", "AG"])
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


_MAIN_FILE = re.compile(r"^(?P<league>[A-Z]+\d?)_(?P<season>\d{4})\.csv$")


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
    df = df[BASE_COLUMNS + AH_LINE_COLUMNS + ODDS_COLUMNS]
    df = df.drop_duplicates(subset=["date", "league", "home", "away"])
    return df.sort_values(["date", "league", "home"], kind="stable").reset_index(drop=True)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    matches = load_all(root / "data" / "raw")
    out_path = root / "data" / "processed" / "matches.parquet"
    matches.to_parquet(out_path, index=False)
    print(f"Saved {len(matches)} matches to {out_path}")
    print(matches.groupby("league")["season"].agg(["min", "max", "count"]).to_string())
