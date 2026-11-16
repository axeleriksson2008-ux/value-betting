"""Generate FAKE demo data (fictional teams) so the app can be tried before real odds exist.

Writes to data/demo/ (not committed):  python -m src.demo
Nothing here is real: teams, odds and results are random.
"""

import shutil
from datetime import timedelta

import numpy as np
import pandas as pd

from src import betlog, config, live, oddsdb
from src.odds_api import save_snapshot, utcnow

DEMO_DIR = config.ROOT / "data" / "demo"
TEAMS = ["Northbridge", "Eastfield", "Westvale", "Southport Rovers", "Kingsmoor", "Ashby Town",
         "Redcliff", "Harrow Park", "Linton Athletic", "Oakham", "Brookside", "Fernley"]
LEAGUES = ["soccer_epl", "soccer_efl_champ", "soccer_spain_la_liga"]


def _odds(p, margin, rng, noise):
    q = p * np.exp(rng.normal(0, noise, 3))
    q = q / q.sum() * (1 + margin)
    return np.round(1 / q, 2)


def _event(eid, sport, home, away, kick, books):
    return {"id": eid, "sport_key": sport, "commence_time": kick.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "home_team": home, "away_team": away,
            "bookmakers": [{"key": k, "title": k, "markets": [{"key": "h2h", "outcomes": [
                {"name": home, "price": float(o[0])}, {"name": "Draw", "price": float(o[1])},
                {"name": away, "price": float(o[2])}]}]} for k, o in books.items()]}


def generate(seed: int = 7, n_past: int = 90, n_future: int = 12):
    rng = np.random.default_rng(seed)
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)
    snaps = DEMO_DIR / "snapshots"
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    truth = {}
    for i in range(n_past + n_future):
        sport = LEAGUES[i % len(LEAGUES)]
        home, away = rng.choice(TEAMS, 2, replace=False)
        if i < n_past:
            kick = now - timedelta(hours=int(rng.integers(2, 24 * 28)))
        else:
            kick = now + timedelta(hours=int(rng.integers(3, 48)))
        strength = rng.normal(0.25, 0.5)
        p = np.array([0.45 + 0.2 * np.tanh(strength), 0.26, 0.0])
        p[2] = 1 - p[0] - p[1]
        eid = f"demo{i:03d}"
        truth[eid] = p
        early = {"pinnacle": _odds(p, 0.025, rng, 0.03)}
        for b in config.SWEDISH_BOOKS:
            early[b] = _odds(p, 0.065, rng, 0.06)
        t_early = kick - timedelta(hours=24) - timedelta(minutes=i)  # unique file names
        if t_early < now:
            save_snapshot(sport, "early", [_event(eid, sport, home, away, kick, early)], t_early, root=snaps)
        else:
            continue
        t_close = kick - timedelta(minutes=40 + i % 7)
        if t_close < now:
            close = {"pinnacle": _odds(p, 0.025, rng, 0.03)}
            for b in config.SWEDISH_BOOKS:
                close[b] = _odds(p, 0.065, rng, 0.04)
            save_snapshot(sport, "close", [_event(eid, sport, home, away, kick, close)], t_close, root=snaps)
    # upcoming matches that are less than a day away got no early snapshot: give them one now
    for i in range(n_past, n_past + n_future):
        eid = f"demo{i:03d}"
        sport = LEAGUES[i % len(LEAGUES)]
        p = truth[eid]
        books = {"pinnacle": _odds(p, 0.025, rng, 0.03)}
        for b in config.SWEDISH_BOOKS:
            books[b] = _odds(p, 0.065, rng, 0.06)
        kick = now + timedelta(hours=3 + i - n_past)
        home, away = TEAMS[i % 12], TEAMS[(i + 5) % 12]
        save_snapshot(sport, "early", [_event(eid, sport, home, away, kick, books)],
                      now - timedelta(minutes=i), root=snaps)

    con = oddsdb.build(DEMO_DIR / "odds.sqlite", snaps, DEMO_DIR / "api_calls.csv")
    prices = oddsdb.price_table(con)
    sig = live.signals(prices)
    sig = sig[(sig["kind"] == "early") & (sig["commence_time"] < now)].drop_duplicates("event_id")
    bets = betlog.load_bets(DEMO_DIR / "none.csv")
    for r in sig.head(30).itertuples():
        stake = max(5.0, round(r.stake_share * 1000))
        bets = betlog.add_bet(bets, event_id=r.event_id, sport=r.sport, match=f"{r.home} – {r.away}",
                              commence_time=r.commence_time, outcome=r.outcome, book=r.book,
                              odds=r.odds, stake=stake, fair_odds=r.fair_odds,
                              placed_at=r.fetched_at, note="demo")
        p = truth[r.event_id]
        result = rng.choice(["h", "d", "a"], p=p)
        bets = betlog.set_status(bets, int(bets["bet_id"].iloc[-1]), "won" if result == r.outcome else "lost")
    betlog.save_bets(bets, DEMO_DIR / "bets.csv")
    pd.DataFrame([{"time_utc": now.isoformat(), "call": "demo", "status": 200, "cost": 0,
                   "remaining": 431, "used": 69}]).to_csv(DEMO_DIR / "api_calls.csv", index=False)
    return DEMO_DIR


if __name__ == "__main__":
    print(f"Demo data written to {generate()}")
