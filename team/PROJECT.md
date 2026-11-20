# Stato del progetto (leggilo per primo)

> Milano Agentic City Hackathon, squadra p4radigm: 5 agenti di una ASST simulata. Gara dal 20/11 21:00 al 21/11 16:00.

## Stato attuale (20/11 ore 22:53)

- GP 1.0.2 online dalle 22:03: testo libero, risposta del Ledger da altra conversazione, ricetta solo dopo `prescribed`. In console `protocol_match +2`.
- Specialist 1.0.2 dalle 22:34, con consenso `report_sharing`, referto unico e `ledger_ref` al check-in (dal passaggio di turno).
- CUP 1.0.1 dalle 22:47, con ricerca cross-ASST e correzione degli ID medico (dal passaggio di turno). La card su `main` riporta 1.0.2 (PR #13).
- Correzioni CUP per P1, consenso e ritiro degli slot testate in locale su `abed/cup-rinnovo-p1`. In attesa di revisione e verifica in Arena.
- GP con messaggi cortesi (PR #7) unito, da pubblicare dopo il CUP.
- Deploy stasera: 6-8 minuti, a volte `failed` per la piattaforma anche con la conformance tutta PASS. Controllare sempre con `city --json status <agente>`.
- Livelli: L2 alle 22:00, L3 alle 23:00, L4 alle 00:00.

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
