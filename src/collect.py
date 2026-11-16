"""Hourly collector: decide per league whether to fetch odds, fetch, save snapshot.

Run:  python -m src.collect            (normally by GitHub Actions every hour)
      python -m src.collect --dry-run  (only print what would be fetched; free)

Decision per league (only the free /events endpoint is used to decide):
  close  a match kicks off within CLOSE_WINDOW_MINUTES and the league has not
         been fetched in the last 50 minutes -> as close to kick-off as we get
  early  a match is within EARLY_WINDOW_HOURS and the league has not been
         fetched in the last EARLY_MIN_GAP_HOURS -> price a day or so before
Budget: below RESERVE_FOR_CLOSING credits only "close", below STOP_BELOW nothing.
The event lists are cached for EVENTS_CACHE_HOURS in data/cache/ so we do not
call the API every hour just to see the fixture list.
"""

import argparse
import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src import config
from src.odds_api import OddsApi, save_snapshot, utcnow

_SNAP = re.compile(r"^(?P<sport>.+)_(?P<hms>\d{6})_(?P<kind>early|close)\.json\.gz$")


def snapshot_times(sport: str, root: Path | None = None) -> list[datetime]:
    """Times of earlier snapshots for this league, from the file names."""
    root = root or config.SNAPSHOT_DIR
    times = []
    for path in Path(root).rglob(f"{sport}_*.json.gz"):
        m = _SNAP.match(path.name)
        if not m or m.group("sport") != sport:
            continue
        y, mo, d = path.parent.parts[-3:]
        t = datetime.strptime(f"{y}{mo}{d}{m.group('hms')}", "%Y%m%d%H%M%S")
        times.append(t.replace(tzinfo=timezone.utc))
    return sorted(times)


def parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def decide(now: datetime, kickoffs: list[datetime], previous: list[datetime],
           remaining: int | None) -> str | None:
    """Return "close", "early" or None for one league."""
    if remaining is not None and remaining < config.STOP_BELOW:
        return None
    future = [k for k in kickoffs if k > now]
    if not future:
        return None
    last = previous[-1] if previous else None
    minutes_to_next = (min(future) - now).total_seconds() / 60
    if minutes_to_next <= config.CLOSE_WINDOW_MINUTES and (last is None or now - last > timedelta(minutes=50)):
        return "close"
    if remaining is not None and remaining < config.RESERVE_FOR_CLOSING:
        return None
    soon = [k for k in future if k - now <= timedelta(hours=config.EARLY_WINDOW_HOURS)]
    if soon and (last is None or now - last > timedelta(hours=config.EARLY_MIN_GAP_HOURS)):
        return "early"
    return None


def cached_events(api: OddsApi, sport: str, now: datetime) -> list:
    """Event list from cache if younger than EVENTS_CACHE_HOURS, else from the (free) API."""
    path = config.CACHE_DIR / f"events_{sport}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        age = now - parse_time(cached["fetched_at"])
        if timedelta(0) <= age < timedelta(hours=config.EVENTS_CACHE_HOURS):
            return cached["events"]
    events = api.events(sport)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": now.isoformat(), "events": events}))
    return events


def last_remaining(log_path: Path | None = None) -> int | None:
    """Credits left according to the last logged API call."""
    path = Path(log_path or config.API_LOG)
    if not path.exists():
        return None
    rem = None
    with path.open() as f:
        for row in csv.DictReader(f):
            if row.get("remaining"):
                rem = int(float(row["remaining"]))
    return rem


def run(api: OddsApi, now: datetime | None = None, dry_run: bool = False) -> list[tuple[str, str]]:
    now = now or utcnow()
    done = []
    for sport in config.LEAGUES:
        try:
            events = cached_events(api, sport, now)
        except Exception as e:  # league out of season or unknown key -> skip
            print(f"{sport}: events failed ({e})")
            continue
        kickoffs = [parse_time(e["commence_time"]) for e in events]
        remaining = api.remaining if api.remaining is not None else last_remaining(api.log_path)
        kind = decide(now, kickoffs, snapshot_times(sport), remaining)
        print(f"{sport}: {len(events)} events, credits left {remaining}, decision {kind}")
        if kind is None or dry_run:
            continue
        data = api.odds(sport)
        path = save_snapshot(sport, kind, data, now)
        done.append((sport, kind))
        print(f"  saved {path.name} ({len(data)} events, credits left {api.remaining})")
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        api = OddsApi()
    except RuntimeError as e:  # no key yet: do nothing instead of failing every hour
        print(f"Skipping: {e}")
        raise SystemExit(0)
    run(api, dry_run=args.dry_run)
