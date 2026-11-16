"""Small client for The Odds API v4 with call logging and raw snapshot storage.

The API key is sent in the `x-api-key` header, read from the environment
variable ODDS_API_KEY (or from .env). In the Claude cloud session the network
proxy injects the real key, so the variable can be a placeholder there.

Every call is appended to data/api_calls.csv with its cost and credits left,
so we always know how much of the monthly quota is used.
Every odds response is saved as a gzipped JSON snapshot (never overwritten).
"""

import csv
import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from src import config


def load_api_key() -> str:
    key = os.environ.get("ODDS_API_KEY")
    if key:
        return key
    env = config.ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("ODDS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("ODDS_API_KEY is not set (put it in .env or as a GitHub secret)")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OddsApi:
    def __init__(self, api_key: str | None = None, session=None, log_path: Path | None = None):
        self.api_key = api_key or load_api_key()
        self.session = session or requests.Session()
        self.log_path = Path(log_path or config.API_LOG)
        self.remaining: int | None = None

    def _get(self, path: str, params: dict, label: str):
        r = self.session.get(
            config.API_HOST + path, params=params, timeout=30,
            headers={"x-api-key": self.api_key, "Accept-Encoding": "gzip"},
        )
        cost = r.headers.get("x-requests-last")
        remaining = r.headers.get("x-requests-remaining")
        if remaining is not None:
            self.remaining = int(float(remaining))
        self._log(label, r.status_code, cost, remaining, r.headers.get("x-requests-used"))
        r.raise_for_status()
        return r.json()

    def _log(self, label, status, cost, remaining, used):
        new = not self.log_path.exists()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time_utc", "call", "status", "cost", "remaining", "used"])
            w.writerow([utcnow().isoformat(timespec="seconds"), label, status, cost, remaining, used])

    # ---- endpoints ----
    def sports(self) -> list:
        """Free: list of sports."""
        return self._get("/v4/sports/", {"all": "true"}, "sports")

    def events(self, sport: str) -> list:
        """Free: upcoming events (id, teams, commence_time) without odds."""
        return self._get(f"/v4/sports/{sport}/events", {"dateFormat": "iso"}, f"events:{sport}")

    def odds(self, sport: str, bookmakers=config.BOOKMAKERS, markets=config.MARKETS) -> list:
        """Costs len(markets) credits per started group of 10 bookmakers."""
        params = {"bookmakers": ",".join(bookmakers), "markets": ",".join(markets),
                  "oddsFormat": "decimal", "dateFormat": "iso"}
        return self._get(f"/v4/sports/{sport}/odds", params, f"odds:{sport}")


def save_snapshot(sport: str, kind: str, data: list, when: datetime | None = None,
                  root: Path | None = None) -> Path:
    """Store a raw odds response: data/snapshots/YYYY/MM/DD/<sport>_<HHMMSS>_<kind>.json.gz"""
    root = Path(root or config.SNAPSHOT_DIR)
    when = when or utcnow()
    folder = root / when.strftime("%Y/%m/%d")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sport}_{when.strftime('%H%M%S')}_{kind}.json.gz"
    payload = {"sport": sport, "kind": kind, "fetched_at": when.isoformat(timespec="seconds"),
               "events": data}
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    return path


def load_snapshots(root: Path | None = None):
    """Yield every stored snapshot dict, oldest first."""
    root = root or config.SNAPSHOT_DIR
    for path in sorted(Path(root).rglob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            yield json.load(f)
