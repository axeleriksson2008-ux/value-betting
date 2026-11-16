## Kort svar

- **Modellen är bättre än ligasnittet för alla fem statistiktyper**, på testdata den inte har sett (2023–26, ~23 000 matcher). Förbättringen är säker (intervallen ligger över noll), men olika stor:
  - **Fouls** och **skott**: tydligast. Lagens stil (pressande, fysiska lag) syns starkt.
  - **Kort** och **skott på mål**: måttlig.
  - **Hörnor**: nästan inte bättre än ligasnittet. Hörnor är till stor del slump och beror på matchbilden.
- **Kalibreringen är bra:** när modellen säger 60 % "över" blir det över i ungefär 60 % av matcherna. Vid ytterligheterna (över 80 %) är modellen något för säker på skott och hörnor.
- **Det här bevisar inte att du slår spelbolagen.** Det finns inga historiska odds för statistikspel, så modellen har bara jämförts med ett enkelt ligasnitt. Bolagen har mer information: domare, laguppställningar och matchens betydelse. Använd den som en *andra åsikt* och logga dina spel, så vet vi efter några hundra spel om den ger övertag.
- **Tacklingar** finns inte i datan och ingår därför inte.
- **Kort** räknas som gula + röda. Bolagen räknar olika (t.ex. om ett andra gult kort räknas som två kort), så kontrollera reglerna hos ditt bolag.

### Valda parametrar (på valideringsdata 2020–23)

| Statistik | Halveringstid | κ (regression mot snittet) |
|---|---|---|
| Skott | 180 dagar | 5 |
| Skott på mål | 365 dagar | 20 |
| Fouls | 180 dagar | 5 |
| Hörnor | 730 dagar | 50 |
| Kort | 730 dagar | 50 |

Hög κ och lång halveringstid för hörnor och kort betyder att lagens "egen" nivå är svag och att ligasnittet väger tungt. Det stämmer med att de är mest slump.

