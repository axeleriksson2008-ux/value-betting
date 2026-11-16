from datetime import date

from src.update_stat_ratings import season_codes


def test_season_codes():
    assert season_codes(date(2026, 11, 16)) == ["2425", "2526", "2627"]
    assert season_codes(date(2027, 3, 1)) == ["2425", "2526", "2627"]   # still 2026/27
    assert season_codes(date(2027, 7, 1)) == ["2526", "2627", "2728"]   # new season
    assert season_codes(date(2099, 8, 1), n=1) == ["9900"]
