import pandas as pd

from src.team_names import best_match, load_mapping, to_football_data, update_mapping

FD = ["Man United", "Man City", "Nott'm Forest", "Wolves", "Brighton", "Tottenham", "Newcastle",
      "Sheffield United", "AIK", "Hammarby", "Djurgarden", "Malmo FF", "IFK Goteborg"]


def test_best_match_common_cases():
    assert best_match("Manchester United", FD) == "Man United"
    assert best_match("Manchester City", FD) == "Man City"
    assert best_match("Nottingham Forest", FD) == "Nott'm Forest"
    assert best_match("Wolverhampton Wanderers", FD) == "Wolves"
    assert best_match("Brighton and Hove Albion", FD) == "Brighton"
    assert best_match("Tottenham Hotspur", FD) == "Tottenham"
    assert best_match("Djurgårdens IF", FD) == "Djurgarden"
    assert best_match("Malmö FF", FD) == "Malmo FF"
    assert best_match("AIK", FD) == "AIK"
    assert best_match("Real Madrid", FD) is None


def test_update_keeps_manual_rows(tmp_path):
    p = tmp_path / "map.csv"
    pd.DataFrame([{"sport": "soccer_epl", "odds_api_name": "Spurs", "football_data_name": "Tottenham",
                   "status": "manual"}]).to_csv(p, index=False)
    m = update_mapping({"soccer_epl": {"Spurs", "Manchester United", "Atlantis FC"}},
                       {"soccer_epl": set(FD)}, p)
    m = load_mapping(p)
    assert to_football_data("soccer_epl", "Spurs", m) == "Tottenham"
    assert to_football_data("soccer_epl", "Manchester United", m) == "Man United"
    assert to_football_data("soccer_epl", "Atlantis FC", m) is None
    st = dict(zip(m.odds_api_name, m.status))
    assert st == {"Spurs": "manual", "Manchester United": "auto", "Atlantis FC": "missing"}
