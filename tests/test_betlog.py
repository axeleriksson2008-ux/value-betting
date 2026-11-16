import numpy as np
import pandas as pd
import pytest

from src import betlog


def _two_bets():
    b = betlog.load_bets("does-not-exist.csv")
    b = betlog.add_bet(b, event_id="e1", sport="soccer_epl", match="A – B",
                       commence_time="2026-11-21T15:00:00Z", outcome="h", book="unibet_se",
                       odds=2.25, stake=20, fair_odds=2.10, placed_at="2026-11-20T10:00:00Z")
    b = betlog.add_bet(b, event_id="e2", sport="soccer_epl", match="C – D",
                       commence_time="2026-11-22T15:00:00Z", outcome="a", book="betsson",
                       odds=4.0, stake=10, placed_at="2026-11-20T11:00:00Z")
    return b


def test_add_and_ids():
    b = _two_bets()
    assert b["bet_id"].tolist() == [1, 2]
    assert (b["status"] == "open").all()
    with pytest.raises(ValueError):
        betlog.add_bet(b, event_id="x", sport="s", match="m", commence_time="2026-01-01",
                       outcome="h", book="b", odds=1.0, stake=5)
    with pytest.raises(ValueError):
        betlog.add_bet(b, event_id="x", sport="s", match="m", commence_time="2026-01-01",
                       outcome="", book="b", odds=2.0, stake=5)
    b = betlog.add_bet(b, event_id="x", sport="E0", match="m", commence_time="2026-01-01T15:00Z",
                       outcome="Hörnor totalt över 9.5", book="bet365", odds=1.9, stake=5)
    assert betlog.evaluate(b)["clv"].isna().all()  # no closing odds for statistics bets


def test_profit_roi_and_clv():
    b = _two_bets()
    b = betlog.set_status(b, 1, "won")
    b = betlog.set_status(b, 2, "lost")
    closing = pd.DataFrame({"event_id": ["e1"], "close_h": [0.5], "close_d": [0.3], "close_a": [0.2]})
    ev = betlog.evaluate(b, closing)
    assert ev["profit"].tolist() == pytest.approx([25.0, -10.0])
    assert ev.loc[0, "clv"] == pytest.approx(2.25 * 0.5 - 1)
    assert np.isnan(ev.loc[1, "clv"])  # no closing odds for e2
    s = betlog.summary(ev, 1000)
    assert s["profit"] == pytest.approx(15.0)
    assert s["roi"] == pytest.approx(15 / 30)
    assert s["bankroll"] == pytest.approx(1015)
    curve = betlog.bankroll_curve(ev, 1000)
    assert curve["bankroll"].tolist() == pytest.approx([1025, 1015])


def test_open_and_void_not_in_profit():
    b = betlog.set_status(_two_bets(), 1, "void")
    s = betlog.summary(betlog.evaluate(b), 500)
    assert s["settled"] == 1 and s["open"] == 1 and s["profit"] == 0
    with pytest.raises(ValueError):
        betlog.set_status(b, 1, "maybe")


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "bets.csv"
    b = betlog.set_status(_two_bets(), 2, "won")
    betlog.save_bets(b, p)
    back = betlog.load_bets(p)
    assert back["status"].tolist() == ["open", "won"]
    assert back["odds"].tolist() == [2.25, 4.0]
    assert str(back["commence_time"].dt.tz) == "UTC"
