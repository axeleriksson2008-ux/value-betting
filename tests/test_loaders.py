import math

from src.loaders import load_all, read_extra_league, read_main_league

MAIN_CSV = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A,PSH,PSD,PSA,"
    "MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,P>2.5,P<2.5,PSCH,PSCD,PSCA,MaxCH,MaxCD,MaxCA,PC>2.5,PC<2.5\n"
    "E0,16/08/2024,20:00,Man United,Fulham,1,0,H,1.6,4.2,5.25,1.62,4.3,5.5,"
    "1.66,4.4,5.6,1.6,4.2,5.3,1.9,1.95,1.65,4.1,5.4,1.7,4.3,5.6,1.92,1.96\n"
    ",,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"  # trailing empty row, should be dropped
)

EXTRA_CSV = (
    "﻿Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA,"
    "MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA\n"
    "Sweden,Allsvenskan,2012,31/03/2012,15:00,Elfsborg,Djurgarden,2,1,H,"
    "1.71,3.98,5.44,1.73,3.98,5.5,1.66,3.68,5\n"
)


def test_main_league_normalised(tmp_path):
    p = tmp_path / "E0_2425.csv"
    p.write_text(MAIN_CSV)
    df = read_main_league(p, "E0", 2024)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["home"] == "Man United" and row["away"] == "Fulham"
    assert (row["hg"], row["ag"]) == (1, 0)
    assert row["date"].strftime("%Y-%m-%d") == "2024-08-16"
    assert row["ps_early_h"] == 1.62
    assert row["ps_close_a"] == 5.4
    assert row["max_close_d"] == 4.3
    assert row["ps_early_o25"] == 1.9
    assert row["ps_close_u25"] == 1.96
    assert row["b365_early_h"] == 1.6
    assert math.isnan(row["b365_close_h"])  # column missing in source


def test_extra_league_normalised(tmp_path):
    p = tmp_path / "SWE.csv"
    p.write_text(EXTRA_CSV, encoding="utf-8")
    df = read_extra_league(p, "SWE")
    row = df.iloc[0]
    assert row["season"] == 2012
    assert row["home"] == "Elfsborg"
    assert row["ps_close_h"] == 1.71
    assert row["avg_close_a"] == 5.0
    assert math.isnan(row["ps_early_h"])  # extra leagues have no early odds


def test_load_all_same_columns(tmp_path):
    (tmp_path / "E0_2425.csv").write_text(MAIN_CSV)
    (tmp_path / "SWE.csv").write_text(EXTRA_CSV, encoding="utf-8")
    df = load_all(tmp_path)
    assert set(df["league"]) == {"E0", "SWE"}
    assert df.loc[df.league == "E0", "season"].iloc[0] == 2024
    assert df["date"].is_monotonic_increasing
