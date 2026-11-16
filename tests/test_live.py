from datetime import datetime, timezone

import pandas as pd
import pytest

from src import live, oddsdb
from src.model import remove_margin
from src.odds_api import save_snapshot


def _event(eid, home, away, kick, books):
    return {"id": eid, "sport_key": "soccer_epl", "commence_time": kick, "home_team": home,
            "away_team": away,
            "bookmakers": [{"key": k, "title": k, "last_update": kick,
                            "markets": [{"key": "h2h", "outcomes": [
                                {"name": home, "price": h}, {"name": away, "price": a},
                                {"name": "Draw", "price": d}]}]} for k, (h, d, a) in books.items()]}


KICK = "2026-11-21T15:00:00Z"


@pytest.fixture
def db(tmp_path, monkeypatch):
    snaps = tmp_path / "snaps"
    # early: Pinnacle 2.00/3.60/3.90, Unibet gives 2.25 on home -> value
    save_snapshot("soccer_epl", "early", [_event("e1", "Arsenal", "Chelsea", KICK, {
        "pinnacle": (2.00, 3.60, 3.90), "unibet_se": (2.25, 3.30, 3.40),
        "svenskaspel_se": (1.95, 3.40, 3.70)})], datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc), root=snaps)
    # close: Pinnacle moved to 1.90 on home
    save_snapshot("soccer_epl", "close", [_event("e1", "Arsenal", "Chelsea", KICK, {
        "pinnacle": (1.90, 3.70, 4.20), "unibet_se": (2.00, 3.40, 3.80)})],
        datetime(2026, 11, 21, 14, 10, tzinfo=timezone.utc), root=snaps)
    # a snapshot after kick-off must be ignored
    save_snapshot("soccer_epl", "close", [_event("e1", "Arsenal", "Chelsea", KICK, {
        "pinnacle": (1.20, 6.0, 15.0)})], datetime(2026, 11, 21, 15, 30, tzinfo=timezone.utc), root=snaps)
    monkeypatch.setattr(live, "utcnow", lambda: datetime(2026, 11, 22, tzinfo=timezone.utc))
    con = oddsdb.build(tmp_path / "x.sqlite", snaps, tmp_path / "nolog.csv")
    return con


def test_db_contents(db):
    assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 3
    assert db.execute("SELECT home, away FROM events").fetchall() == [("Arsenal", "Chelsea")]
    rows = db.execute("SELECT outcome, price FROM prices WHERE book='unibet_se' AND snapshot_id=1 "
                      "ORDER BY outcome").fetchall()
    assert rows == [("a", 3.4), ("d", 3.3), ("h", 2.25)]
    # closing view = last price before kick-off
    assert db.execute("SELECT price FROM closing WHERE book='pinnacle' AND outcome='h'").fetchone()[0] == 1.90


def test_signal_and_clv(db):
    prices = oddsdb.price_table(db)
    s = live.signals(prices)
    first = s[(s.kind == "early") & (s.outcome == "h")].iloc[0]
    fair = remove_margin([2.00, 3.60, 3.90])
    assert first["book"] == "unibet_se"
    assert first["value"] == pytest.approx(2.25 * fair[0] - 1)
    c = live.clv_table(prices)
    row = c[(c.outcome == "h") & (c.book == "unibet_se")].iloc[0]
    close = remove_margin([1.90, 3.70, 4.20])
    assert row["clv"] == pytest.approx(2.25 * close[0] - 1)
    assert row["minutes_before"] == pytest.approx(50)


def test_reports_render(db):
    prices = oddsdb.price_table(db)
    txt = live.clv_report(prices, api_log="missing.csv")
    assert "Snitt-CLV" in txt
    assert "Value-spel" in live.value_report(prices)


def test_h2h_outcome_mapping():
    assert oddsdb.h2h_outcome("Draw", "A", "B") == "d"
    assert oddsdb.h2h_outcome("B", "A", "B") == "a"
    assert oddsdb.h2h_outcome("Over", "A", "B") is None


def test_value_report_lists_upcoming(db, monkeypatch):
    monkeypatch.setattr(live, "utcnow", lambda: datetime(2026, 11, 20, 15, tzinfo=timezone.utc))
    txt = live.value_report(oddsdb.price_table(db), bankroll=1000)
    assert "Arsenal – Chelsea" in txt and "unibet_se" in txt
    # latest snapshot: Unibet 2.00 vs fair 1.94 -> value 3 %, quarter Kelly 0.75 % of 1000 = 7 kr
    assert "7 kr" in txt


def test_signals_book_filter(db):
    prices = oddsdb.price_table(db)
    only_ss = live.signals(prices, threshold=-1, books=["svenskaspel_se"])
    assert set(only_ss["book"]) == {"svenskaspel_se"}
    assert set(live.signals(prices, threshold=-1)["book"]) <= {"unibet_se", "svenskaspel_se"}


def test_latest_fair_and_manual_value(db, monkeypatch):
    now = pd.Timestamp("2026-11-20T15:00:00Z")
    f = live.latest_fair(oddsdb.price_table(db), now=now)
    assert len(f) == 1
    # latest snapshot before kick-off is the closing one
    assert f.iloc[0]["fair_h"] == pytest.approx(remove_margin([1.90, 3.70, 4.20])[0])
    mv = live.manual_value(0.5, 2.2, 1000)
    assert mv["value"] == pytest.approx(0.1)
    assert mv["fair_odds"] == pytest.approx(2.0)
    assert mv["stake"] == 20  # quarter Kelly 2.1 % -> capped at 2 %
