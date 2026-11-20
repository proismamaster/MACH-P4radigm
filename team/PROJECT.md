# Stato del progetto (leggilo per primo)

> Milano Agentic City Hackathon, squadra p4radigm: 5 agenti di una ASST simulata. Gara dal 20/11 21:00 al 21/11 16:00.

## Stato attuale (20/11 ore 22:12)

- GP 1.0.2 online dalle 22:03: testo libero, risposta del Ledger da altra conversazione, ricetta solo dopo `prescribed`. In console `protocol_match +2`.
- Specialist 1.0.1 (consenso `report_sharing`): deploy in corso, il primo tentativo è fallito per la piattaforma (ingress non pronto). Online 1.0.0.
- CUP: cross-ASST unito su main (PR #8), da pubblicare 23:30-00:00. Rinnovo P1 ancora da fare.
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
