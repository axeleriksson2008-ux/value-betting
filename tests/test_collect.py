from datetime import datetime, timedelta, timezone

from src import collect, config
from src.odds_api import OddsApi, load_snapshots, save_snapshot

NOW = datetime(2026, 11, 21, 14, 7, tzinfo=timezone.utc)
H = timedelta(hours=1)


def test_close_when_kickoff_within_window():
    assert collect.decide(NOW, [NOW + timedelta(minutes=53)], [], 400) == "close"


def test_no_double_close_within_50_minutes():
    prev = [NOW - timedelta(minutes=30)]
    assert collect.decide(NOW, [NOW + timedelta(minutes=40)], prev, 400) is None
    prev = [NOW - timedelta(minutes=60)]
    assert collect.decide(NOW, [NOW + timedelta(minutes=40)], prev, 400) == "close"


def test_early_once_per_gap():
    kick = [NOW + 24 * H]
    assert collect.decide(NOW, kick, [], 400) == "early"
    assert collect.decide(NOW, kick, [NOW - 5 * H], 400) is None
    assert collect.decide(NOW, kick, [NOW - 21 * H], 400) == "early"
    assert collect.decide(NOW, [NOW + 50 * H], [], 400) is None  # too far away


def test_budget_rules():
    assert collect.decide(NOW, [NOW + 24 * H], [], config.RESERVE_FOR_CLOSING - 1) is None
    assert collect.decide(NOW, [NOW + timedelta(minutes=30)], [], config.RESERVE_FOR_CLOSING - 1) == "close"
    assert collect.decide(NOW, [NOW + timedelta(minutes=30)], [], config.STOP_BELOW - 1) is None


def test_past_matches_ignored():
    assert collect.decide(NOW, [NOW - H], [], 400) is None


def test_snapshot_roundtrip_and_times(tmp_path):
    save_snapshot("soccer_epl", "early", [{"id": "x"}], NOW, root=tmp_path)
    save_snapshot("soccer_epl_extra", "close", [], NOW + H, root=tmp_path)  # other sport, similar prefix
    assert collect.snapshot_times("soccer_epl", root=tmp_path) == [NOW.replace(microsecond=0)]
    snaps = list(load_snapshots(tmp_path))
    assert snaps[0]["events"] == [{"id": "x"}] and snaps[0]["kind"] == "early"


class FakeResponse:
    def __init__(self, data, headers):
        self._data, self.headers, self.status_code = data, headers, 200

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params, timeout, headers):
        self.calls.append((url, params, headers))
        cost = "0" if url.endswith("/events") else "1"
        if url.endswith("/events"):
            data = [{"id": "e1", "commence_time": "2026-11-21T15:00:00Z"}] if "epl" in url else []
        else:
            data = [{"id": "e1", "bookmakers": []}]
        return FakeResponse(data, {"x-requests-last": cost, "x-requests-remaining": "450",
                                   "x-requests-used": "50"})


def test_run_fetches_only_where_needed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    sess = FakeSession()
    api = OddsApi(api_key="dummy", session=sess, log_path=tmp_path / "log.csv")
    done = collect.run(api, now=NOW)
    assert done == [("soccer_epl", "close")]
    odds_calls = [c for c in sess.calls if c[0].endswith("/odds")]
    assert len(odds_calls) == 1
    assert odds_calls[0][1]["bookmakers"].count(",") == len(config.BOOKMAKERS) - 1
    assert odds_calls[0][2]["x-api-key"] == "dummy"
    assert len(list((tmp_path / "snaps").rglob("*.json.gz"))) == 1  # written to the patched dir
    log = (tmp_path / "log.csv").read_text().splitlines()
    assert log[0].startswith("time_utc") and len(log) == 1 + len(config.LEAGUES) + 1


def test_events_are_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    sess = FakeSession()
    api = OddsApi(api_key="dummy", session=sess, log_path=tmp_path / "log.csv")
    collect.run(api, now=NOW, dry_run=True)
    collect.run(api, now=NOW + H, dry_run=True)        # within cache time: no new calls
    n_events = sum(c[0].endswith("/events") for c in sess.calls)
    assert n_events == len(config.LEAGUES)
    collect.run(api, now=NOW + 7 * H, dry_run=True)    # cache expired
    assert sum(c[0].endswith("/events") for c in sess.calls) == 2 * len(config.LEAGUES)
    assert collect.last_remaining(tmp_path / "log.csv") == 450
