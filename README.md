# Value-betting fotboll – analysverktyg

Fas 1: Poisson-modell och rullande backtest, resultat i `reports/backtest.md`.
Fas 2: modell v2, 38 ligor, alla bolag och marknader, resultat i `reports/phase2.md`.

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

Verktyget är för analys. Satsa bara små andelar av en kassa du har råd att förlora.
