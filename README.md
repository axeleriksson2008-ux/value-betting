# Value-betting fotboll – analysverktyg

Fas 1: Poisson-modell och rullande backtest, resultat i `reports/backtest.md`.
Fas 2: modell v2, 38 ligor, alla bolag och marknader, resultat i `reports/phase2.md`.
Fas 3: live-odds (The Odds API) hämtas varje timme av GitHub Actions, rapporter i `reports/live_value.md` och `reports/live_clv.md`.
Fas 4: webbsida (Streamlit) med value-spel, spellogg och statistik.

## Webbsidan

```bash
pip install -r requirements.txt
streamlit run src/app.py        # öppna http://localhost:8501
python -m src.demo              # (valfritt) påhittad demodata, välj "Demo" i sidomenyn
```

Spelloggen sparas i `data/bets.csv`. Kör `git pull` först för att få de senaste oddsen från GitHub Actions.

## Live-odds (fas 3)

1. Skaffa en gratis nyckel på the-odds-api.com.
2. Lägg den som GitHub-secret `ODDS_API_KEY` (Settings → Secrets and variables → Actions).
   Lokalt: skriv `ODDS_API_KEY=...` i `.env` (som aldrig committas).
3. Inställningar (ligor, bolag, budget) finns i `src/config.py`.
4. Lagnamn mappas i `config/team_names.csv` (`python -m src.team_names`), rätta rader med status auto/missing för hand.

## Kör

```bash
pip install -r requirements.txt
python3 -m src.loaders    # data/raw/*.csv -> data/processed/matches.csv
python3 -m src.backtest   # rullande prediktioner -> data/processed/predictions.csv (~45 s)
python3 -m src.report     # tabeller och grafer -> reports/backtest.md
python3 -m pytest         # tester

# Fas 2
python3 -m src.loaders          # alla ligor -> data/processed/matches.parquet
python3 -m src.tune             # parameterval på valideringsperioden (~10 min)
python3 -c "from src.walkforward import *; import pandas as pd; m=pd.read_parquet('data/processed/matches.parquet'); predict_all(m, Params(half_life=365, kappa=10), VAL_START).to_parquet('data/processed/v2_predictions.parquet')"
python3 -m src.search           # alla strategier, urval på validering
python3 -m src.report_phase2    # -> reports/phase2.md
```

OBS: fas 1-skripten (`src.backtest`, `src.report`) läser den gamla `matches.csv` och behöver köras med fas 1-datan.

CSV-filerna hämtas från football-data.co.uk till `data/raw/`
(`SWE.csv` från `/new/`, `E0_2425.csv` osv. från `/mmz4281/<säsong>/E0.csv`).

## Kod

- `src/loaders.py` – normaliserar huvudligor och extraligor till samma tabell
- `src/model.py` – Poisson-modell, marginalborttagning, value, kvarts-Kelly
- `src/backtest.py` – rullande prediktion utan look-ahead
- `src/evaluate.py` – log loss, Brier, kalibrering, spelsimulering, CLV, bootstrap
- `src/report.py` – bygger rapporten från `reports/backtest_template.md`
- `src/ratings.py` – modell v2 (viktad Poisson-ML, Dixon-Coles)
- `src/markets.py` – asiatiskt handikapp
- `src/walkforward.py` – rullande prediktion för v2, perioder för validering/test
- `src/tune.py`, `src/search.py`, `src/strategies.py` – parameterval och strategisökning
- `src/report_phase2.py` – bygger `reports/phase2.md`
- `src/config.py` – ligor, bolag, credit-budget, insatsregler
- `src/odds_api.py`, `src/collect.py` – API-klient och timvis hämtning
- `src/oddsdb.py` – SQLite-databas byggd från sparade odds
- `src/live.py` – value-lista och CLV-uppföljning
- `src/team_names.py` – lagnamnsmappning
- `src/betlog.py`, `src/app.py`, `src/demo.py` – spellogg, webbsida, demodata

Verktyget är för analys. Satsa bara små andelar av en kassa du har råd att förlora.
