"""Build the SQLite database data/odds.sqlite from the raw snapshots.

The snapshots (gzipped JSON) are the source of truth and are committed to git.
The database is derived from them and can always be rebuilt:  python -m src.oddsdb

Tables
  snapshots(id, sport, kind, fetched_at)
  events(event_id, sport, commence_time, home, away)
  prices(snapshot_id, event_id, book, market, outcome, price, last_update)
      outcome: h / d / a for h2h
  api_calls(time_utc, call, status, cost, remaining, used)
View
  closing: the last price per event, book and outcome from a snapshot taken
           before kick-off.
"""

import sqlite3
from pathlib import Path

import pandas as pd

from src import config
from src.odds_api import load_snapshots

SCHEMA = """
CREATE TABLE snapshots(id INTEGER PRIMARY KEY, sport TEXT, kind TEXT, fetched_at TEXT);
CREATE TABLE events(event_id TEXT PRIMARY KEY, sport TEXT, commence_time TEXT, home TEXT, away TEXT);
CREATE TABLE prices(snapshot_id INTEGER, event_id TEXT, book TEXT, market TEXT, outcome TEXT,
                    price REAL, last_update TEXT);
CREATE INDEX ix_prices_event ON prices(event_id, book, outcome);
CREATE VIEW closing AS
  SELECT p.event_id, p.book, p.outcome, p.price, s.fetched_at
  FROM prices p JOIN snapshots s ON s.id = p.snapshot_id JOIN events e ON e.event_id = p.event_id
  WHERE s.fetched_at < e.commence_time
    AND s.fetched_at = (SELECT MAX(s2.fetched_at) FROM prices p2 JOIN snapshots s2 ON s2.id = p2.snapshot_id
                        WHERE p2.event_id = p.event_id AND p2.book = p.book AND p2.outcome = p.outcome
                          AND s2.fetched_at < e.commence_time);
"""


def h2h_outcome(name: str, home: str, away: str) -> str | None:
    if name == home:
        return "h"
    if name == away:
        return "a"
    if name.lower() == "draw":
        return "d"
    return None


def snapshot_rows(snap: dict):
    """Flatten one snapshot into event rows and price rows."""
    events, prices = [], []
    for ev in snap["events"]:
        events.append((ev["id"], snap["sport"], ev["commence_time"], ev["home_team"], ev["away_team"]))
        for bm in ev.get("bookmakers", []):
            for mk in bm.get("markets", []):
                if mk["key"] != "h2h":
                    continue
                for o in mk["outcomes"]:
                    out = h2h_outcome(o["name"], ev["home_team"], ev["away_team"])
                    if out:
                        prices.append((ev["id"], bm["key"], "h2h", out, float(o["price"]),
                                       mk.get("last_update", bm.get("last_update"))))
    return events, prices


def build(db_path: Path | None = None, snapshot_dir: Path | None = None,
          api_log: Path | None = None) -> sqlite3.Connection:
    db_path = Path(db_path or config.DB_PATH)
    snapshot_dir = snapshot_dir or config.SNAPSHOT_DIR
    api_log = api_log or config.API_LOG
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    for snap in load_snapshots(snapshot_dir):
        cur = con.execute("INSERT INTO snapshots(sport, kind, fetched_at) VALUES (?,?,?)",
                          (snap["sport"], snap["kind"], snap["fetched_at"]))
        sid = cur.lastrowid
        events, prices = snapshot_rows(snap)
        con.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?)", events)
        con.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?)", [(sid, *p) for p in prices])
    if Path(api_log).exists():
        pd.read_csv(api_log).to_sql("api_calls", con, index=False)
    con.commit()
    return con


def price_table(con: sqlite3.Connection) -> pd.DataFrame:
    """All prices with snapshot and event info, one row per price."""
    return pd.read_sql(
        """SELECT s.id AS snapshot_id, s.sport, s.kind, s.fetched_at, e.event_id, e.commence_time,
                  e.home, e.away, p.book, p.outcome, p.price
           FROM prices p JOIN snapshots s ON s.id = p.snapshot_id JOIN events e ON e.event_id = p.event_id""",
        con, parse_dates=["fetched_at", "commence_time"])


if __name__ == "__main__":
    con = build()
    n = con.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    print(f"Built {config.DB_PATH} with {n} prices")
