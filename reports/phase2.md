# Fas 2 – Bättre modell och sökning bland alla odds, ligor och marknader

*Genereras av `python3 -m src.report_phase2`. Tabellerna räknas om från data. Texten är skriven utifrån körningen 2026-11-16.*

## Kort svar

1. **Modell v2 är klart bättre än v1, men fortfarande sämre än marknaden.** Avståndet till Pinnacle i log loss har krympt med cirka 40 %, och förbättringen håller på testdata som modellen aldrig sett. Ändå är v2 sämre än Pinnacle i **alla 38 ligor**.
2. **Att spela på modellens "value" förlorar pengar överallt:** i alla marknader, mot alla bolag och i alla ligor. Inte en enda modellstrategi klarade urvalet.
3. **Det enda som håller utanför urvalsperioden är strategin utan egen modell:** spela när ett bolag ger högre odds än Pinnacles rättvisa pris. Mot `Max`-odds i alla ligor gav det **+2,3 % ROI på 16 414 testspel (95 % KI +0,1 … +4,5 %)** och positiv CLV. Mot bolag med namn, som vi vet går att spela hos, är resultatet bara +1,3 % och osäkert.

Det betyder: **jag hittar inget bevis för att Poisson-modellen hittar felsatta odds.** Det som finns är små prisskillnader mellan bolag. De går eventuellt att utnyttja, men bara om man har tillgång till rätt bolag i rätt ögonblick.

## Data

- **38 ligor och 117 389 matcher:** 22 huvudligor (England 1–5, Skottland 1–4, Tyskland, Italien, Spanien och Frankrike 1–2, Nederländerna, Belgien, Portugal, Turkiet, Grekland) 2019/20–2025/26, och 16 extraligor (bland annat Sverige, Norge, Danmark, Finland, USA, Brasilien och Japan) 2012–2026.
- **Marknader:**
  - 1X2 med 14 bolag plus `Max`/`Avg`.
  - Över/under 2,5 och asiatiskt handikapp med Pinnacle, Bet365, Betfair-börsen och `Max`/`Avg`. Extraligorna har bara 1X2.
- **"Bästa namngivna bolag"** är det högsta oddset bland B365, bwin, Interwetten, William Hill, VC, Betfair, Betfair-börsen, 1xBet, Betfred, BetMGM, BetVictor, Coral och Ladbrokes. Det är mer realistiskt än `Max`, som innehåller okända bolag.
- **Betfair-börsen** räknas med 5 % provision på vinster.
- **Datafel:** odds som är mer än 25 % över snittoddset för samma utfall räknas som datafel och används inte. Exempel: helgen 29 november 2025 har `Max` för asiatiskt handikapp 22,0 i flera ligor där alla bolag har cirka 1,9. Den regeln infördes efter att felet upptäcktes på testdatan, och den gör resultaten *sämre*, inte bättre.
- **Pinnacle saknas i football-data från mitten av 2025.** Testperioden för strategier som kräver Pinnacle tar därför i praktiken slut då.

## Upplägg: hitta och testa på olika data

| Period | Används till |
|---|---|
| **Validering** juli 2020 – juni 2023 | välja modellparametrar och strategier |
| **Test** juli 2023 – nov 2026 | bara utvärdering, efter att valen låsts |

Varje prediktion använder bara matcher före matchdagen (rullande, med test mot look-ahead som i fas 1).

## 1. Modell v2

v2 skattar *en* attack- och *en* försvarsstyrka per lag samt en hemmafördel per liga, med maximum likelihood. Gamla matcher väger mindre (halveringstid), och varje lag dras mot snittet med κ låtsasmatcher. Dixon-Coles korrigerar sannolikheterna för 0–0, 1–0, 0–1 och 1–1.

**Parametrarna valdes på valideringsdata** (48 kombinationer × 3 Dixon-Coles-varianter, se `reports/tuning_validation.csv`):
- Halveringstid 365 dagar (testade 90/180/365/730).
- κ = 10 (testade 2/5/10/20).
- Inget avdrag för uppflyttade lag (testade 1,0/0,9/0,8).
- Dixon-Coles med ρ = −0,05.

De bästa värdena låg inte i kanten av rutnätet. Dixon-Coles gav en mycket liten förbättring, och avdraget för uppflyttade lag ingen alls.

### Log loss (lägre är bättre, samma matcher för alla tre)

| Period | Marknad | Matcher | Pinnacle stängning | Modell v1 | Modell v2 |
|---|---|---|---|---|---|
| Validering 2020–23 | 1X2 | 36687 | 0.9999 | 1.0386 | 1.0236 |
| Validering 2020–23 | Ö/U 2,5 | 22838 | 0.6744 | 0.6982 | 0.6857 |
| Test 2023–26 | 1X2 | 28956 | 1.0007 | 1.0376 | 1.0217 |
| Test 2023–26 | Ö/U 2,5 | 17681 | 0.6744 | 0.6993 | 0.6863 |

v2 slår v1 tydligt, även på testperioden. Marknaden är fortfarande klart bättre: 0,02 i log loss är en stor skillnad.

### Per liga, testperioden, 1X2

| Liga | Matcher | Pinnacle | Modell v2 | Skillnad (v2 − Pinnacle) |
|---|---|---|---|---|
| SC3 | 400 | 1.0667 | 1.0700 | +0.0034 |
| SWZ | 511 | 1.0261 | 1.0328 | +0.0068 |
| POL | 704 | 1.0421 | 1.0490 | +0.0069 |
| EC | 1256 | 1.0430 | 1.0514 | +0.0084 |
| SC0 | 508 | 0.9582 | 0.9698 | +0.0117 |
| E2 | 1226 | 1.0214 | 1.0331 | +0.0117 |
| D2 | 679 | 1.0402 | 1.0522 | +0.0120 |
| ARG | 1323 | 1.0566 | 1.0689 | +0.0123 |
| AUT | 446 | 1.0099 | 1.0223 | +0.0124 |
| RUS | 579 | 0.9792 | 0.9922 | +0.0131 |
| FIN | 421 | 0.9885 | 1.0025 | +0.0140 |
| E1 | 1349 | 1.0241 | 1.0393 | +0.0152 |
| IRL | 420 | 1.0046 | 1.0210 | +0.0164 |
| JPN | 886 | 1.0533 | 1.0698 | +0.0165 |
| MEX | 811 | 0.9759 | 0.9946 | +0.0186 |
| B1 | 711 | 0.9829 | 1.0019 | +0.0189 |
| F2 | 754 | 1.0526 | 1.0724 | +0.0198 |
| E3 | 1233 | 1.0494 | 1.0699 | +0.0205 |
| SWE | 599 | 0.9978 | 1.0187 | +0.0209 |
| F1 | 759 | 0.9789 | 1.0002 | +0.0213 |
| E0 | 961 | 0.9466 | 0.9681 | +0.0215 |
| SP2 | 1093 | 1.0406 | 1.0622 | +0.0215 |
| SP1 | 936 | 0.9488 | 0.9707 | +0.0219 |
| SC2 | 390 | 1.0076 | 1.0313 | +0.0237 |
| USA | 1286 | 1.0244 | 1.0484 | +0.0240 |
| ROU | 734 | 1.0334 | 1.0577 | +0.0243 |
| DNK | 457 | 0.9871 | 1.0117 | +0.0246 |
| G1 | 516 | 0.9292 | 0.9545 | +0.0253 |
| I1 | 946 | 0.9625 | 0.9886 | +0.0262 |
| BRA | 964 | 0.9917 | 1.0188 | +0.0271 |
| N1 | 745 | 0.9221 | 0.9498 | +0.0278 |
| NOR | 587 | 0.9681 | 0.9974 | +0.0292 |
| P1 | 751 | 0.9088 | 0.9386 | +0.0297 |
| SC1 | 403 | 1.0179 | 1.0482 | +0.0302 |
| I2 | 805 | 1.0511 | 1.0859 | +0.0347 |
| D1 | 746 | 0.9601 | 0.9952 | +0.0351 |
| T1 | 840 | 0.9297 | 0.9757 | +0.0460 |
| CHN | 588 | 0.8939 | 0.9488 | +0.0549 |

v2 är bättre än Pinnacle i 0 av 38 ligor. Närmast kommer den i lägre ligor (skotska fjärdedivisionen, Schweiz, Polen, National League), där marknaden har minst information. Längst ifrån är den i Kina, Turkiet och Bundesliga.

![Kalibrering](phase2_calibration.png)

v1 är överkonfident: dess linje är flackare än diagonalen. v2 ligger nära diagonalen och är snarare lite för försiktig med stora favoriter (när den säger 75–85 % vinner favoriten ännu oftare). Felet i v2 sitter alltså inte i en grov snedvridning utan i enskilda matcher.

## 2. Spel enligt modell v2 (tröskel 5 %, alla ligor)

| Marknad | Odds | Spel (test) | ROI test | 95 % KI | CLV test | ROI validering |
|---|---|---|---|---|---|---|
| 1x2 | avg | 21896 | -16.9 % | -19.0 % … -14.7 % | -10.0 % | -12.1 % |
| 1x2 | b365 | 16660 | -13.8 % | -16.4 % … -11.2 % | -8.5 % | -11.5 % |
| 1x2 | best | 23428 | -10.8 % | -13.1 % … -8.6 % | -5.1 % | -9.6 % |
| 1x2 | bfe | 16062 | -10.5 % | -13.2 % … -7.8 % | -5.5 % | – |
| 1x2 | bw | 10113 | -18.6 % | -21.7 % … -15.5 % | -11.6 % | -13.3 % |
| 1x2 | max | 29484 | -8.9 % | -10.9 % … -6.9 % | -3.3 % | -5.1 % |
| 1x2 | ps | 20686 | -12.9 % | -15.2 % … -10.7 % | -6.3 % | -8.3 % |
| ah | avg | 10381 | -3.1 % | -5.0 % … -1.3 % | -4.0 % | -6.3 % |
| ah | b365 | 12229 | -3.7 % | -5.3 % … -2.2 % | -3.3 % | -5.8 % |
| ah | best | 12557 | -3.4 % | -4.9 % … -1.8 % | -3.1 % | -5.8 % |
| ah | bfe | 6019 | -4.0 % | -6.2 % … -1.8 % | -4.0 % | – |
| ah | max | 13638 | -2.5 % | -4.0 % … -1.0 % | -1.8 % | -3.7 % |
| ah | ps | 10220 | -3.5 % | -5.2 % … -1.8 % | -2.8 % | -5.3 % |
| ou25 | avg | 7415 | -8.8 % | -11.2 % … -6.5 % | -6.2 % | -6.8 % |
| ou25 | b365 | 8527 | -6.9 % | -9.1 % … -4.8 % | -5.2 % | -6.3 % |
| ou25 | best | 9141 | -6.4 % | -8.5 % … -4.3 % | -4.7 % | -6.3 % |
| ou25 | bfe | 4792 | -6.4 % | -9.3 % … -3.5 % | -4.9 % | – |
| ou25 | max | 11451 | -3.9 % | -5.8 % … -2.0 % | -2.5 % | -2.6 % |
| ou25 | ps | 7803 | -7.1 % | -9.3 % … -4.8 % | -4.2 % | -5.0 % |

**Alla är negativa, och alla har negativ CLV.** Bättre log loss gav alltså inte bättre spel. Förklaringen är urvalet: modellen avviker i snitt 6,4 procentenheter från marknaden i enskilda matcher. När vi spelar där avvikelsen är störst plockar vi fram modellens största misstag, oftast skrällar med höga odds. Modellen tror att de spelen har i snitt 25 % value, men utfallet blir −7 %.

## 3. Strategisökning

Varje kombination av:
- **Sannolikhetskälla:** modell, Pinnacle eller kombination (Pinnacle säger value *och* modellen håller med).
- **Marknad:** 1X2, Ö/U 2,5 eller AH.
- **Bolag** (alla, plus "bästa namngivna").
- **Liga:** var för sig eller alla tillsammans.
- **Tröskel:** 0, 3, 5 eller 10 %.

Det ger **6973 strategier.**

**Urvalsregel (bestämd före testet):** på valideringsperioden minst 100 spel, undre gränsen i ROI:s 95 %-intervall > 0 och snitt-CLV > 0. **12 strategier klarade det:**

| Källa | Marknad | Odds | Liga | Tröskel | Spel val | ROI val | Spel test | ROI test | 95 % KI test | CLV test |
|---|---|---|---|---|---|---|---|---|---|---|
| combo | 1x2 | max | JPN | 0% | 481 | +14.8 % | 234 | +10.0 % | -11.7 % … +31.7 % | +3.6 % |
| pinnacle | 1x2 | max | ALL | 0% | 28435 | +1.7 % | 16414 | +2.3 % | +0.1 % … +4.5 % | +2.0 % |
| pinnacle | 1x2 | max | ALL | 3% | 8664 | +3.9 % | 4434 | +4.1 % | -0.8 % … +9.0 % | +5.1 % |
| pinnacle | 1x2 | max | ARG | 3% | 563 | +17.5 % | 445 | +9.4 % | -5.5 % … +24.3 % | +6.4 % |
| pinnacle | 1x2 | max | ARG | 5% | 253 | +24.4 % | 233 | +7.5 % | -14.7 % … +29.8 % | +8.6 % |
| pinnacle | 1x2 | max | SP2 | 3% | 310 | +20.2 % | 122 | -3.7 % | -29.5 % … +22.0 % | +2.8 % |
| pinnacle | 1x2 | max | SWE | 3% | 226 | +23.0 % | 133 | +24.7 % | -4.0 % … +53.4 % | +6.1 % |
| pinnacle | 1x2 | max | T1 | 0% | 863 | +12.2 % | 561 | +2.7 % | -8.3 % … +13.6 % | +1.2 % |
| pinnacle | ah | max | ALL | 3% | 944 | +9.1 % | 292 | +7.2 % | -3.4 % … +17.7 % | +2.4 % |
| pinnacle | ou25 | max | ALL | 3% | 839 | +10.8 % | 219 | +4.4 % | -10.0 % … +18.8 % | +3.8 % |
| pinnacle | ou25 | max | ALL | 5% | 167 | +21.7 % | 73 | -2.8 % | -27.5 % … +21.8 % | +8.1 % |
| pinnacle | ou25 | max | P1 | 0% | 374 | +9.7 % | 130 | +7.0 % | -8.8 % … +22.9 % | +1.1 % |

- **Inte en enda modellstrategi valdes.** 11 av 12 är "Pinnacle → Max", och en är kombinationen i Japan.
- **10 av 12 hade positiv ROI på testperioden,** och alla hade positiv CLV där. Men de enskilda testintervallen är breda.
- **Alla valda strategier tillsammans på testperioden:** 17081 unika spel, ROI +2.5 % (95 % KI +0.4 % … +4.6 %), vinst +424.1 enheter, max drawdown 89.4 enheter, snitt-CLV +2.1 %.
- **Tänk på antalet försök:** av ~7 000 strategier skulle ett antal klara regeln av ren tur. Att nästan alla valda är samma typ (Pinnacle mot Max), och att de håller på testet, talar för en verklig effekt och inte för slump.

### Hur realistiskt är det? Max mot bolag med namn

| Strategi (1X2, alla ligor) | Tröskel | Spel val | ROI val | Spel test | ROI test | 95 % KI test | CLV test |
|---|---|---|---|---|---|---|---|
| Pinnacle → Max (alla bolag i football-data) | 0% | 28435 | +1.7 % | 16414 | +2.3 % | +0.1 % … +4.5 % | +2.0 % |
| Pinnacle → Max (alla bolag i football-data) | 3% | 8664 | +3.9 % | 4434 | +4.1 % | -0.8 % … +9.0 % | +5.1 % |
| Pinnacle → bästa namngivna bolag | 0% | 6551 | +1.7 % | 7207 | +1.3 % | -2.3 % … +4.8 % | +1.3 % |
| Pinnacle → bästa namngivna bolag | 3% | 1435 | +0.9 % | 1569 | +2.8 % | -6.4 % … +12.0 % | +4.3 % |
| Pinnacle → Bet365 | 0% | 2806 | +1.4 % | 1995 | +8.4 % | +1.0 % … +15.7 % | +0.9 % |
| Pinnacle → Bet365 | 3% | 607 | +10.4 % | 502 | +3.8 % | -13.1 % … +20.6 % | +3.7 % |
| Pinnacle → bwin | 0% | 1438 | +6.5 % | 971 | -3.6 % | -10.3 % … +3.2 % | -0.1 % |
| Pinnacle → bwin | 3% | 127 | +14.9 % | 70 | -4.7 % | -39.7 % … +30.3 % | +1.2 % |
| Pinnacle → Betfair-börsen (−5 % provision) | 0% | – | – | 2362 | -2.1 % | -8.7 % … +4.5 % | +1.4 % |
| Pinnacle → Betfair-börsen (−5 % provision) | 3% | – | – | 644 | +3.8 % | -10.9 % … +18.4 % | +5.7 % |

`Max` är det högsta oddset bland alla bolag som football-data samlar in, och vi vet inte vilka bolag det är. Där finns både seriösa och okända bolag samt odds som bara fanns en kort stund. Med bara bolag vi kan namnge krymper effekten till +1–3 %, och intervallen täcker noll. Mot Bet365 med tröskel 0 % gav testet +8,4 %, men det är få spel och valideringen gav bara +1,4 %.

![Ackumulerad vinst](phase2_cumulative.png)

## 4. Slutsats

1. **Modellen hittar inte felsatta odds.** v2 är en bra modell, men inte i närheten av marknaden. Alla försök att spela på dess value förlorar.
2. **Prisskillnader mellan bolag finns:** när ett bolag ger mer än Pinnacles rättvisa pris har det i snitt lönat sig, cirka +2 % ROI och positiv CLV, både i validering och test. Det är ingen "statistik om vad som borde ske" utan att utnyttja att vissa bolag är långsammare eller sämre än Pinnacle.
3. **Det stora frågetecknet är tillgängligheten.** Ger *svenska* bolag sådana odds, i tid, och utan att begränsa kontot? Det går inte att svara på med football-data, eftersom svenska bolag (Svenska Spel, ATG, Unibet, LeoVegas m.fl.) inte finns där.

## 5. Förslag på nästa steg

- **Fas 3, i bantad form:** hämta odds för Pinnacle (eller Betfair-börsen) och de svenska bolag du kan spela hos från ett odds-API. Logga dem flera gånger per dag tillsammans med stängningsoddsen, utan att spela. Efter några månader vet vi:
  - om svenska bolag alls ligger över Pinnacles rättvisa pris,
  - hur ofta det händer,
  - om CLV:n är positiv.
- **Modellen kan få en mindre roll:** som kontroll (varna när ett "value-spel" kan bero på skada eller avstängning som Pinnacle redan räknat med), eller i ligor som Pinnacle inte täcker. Inte som huvudmotor.
- **Mer modellarbete** (xG, laguppställningar) skulle kunna minska avståndet till marknaden. Erfarenheten är dock att det kräver mycket bättre data än resultat och odds. Jag rekommenderar det inte nu.
