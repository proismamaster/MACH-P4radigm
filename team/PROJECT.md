# Stato del progetto (leggilo per primo)

> Milano Agentic City Hackathon, squadra p4radigm: 5 agenti di una ASST simulata. Gara dal 20/11 21:00 al 21/11 16:00.

## Stato attuale (21/11 ore 04:20)

- Online: consultorio 1.0.7, specialist 1.0.4, ospedale 1.0.3, GP 1.0.3, CUP 1.0.20. Tutto il codice del consultorio è in `main`.
- CUP: 5 correzioni in `main` (orologio senza weekend, paging fino a 20 pagine, anticipo minimo 1 ora, cancel con id, rifiuti day/gender), non ancora pubblicate. Finestra 04:30-05:00, ultimi deploy entro le 05:30, rollback `--to 1.0.20`.
- Alle 10:00: unire e pubblicare la #86 (impostori del CUP). Il filtro del consultorio è già in modalità sicura.
- Perdita principale: dopo il confirm del cittadino solo 2 percorsi su 61 arrivano alla ricevuta. Causa non confermata per ospedale e specialist (mancano i messaggi del Ledger).
- Gara fino alle 16:00; freeze del codice dalle 06:00 alle 10:00.

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
