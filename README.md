# Value-betting fotboll – analysverktyg

Fas 1: historisk data, Poisson-modell och rullande backtest. Resultat: `reports/backtest.md`.

## Kör

```bash
pip install -r requirements.txt
python3 -m src.loaders    # data/raw/*.csv -> data/processed/matches.csv
python3 -m src.backtest   # rullande prediktioner -> data/processed/predictions.csv (~45 s)
python3 -m src.report     # tabeller och grafer -> reports/backtest.md
python3 -m pytest         # tester
```

CSV-filerna hämtas från football-data.co.uk till `data/raw/`
(`SWE.csv` från `/new/`, `E0_2425.csv` osv. från `/mmz4281/<säsong>/E0.csv`).

## Kod

- `src/loaders.py` – normaliserar huvudligor och extraligor till samma tabell
- `src/model.py` – Poisson-modell, marginalborttagning, value, kvarts-Kelly
- `src/backtest.py` – rullande prediktion utan look-ahead
- `src/evaluate.py` – log loss, Brier, kalibrering, spelsimulering, CLV, bootstrap
- `src/report.py` – bygger rapporten från `reports/backtest_template.md`

Verktyget är för analys. Satsa bara små andelar av en kassa du har råd att förlora.
