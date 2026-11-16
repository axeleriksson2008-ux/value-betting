"""Map team names from The Odds API to football-data.co.uk names.

The mapping lives in config/team_names.csv with columns
  sport, odds_api_name, football_data_name, status
status:
  manual  set or checked by hand -> never changed by this script
  auto    best fuzzy match, please check
  missing no good match found, please fill in by hand
Run:  python -m src.team_names   (adds new teams, keeps existing rows)
"""

import difflib
import re
import unicodedata
from pathlib import Path

import pandas as pd

from src import config

COLUMNS = ["sport", "odds_api_name", "football_data_name", "status"]
# common words that only add noise when comparing names
_NOISE = {"fc", "afc", "cf", "sc", "ac", "if", "ff", "bk", "fk", "ik", "sk", "club", "de", "the",
}
_ALIASES = {"manchester": "man", "nottingham": "nott'm", "wolverhampton": "wolves",
            "sheffield": "sheff", "saint": "st", "olympique": "", "borussia": "", "athletic": "ath"}


def normalise(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9' ]", " ", s)
    words = [_ALIASES.get(w, w) for w in s.split()]
    return " ".join(w for w in words if w and w not in _NOISE)


def best_match(name: str, candidates: list[str], cutoff: float = 0.6) -> str | None:
    if name in candidates:
        return name
    norm = {normalise(c): c for c in candidates}
    target = normalise(name)
    if target in norm:
        return norm[target]
    hits = difflib.get_close_matches(target, list(norm), n=1, cutoff=cutoff)
    if hits:
        return norm[hits[0]]
    # one name contained in the other, e.g. "Brighton and Hove Albion" vs "Brighton"
    for n, c in norm.items():
        if n and (n in target or target in n):
            return c
    return None


def load_mapping(path: Path | None = None) -> pd.DataFrame:
    path = Path(path or config.TEAM_MAP)
    if path.exists():
        return pd.read_csv(path, dtype=str).fillna("")
    return pd.DataFrame(columns=COLUMNS)


def update_mapping(odds_teams: dict[str, set[str]], fd_teams: dict[str, set[str]],
                   path: Path | None = None) -> pd.DataFrame:
    """odds_teams: sport -> Odds API names; fd_teams: sport -> football-data names."""
    path = Path(path or config.TEAM_MAP)
    m = load_mapping(path)
    keep = m[m["status"] == "manual"]
    known = set(zip(keep["sport"], keep["odds_api_name"]))
    rows = [keep]
    for sport, names in odds_teams.items():
        cands = sorted(fd_teams.get(sport, set()))
        for name in sorted(names):
            if (sport, name) in known:
                continue
            match = best_match(name, cands) if cands else None
            rows.append(pd.DataFrame([{"sport": sport, "odds_api_name": name,
                                       "football_data_name": match or "",
                                       "status": "auto" if match else "missing"}]))
    out = pd.concat(rows, ignore_index=True)[COLUMNS].sort_values(["sport", "odds_api_name"])
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def to_football_data(sport: str, name: str, mapping: pd.DataFrame) -> str | None:
    hit = mapping[(mapping["sport"] == sport) & (mapping["odds_api_name"] == name)]
    if hit.empty or not hit["football_data_name"].iloc[0]:
        return None
    return hit["football_data_name"].iloc[0]


def main():
    from src import oddsdb
    con = oddsdb.build()
    ev = pd.read_sql("SELECT sport, home, away FROM events", con)
    odds_teams = {s: set(g["home"]) | set(g["away"]) for s, g in ev.groupby("sport")}
    matches = pd.read_parquet(config.ROOT / "data" / "processed" / "matches.parquet")
    recent = matches[matches["date"] >= matches["date"].max() - pd.Timedelta(days=730)]
    fd_teams = {}
    for sport, code in config.LEAGUES.items():
        if code:
            lg = recent[recent["league"] == code]
            fd_teams[sport] = set(lg["home"]) | set(lg["away"])
    m = update_mapping(odds_teams, fd_teams)
    print(m["status"].value_counts().to_string())
    print(f"Check rows with status auto/missing in {config.TEAM_MAP}")


if __name__ == "__main__":
    main()
