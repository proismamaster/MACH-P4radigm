# Stato del progetto (leggilo per primo)

> Milano Agentic City Hackathon, squadra p4radigm: 5 agenti di una ASST simulata. Gara dal 20/11 21:00 al 21/11 16:00.

## Stato attuale (21/11 ore 08:30, freeze fino alle 10:00)

- **Classifica: Boscovich 19° con 3467.** Il 9° (finale) è Ambrogio con 3789: mancano 322 punti. Dal 15° al 18° siamo a meno di 165. Dalle 10:00 alle 16:00 livello 8 con impostori e cambio di regola P1-P3.
- **Aggiornamento 11:10 (locali):** i rilasci e le versioni online sono in `team/RILASCI.md` (le righe qui sotto sono delle 08:30). **Consultorio 1.0.10 online dalle 10:06 UTC** (attesa della risposta del Ledger, slot rifiutato mai riproposto, EXPIRED/STALE_FENCE con recupero); `team/PROBLEMS.md` ha i tempi per fase e `tools/misura_latenze.js` li rimisura dalla console.
- **Online (tutti visibili):** CUP 1.0.23, **GP 1.0.5 dalle 08:29** (pubblicato da Alberto durante il freeze: il Ledger risponde in 7-9 minuti e il GP perdeva un giro per ogni ricetta, vedi `team/REVISIONE.md`), ospedale 1.0.4, specialist 1.0.4, consultorio 1.0.8.
- **Su `main`, da pubblicare alle 10:00** (tutti i test verdi: 21 file, test_facility TUTTO OK per ospedale e consultorio):
  - CUP 1.0.24 + **PR #86** (impostori: partner da `city.find` solo con ruolo della famiglia giusta e `no_clinical_advice`, reputazione più alta prima). La #86 è già aggiornata con `main`: si unisce senza conflitti.
  - Ospedale 1.0.5 (finestra MACH-1.3), consultorio 1.0.9 (anticipo minimo 10 ore d'agenda, margine al confirm, agenda e pagina 1 condivise per ondata). Il CUP 1.0.24 contiene anche: letture del Ledger condivise per ondata, ricetta + agenda + pagina 1 nello stesso turno, al massimo 6 partner per ricerca. Specialist senza modifiche.
  - **GP: niente deploy alle 10:00.** La 1.0.5 online è già il codice di `main`; la card è a 1.0.6 per il prossimo rilascio.
- **Deploy alle 10:00:** uno al minuto (la città rifiuta con `QUOTA_EXCEEDED`), prima il CUP, poi ospedale e consultorio. Dopo ognuno `city --json status agent:<id>`. Per il CUP controllare nei log `cup.find ... kept=` diverso da 0. Rollback: CUP `--to 1.0.23`, GP `--to 1.0.4`, ospedale `--to 1.0.4`, consultorio `--to 1.0.8`.
- **Perdita principale della notte:** confirm senza ricevuta (2 su 61) perché lo slot era già passato quando il cittadino decideva (3-27 ore d'agenda). Corretto con l'anticipo degli slot (ospedale 24 ore, CUP e consultorio 10-30 ore): da verificare in console sui primi percorsi dopo le 10:00 (`past`, `EXPIRED`, ricevute).
- **Aperti:** follow-up dello specialist (serve un verdetto di cardiologia dalla console per sapere quando è richiesto); pitch e vision 2027 (Ettore, prima della finale: vale anche per la scelta dei mentor).

## Dove trovare cosa

| File | Cosa contiene |
|---|---|
| `AI.md` | Regole per tutti: git, test, deploy, errori da non ripetere |
| `team/TASKS.md` | Chi fa cosa adesso |
| `team/PROBLEMS.md` | Bug aperti e risolti |
| `team/DECISIONS.md` | Scelte tecniche e perché |
| `team/JOURNAL.md` | Diario delle sessioni, la più recente in alto |
| `team/scenari.md` | Casi di test da provare a mano |
| `team/registro-regole.md` | Cambi di regola visti in gara |
| `docs-kit/` | Regole ufficiali del kit (sola lettura) |
