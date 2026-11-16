# Backtest fas 1 – Poisson-modell mot marknaden

*Genereras av `python3 -m src.report`. Tabellerna räknas om varje gång. Texten är skriven för hand utifrån körningen 2026-11-16.*

## Kort svar

**Modellen slår inte marknaden.** Den förutsäger sämre än Pinnacles stängningsodds i alla ligor och marknader. Att spela på dess "value" har gett förlust mot vanliga bolag (B365, snittodds). ROI-intervallen ligger helt eller nästan helt under noll. Mot `Max`-odds ligger resultatet runt noll, men det beror på att `Max` är för optimistiskt (se nedan) och inte på modellen.

**Strategin utan modell är det enda som ser lovande ut.** Den räknar bort marginalen från Pinnacles odds och spelar när B365 ger högre odds än det rättvisa. Den har gett positiv CLV, alltså bättre odds än Pinnacles rättvisa stängningsodds, nästan alla år. Antalet spel är dock litet och oddsen höga, så ROI-intervallet täcker fortfarande noll. Det är inte bevisat, men det är en riktig signal värd att följa upp.

## Data och upplägg

- **Ligor:** Premier League (E0) och Championship (E1) 2019/20–2025/26 samt Allsvenskan (SWE) 2012–2026, totalt 10 132 matcher. Modellen kunde förutsäga 9 565 av dem.
- **Rullande backtest:** för varje matchdag tränas modellen bara på samma ligas matcher från de senaste 365 dagarna och strikt före dagen. Ett test (`tests/test_backtest.py`) bevisar att en prediktion inte påverkas av framtida resultat.
- **Säsongsstart:** matcher där ett lag har färre än 3 matcher i fönstret hoppas över, främst uppflyttade lag. Regression mot snittet görs med k = 5 "låtsasmatcher" på ligasnittsnivå. k valdes i förväg och har **inte** justerats för att få bättre resultat.
- **Marknaden:** Pinnacles odds med marginalen bortränkad proportionellt.
- **Odds vi spelar på:** i E0/E1 används de tidiga oddsen, som football-data samlar in några dagar före match och som modellen realistiskt kunde ha spelat på. I SWE finns bara stängningsodds.
- **Insats:** 1 enhet per spel, och högst ett spel per match och marknad (utfallet med högst value).
- **CLV:** oddset vi tog × Pinnacles marginalfria stängningssannolikhet − 1. Positivt betyder att vi fick bättre odds än det slutliga rättvisa priset.
- **95 % KI:** bootstrap med 5 000 omdragningar av spelen.

### Begränsningar i datan

1. **Pinnacle-odds saknas från mitten av 2025.** Pinnacle slutade leverera till football-data. För E0/E1 2025/26 saknas en stor del och för Allsvenskan 2026 allt. Matcher utan Pinnacle-odds räknas inte med i jämförelserna mot marknaden.
2. **`Max` är ett för optimistiskt riktmärke.** Det är det högsta oddset bland många bolag, varav flera inte är tillgängliga i Sverige, och några är gamla eller felaktiga. Bevis: att spela *alla* utfall på `Max`-oddset ger nästan nollresultat, trots att det inte innehåller någon kunskap alls.
3. **Allsvenskan har bara stängningsodds** och B365 bara från 2025. CLV i SWE mäts därför samtidigt som spelet läggs och betyder lite där.
4. **Det finns inga BTTS-odds.** BTTS beräknas av modellen men kan inte utvärderas mot odds.

## 1. Träffsäkerhet: modell mot marknad

Lägre är bättre. Samma matcher jämförs (de där Pinnacles stängningsodds finns).

**1X2**

| Liga | Matcher | Log loss modell | Log loss Pinnacle | Brier modell | Brier Pinnacle |
|---|---|---|---|---|---|
| E0 | 2338 | 0.9992 | 0.9610 | 0.5953 | 0.5698 |
| E1 | 3379 | 1.0663 | 1.0364 | 0.6440 | 0.6228 |
| SWE | 3161 | 1.0283 | 0.9806 | 0.6176 | 0.5841 |

**Över/under 2,5** (bara E0/E1, SWE saknar dessa odds)

| Liga | Matcher | Log loss modell | Log loss Pinnacle | Brier modell | Brier Pinnacle |
|---|---|---|---|---|---|
| E0 | 2327 | 0.6937 | 0.6752 | 0.4997 | 0.4823 |
| E1 | 3379 | 0.7023 | 0.6820 | 0.5074 | 0.4890 |

Skillnaden är stor. 0,03–0,05 i log loss är ungefär skillnaden mellan en marknad och en bra amatörmodell. Modellen är sämre i varje liga.

### Varför? Modellen är överkonfident

![Kalibrering](calibration.png)

Pinnacles linje ligger nästan på diagonalen, alltså inträffar det de säger med rätt frekvens. Modellens linje är flackare. När modellen säger 15–20 % inträffar det oftare än så, och när den säger 70 % inträffar det mer sällan. Den drar för långtgående slutsatser av för lite data:

- Hemma- och bortastyrkor räknas var för sig, så varje lag har bara cirka 19 hemmamatcher per säsong att räkna på.
- k = 5 låtsasmatcher är för lite regression mot snittet.
- Alla matcher det senaste året väger lika, inga justeringar görs för motståndets styrka och resultaten är brusiga, eftersom mål är sällsynta.

Följden är att modellen i snitt avviker 8,5 procentenheter från marknaden och ser "value" i nästan varje match. Det är brus, inte ett övertag.

## 2. Spel enligt modellen

"alla" = spela det bästa utfallet i varje match oavsett value. Det är ett riktmärke för vad oddset ger utan kunskap.

**1X2**

| Odds | Value-tröskel | Spel | Snittodds | ROI | 95 % KI för ROI | Vinst (enh.) | Max drawdown | Snitt-CLV |
|---|---|---|---|---|---|---|---|---|
| b365 | alla | 6474 | 3.86 | -5.4 % | -9.3 % … -1.3 % | -349.0 | 362.7 | -5.5 % |
| b365 | ≥ 0% | 5898 | 3.97 | -5.4 % | -9.6 % … -1.2 % | -320.6 | 336.0 | -5.5 % |
| b365 | ≥ 3% | 5324 | 4.08 | -6.1 % | -10.7 % … -1.5 % | -326.5 | 340.9 | -5.5 % |
| b365 | ≥ 5% | 4993 | 4.15 | -6.3 % | -10.9 % … -1.5 % | -316.2 | 329.8 | -5.6 % |
| b365 | ≥ 10% | 4155 | 4.36 | -5.2 % | -10.4 % … +0.2 % | -215.2 | 247.2 | -5.7 % |
| avg | alla | 9565 | 3.88 | -8.0 % | -11.1 % … -4.8 % | -764.1 | 781.5 | -6.2 % |
| avg | ≥ 0% | 8733 | 3.99 | -7.7 % | -10.9 % … -4.2 % | -670.0 | 696.7 | -6.3 % |
| avg | ≥ 3% | 7940 | 4.10 | -8.1 % | -11.7 % … -4.4 % | -640.2 | 662.2 | -6.3 % |
| avg | ≥ 5% | 7416 | 4.17 | -8.7 % | -12.5 % … -5.0 % | -645.9 | 663.9 | -6.4 % |
| avg | ≥ 10% | 6172 | 4.40 | -8.8 % | -12.9 % … -4.6 % | -545.7 | 560.2 | -6.6 % |
| max | alla | 9565 | 4.37 | -1.9 % | -5.4 % … +1.7 % | -182.4 | 236.6 | +0.2 % |
| max | ≥ 0% | 9491 | 4.38 | -2.1 % | -5.7 % … +1.6 % | -199.6 | 235.5 | +0.2 % |
| max | ≥ 3% | 9102 | 4.44 | -1.8 % | -5.5 % … +2.0 % | -163.7 | 242.6 | +0.3 % |
| max | ≥ 5% | 8695 | 4.50 | -1.8 % | -5.6 % … +1.9 % | -154.8 | 234.0 | +0.3 % |
| max | ≥ 10% | 7531 | 4.71 | -2.1 % | -5.9 % … +2.2 % | -154.9 | 191.0 | +0.4 % |

**Över/under 2,5**

| Odds | Value-tröskel | Spel | Snittodds | ROI | 95 % KI för ROI | Vinst (enh.) | Max drawdown | Snitt-CLV |
|---|---|---|---|---|---|---|---|---|
| b365 | alla | 6168 | 1.96 | -3.5 % | -5.9 % … -1.1 % | -214.1 | 227.9 | -4.9 % |
| b365 | ≥ 0% | 4975 | 1.98 | -3.0 % | -5.9 % … -0.3 % | -150.7 | 170.2 | -4.9 % |
| b365 | ≥ 3% | 4273 | 1.99 | -3.0 % | -6.0 % … -0.1 % | -127.2 | 141.8 | -4.9 % |
| b365 | ≥ 5% | 3839 | 2.00 | -3.3 % | -6.4 % … -0.1 % | -127.7 | 137.6 | -4.9 % |
| b365 | ≥ 10% | 2807 | 2.02 | -2.7 % | -6.5 % … +1.0 % | -76.4 | 89.1 | -5.0 % |
| avg | alla | 6170 | 1.96 | -3.7 % | -6.1 % … -1.2 % | -229.7 | 243.2 | -5.1 % |
| avg | ≥ 0% | 4920 | 1.97 | -3.1 % | -5.8 % … -0.3 % | -151.6 | 174.0 | -5.1 % |
| avg | ≥ 3% | 4205 | 1.98 | -3.4 % | -6.3 % … -0.3 % | -141.1 | 153.0 | -5.2 % |
| avg | ≥ 5% | 3757 | 1.99 | -3.0 % | -6.2 % … +0.2 % | -112.9 | 123.9 | -5.2 % |
| avg | ≥ 10% | 2743 | 2.02 | -4.2 % | -8.0 % … -0.4 % | -114.4 | 127.2 | -5.3 % |
| max | alla | 6170 | 2.04 | -0.1 % | -2.7 % … +2.5 % | -7.3 | 71.6 | -1.5 % |
| max | ≥ 0% | 5778 | 2.04 | -0.1 % | -2.8 % … +2.4 % | -6.8 | 70.0 | -1.5 % |
| max | ≥ 3% | 5080 | 2.05 | +0.3 % | -2.7 % … +3.1 % | +15.8 | 80.9 | -1.5 % |
| max | ≥ 5% | 4627 | 2.06 | -0.2 % | -3.1 % … +2.8 % | -7.3 | 73.9 | -1.5 % |
| max | ≥ 10% | 3516 | 2.08 | +0.3 % | -3.2 % … +3.7 % | +9.3 | 63.3 | -1.5 % |

![Ackumulerad vinst, modell](cumulative_model.png)

Tolkning:
- **B365 och snittodds:** konsekvent förlust på −3 till −9 %, med negativ CLV på cirka −5 %. Det motsvarar ungefär bolagens marginal, så modellen tillför ingenting.
- **Max:** runt noll, men lika bra som att spela "alla". Value-tröskeln förbättrar alltså inte resultatet. Det som syns är att `Max` i sig är för generöst, inte att modellen fungerar.
- **Högre tröskel hjälper inte.** Om modellen hade ett övertag skulle ROI stiga med tröskeln. Det gör den inte.

## 3. Strategi utan egen modell: Pinnacle som "sanning"

Räkna bort marginalen från Pinnacles odds (samma tidpunkt som spelet) och spela när ett annat bolag ger högre odds än det rättvisa.

**1X2**

| Odds | Value-tröskel | Spel | Snittodds | ROI | 95 % KI för ROI | Vinst (enh.) | Max drawdown | Snitt-CLV |
|---|---|---|---|---|---|---|---|---|
| b365 | alla | 6132 | 3.54 | -2.9 % | -7.0 % … +1.1 % | -177.8 | 222.7 | -2.9 % |
| b365 | ≥ 0% | 698 | 5.42 | +5.2 % | -10.6 % … +21.3 % | +36.3 | 52.6 | +1.2 % |
| b365 | ≥ 3% | 170 | 7.66 | +28.4 % | -11.4 % … +72.9 % | +48.2 | 20.9 | +4.3 % |
| b365 | ≥ 5% | 84 | 8.90 | +49.7 % | -13.1 % … +119.2 % | +41.8 | 10.2 | +4.7 % |
| b365 | ≥ 10% | 18 | 10.33 | +84.2 % | -76.1 % … +295.3 % | +15.1 | 5.0 | +7.5 % |
| max | alla | 9426 | 4.31 | -1.4 % | -4.8 % … +2.1 % | -127.8 | 280.6 | +2.0 % |
| max | ≥ 0% | 6996 | 4.70 | -2.2 % | -6.5 % … +2.1 % | -157.1 | 291.6 | +3.1 % |
| max | ≥ 3% | 2662 | 6.32 | -2.3 % | -10.6 % … +5.8 % | -61.6 | 176.4 | +6.7 % |
| max | ≥ 5% | 1451 | 7.72 | +0.1 % | -11.8 % … +12.8 % | +1.4 | 104.0 | +9.3 % |
| max | ≥ 10% | 450 | 11.56 | +1.0 % | -25.1 % … +30.0 % | +4.3 | 76.3 | +14.4 % |

**Över/under 2,5**

| Odds | Value-tröskel | Spel | Snittodds | ROI | 95 % KI för ROI | Vinst (enh.) | Max drawdown | Snitt-CLV |
|---|---|---|---|---|---|---|---|---|
| b365 | alla | 6045 | 1.91 | -3.7 % | -6.1 % … -1.3 % | -225.1 | 261.9 | -3.7 % |
| b365 | ≥ 0% | 58 | 2.56 | +3.4 % | -28.1 % … +36.7 % | +2.0 | 6.2 | +2.6 % |
| b365 | ≥ 3% | 15 | 3.45 | +29.7 % | -52.0 % … +113.0 % | +4.5 | 4.0 | +7.6 % |
| b365 | ≥ 5% | 11 | 3.57 | +31.4 % | -68.2 % … +133.6 % | +3.5 | 3.0 | +9.6 % |
| b365 | ≥ 10% | 7 | 3.70 | +2.9 % | -100.0 % … +128.6 % | +0.2 | 2.0 | +12.7 % |
| max | alla | 6047 | 2.02 | -1.5 % | -4.0 % … +1.1 % | -90.6 | 155.5 | -0.4 % |
| max | ≥ 0% | 1941 | 2.08 | +1.9 % | -2.8 % … +6.6 % | +36.4 | 44.1 | +1.6 % |
| max | ≥ 3% | 139 | 2.44 | +14.2 % | -5.5 % … +34.8 % | +19.7 | 13.7 | +6.8 % |
| max | ≥ 5% | 39 | 2.89 | +11.7 % | -32.3 % … +58.4 % | +4.6 | 5.8 | +12.7 % |
| max | ≥ 10% | 15 | 3.59 | +54.5 % | -29.9 % … +140.0 % | +8.2 | 3.0 | +22.0 % |

![Ackumulerad vinst, Pinnacle-strategin](cumulative_pinnacle.png)

Tolkning:
- **Pinnacle → B365 har positiv CLV.** Den är +1 % vid 0 % tröskel och +4 % vid 3 %, och positiv nästan varje år, med 2024 som undantag. CLV är ett mycket stabilare mått än ROI, för den visar om vi fått bra pris och inte om vi haft tur.
- **ROI är positiv men osäker.** Spelen är få (100–700) och har höga snittodds (5–8, mest oavgjort och bortaseger som skrällar). Därför är intervallen mycket breda och täcker noll.
- **Pinnacle → Max** ger fler spel men ingen tydlig vinst, vilket stämmer med att `Max` innehåller felaktiga och otillgängliga odds.
- **Verkliga hinder:** spelbolag som B365 begränsar ofta kunder som vinner på det här sättet. Svenska bolag (Svenska Spel, ATG, Unibet m.fl.) finns inte i datan, så vi vet inte om de beter sig som B365.

## Slutsats och förslag

1. **Bygg inte vidare mot live och webbsida med nuvarande modell.** Den har inget övertag.
2. **Fas 2 kan göra modellen bättre, men målet bör vara realistiskt.** Att slå Pinnacles stängningsodds med en målmodell är mycket svårt. Ett rimligt delmål är att komma *nära* marknaden i log loss. Förbättringarna i tur och ordning:
   - Maximum likelihood-skattning med gemensamma attack- och försvarsstyrkor plus en hemmafördel, i stället för separata hemma- och bortasnitt. Det halverar bruset.
   - Tidsviktning och Dixon-Coles.
   - Parametrarna (k, avklingning) väljs på tidiga säsonger och utvärderas på senare, aldrig på samma data.
3. **Det mest lovande spåret är Pinnacle-strategin** (eller en blandning: modellen som filter ovanpå marknadens pris). För att testa den mot *svenska* bolag behövs live-odds från ett API (fas 3) och att CLV loggas framåt. Det är där ett eventuellt övertag kan bevisas.
