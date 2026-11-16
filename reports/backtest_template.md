# Backtest fas 1 – Poisson-modell mot marknaden

*Genereras av `python3 -m src.report`. Tabellerna räknas om varje gång. Texten är skriven för hand utifrån körningen 2026-11-16.*

## Kort svar

**Den egna Poisson-modellen slår inte marknaden.** Den förutsäger sämre än Pinnacles stängningsodds i alla ligor och marknader. Att spela på dess "value" har gett förlust mot vanliga bolag (B365 −5 till −6 %, snittodds cirka −8 %), och ROI-intervallen ligger under noll. Mot `Max`-odds ligger resultatet runt noll, men det gör också att spela *alla* matcher på `Max`. Modellen tillför alltså ingenting.

**Strategin utan modell är intressant men inte bevisad.** Den räknar bort marginalen från Pinnacles odds och spelar när ett annat bolag ger mer:
- **Pinnacle → Max, value ≥ 3 %:** 1 867 spel, ROI +8 % (95 % KI +0,6 … +16,5 %) och positiv CLV i 91 % av spelen. Det är enda intervallet som ligger över noll, men två tredjedelar av spelen kommer från Allsvenskan, och `Max` innehåller odds vi kanske inte hade kunnat spela på.
- **Pinnacle → B365:** positiv CLV, men för få spel för att säga något om ROI.

Vi har testat ett 40-tal kombinationer, så att *ett* intervall hamnar över noll kan vara slump. Det här ska följas upp framåt med riktiga svenska odds (fas 3), inte byggas på direkt.

## Data och upplägg

- **Ligor:** Premier League (E0) och Championship (E1) 2019/20–2025/26 samt Allsvenskan (SWE) 2012–2026, totalt 10 132 matcher. Modellen kunde förutsäga 9 565 av dem.
- **Rullande backtest:** för varje matchdag tränas modellen bara på samma ligas matcher från de senaste 365 dagarna och strikt före dagen. Ett test (`tests/test_backtest.py`) bevisar att en prediktion inte påverkas av framtida resultat.
- **Säsongsstart:** matcher där ett lag har färre än 3 matcher i fönstret hoppas över, främst uppflyttade lag. Regression mot snittet görs med k = 5 "låtsasmatcher" på ligasnittsnivå. k valdes i förväg och har **inte** justerats för att få bättre resultat.
- **Marknaden:** Pinnacles odds med marginalen bortränkad enligt *potensmetoden* (p = q^k). Den ger skrällar lite lägre sannolikhet än proportionell normalisering och passar utfallen bättre (lägre log loss). Se avsnitt 4 om varför detta spelar roll.
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

{{ACC_1X2}}

**Över/under 2,5** (bara E0/E1, SWE saknar dessa odds)

{{ACC_OU}}

Skillnaden är stor. 0,03–0,05 i log loss är ungefär skillnaden mellan en marknad och en bra amatörmodell. Modellen är sämre i varje liga.

### Varför? Modellen är överkonfident

![Kalibrering](calibration.png)

Pinnacles linje ligger nästan på diagonalen, alltså inträffar det de säger med rätt frekvens. Modellens linje är flackare. När modellen säger 15–20 % inträffar det oftare än så, och när den säger 70 % inträffar det mer sällan. Den drar för långtgående slutsatser av för lite data:

- Hemma- och bortastyrkor räknas var för sig, så varje lag har bara cirka 19 hemmamatcher per säsong att räkna på.
- k = 5 låtsasmatcher är för lite regression mot snittet.
- Alla matcher det senaste året väger lika, inga justeringar görs för motståndets styrka och resultaten är brusiga, eftersom mål är sällsynta.

Följden är att modellens sannolikhet för hemmaseger i snitt avviker 8,5 procentenheter från marknadens och ser "value" i nästan varje match. Det är brus, inte ett övertag.

## 2. Spel enligt modellen

"alla" = spela det bästa utfallet i varje match oavsett value. Det är ett riktmärke för vad oddset ger utan kunskap.

**1X2**

{{MODEL_1X2}}

**Över/under 2,5**

{{MODEL_OU}}

![Ackumulerad vinst, modell](cumulative_model.png)

Tolkning:
- **B365 och snittodds:** konsekvent förlust på −3 till −9 %, med negativ CLV på cirka −5 %. Det motsvarar ungefär bolagens marginal, så modellen tillför ingenting.
- **Max:** runt noll, men lika bra som att spela "alla". Value-tröskeln förbättrar alltså inte resultatet. Det som syns är att `Max` i sig är för generöst, inte att modellen fungerar.
- **Högre tröskel hjälper inte.** Om modellen hade ett övertag skulle ROI stiga med tröskeln. Det gör den inte.

## 3. Strategi utan egen modell: Pinnacle som "sanning"

Räkna bort marginalen från Pinnacles odds (samma tidpunkt som spelet) och spela när ett annat bolag ger högre odds än det rättvisa. I E0/E1 jämförs tidiga odds med tidiga odds och i SWE stängning med stängning.

**1X2**

{{PIN_1X2}}

**Över/under 2,5**

{{PIN_OU}}

![Ackumulerad vinst, Pinnacle-strategin](cumulative_pinnacle.png)

**Per liga, Pinnacle → Max, value ≥ 3 %**

{{PIN_LEAGUE_MAX}}

**Per liga, Pinnacle → B365, value ≥ 0 %**

{{PIN_LEAGUE_B365}}

Tolkning:
- **CLV är positiv i alla ligor och alla år** för Pinnacle → Max. Vi får alltså systematiskt bättre odds än Pinnacles rättvisa pris, och det mätvärdet är mycket stabilare än ROI.
- **ROI följer inte CLV överallt.** Allsvenskan ger klart plus, Premier League lite plus och Championship minus, trots positiv CLV även där. Per år svänger ROI från −20 % till +50 %. Det visar hur stor variansen är.
- **`Max` är problemet.** Det högsta oddset bland många bolag innehåller ibland felaktiga eller gamla odds och bolag som inte tar svenska kunder. I Allsvenskan jämförs dessutom Max-stängning med Pinnacle-stängning i samma ögonblick. Vi vet inte om de oddsen faktiskt gick att spela på.
- **B365** ger positiv CLV, men oddsen ligger sällan över Pinnacles rättvisa pris, så spelen blir för få för en slutsats.
- **Verkliga hinder:** bolag begränsar ofta kunder som systematiskt tar bättre odds än marknaden. Svenska bolag (Svenska Spel, ATG, Unibet m.fl.) finns inte i datan.

## 4. Känslighet: hur marginalen räknas bort

Bolagen lägger mer marginal på skrällar. Proportionell borttagning ger därför skrällar för hög rättvis sannolikhet, och då ser höga odds ut att ha "value" som inte finns. Potensmetoden passar Pinnacles utfall bättre (log loss 0,99738 mot 0,99754 för 1X2) och används därför som standard. Valet gjordes på log loss, men jag upptäckte problemet *efter* att ha sett resultaten, och det ska du känna till.

{{MARGIN_CMP}}

Med proportionell metod blir snittoddsen högre och ROI sämre för Max trots högre CLV. Det är tecknet på att den metoden överskattar skrällar.

## Slutsats och förslag

1. **Bygg inte vidare mot live och webbsida med nuvarande Poisson-modell.** Den har inget övertag och är för överkonfident.
2. **Fas 2 kan förbättra modellen, men sikta realistiskt.** Att slå Pinnacles stängningsodds med en ren målmodell är mycket svårt. Ett rimligt mål är att komma *nära* marknaden i log loss, så att modellen kan användas som ett filter ovanpå marknadens pris. Förbättringarna i tur och ordning:
   - Maximum likelihood-skattning med gemensamma attack- och försvarsstyrkor plus en hemmafördel, i stället för separata hemma- och bortasnitt. Det minskar bruset kraftigt.
   - Tidsviktning och Dixon-Coles.
   - Parametrarna (k, avklingning) väljs på tidiga säsonger och utvärderas på senare, aldrig på samma data.
3. **Det mest lovande spåret är marknadsstrategin** (Pinnacle eller en marginalfri konsensus som "sanning", spel när ett svenskt bolag ger mer). Det kan bara bevisas med riktiga, spelbara svenska odds. Fas 3 bör därför logga odds och stängningsodds från svenska bolag och mäta CLV framåt, i några månader, innan några pengar satsas.
4. **Notera:** Pinnacle-odds saknas i football-data från 2025. Ett live-API måste därför ha Pinnacle (eller ett annat skarpt bolag och börser som Betfair) för att strategin ska fungera.
