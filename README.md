# MACH-P4radigm

Cinque agenti AI per il **Milano Agentic City Hackathon (MACH 2026)**, squadra p4radigm, ASST Bicocca.
Il codice è stato scritto e rilasciato in 30 ore (20-21 novembre 2026). In classifica abbiamo chiuso intorno al 9° posto.

## Cosa fa

La città simula cittadini che scrivono in italiano libero (a volte in inglese, con gergo, con messaggi ostili) per ottenere una visita. Ogni ASST schiera cinque agenti, che parlano con i cittadini e tra loro e scrivono sul registro della città, il **Ledger**.

| Agente | Cartella | Ruolo |
|---|---|---|
| Medico di base (GP) | `asst/gp` | Capisce il disturbo, riconosce le red flag, prescrive una visita e annuncia la ricetta |
| Centro prenotazioni (CUP) | `asst/booking_centre` | Cerca gli slot, propone fino a 5 offerte, gestisce conferme, scadenze e ricerca presso ASST partner |
| Ospedale | `asst/hospital` | Fisiatria: slot, hold, commit, ricevuta, check-in |
| Specialista | `asst/specialist` | Cardiologia: come l'ospedale, più il referto con consenso |
| Consultorio | `asst/family_counseling` | Ginecologia ad accesso diretto, senza ricetta |

Percorso tipico: cittadino -> GP (`prescribe` sul Ledger) -> CUP (`hold` e `commit` sulla struttura) -> ricevuta -> check-in -> referto. Il giudice della città assegna punti per ogni passo (ricetta corretta +2, prenotazione nelle preferenze +2, check-in +2, referto +2) e toglie punti per prenotazioni mancate o dati divulgati senza consenso.

## Come è fatto

- Ogni agente è un `agent.py` con `async def main(need, city)`, costruito sul `city-sdk`. Si legge il caso con `city.history()` e si risponde con `city.say()`.
- Rilascio con `city deploy <agente>`: build, conformance (health p99, `custody.ack`), promozione. `city scale` regola pod e concorrenza.
- Protocollo tra squadre **MACH-1.x**: `need.request` -> `offer` o `cancel reason=...` -> `confirm` con consenso `cross_asst` -> `booking.receipt`.
- Regole di cura che cambiano a metà gara (P1 ricetta valida 2 giorni, P2 consenso cross-ASST, P3 riserva urgenti) e livelli 1-8 con vincoli, guasti e cittadini ostili.

## Cosa abbiamo imparato

1. **Il Ledger risponde in 3-9 minuti**, non in secondi. La spinta che dovrebbe aprire il turno successivo arriva dopo 60-90 s oppure mai. Un agente che chiude il turno e aspetta la spinta resta muto: l'abbiamo capito solo nel pomeriggio. Soluzione: leggere la storia del caso dentro il turno, con un'attesa limitata (`_until`, `_await_line`).
2. **Le ondate di cittadini arrivano ogni 20 minuti** (:11, :31, :51), 40-60 insieme. Con concorrenza 8 il CUP e il GP restavano muti; un pod con concorrenza 32 ha aiutato.
3. **Ogni deploy o scale perde i messaggi in volo.** Un solo rilascio alla volta, mai subito dopo un'ondata.
4. **Misurare prima di cambiare.** Una nostra modifica "ragionevole" (slot B ad almeno 20 ore) ha raddoppiato i rifiuti per scadenza ed è stata ritirata. Un'altra (annunciare la ricetta senza aspettare il Ledger) è finita in rollback: l'ultimo effetto non è stato verificato perché la piattaforma ha chiuso.
5. Il cittadino conferma da 3 a 35 minuti reali dopo l'offerta, cioè ore di agenda: gli slot troppo vicini arrivano già passati (`reason=past`).

## Come è stata usata la repo

- Lavoro in parallelo di 5 persone e di più AI (Claude Code, ChatGPT), con regole in `CLAUDE.md` e `AGENTS.md` per non pestarsi i piedi.
- 35 file di test in `tools/` (`python tools/test_*.py`), con un Ledger finto. Regola: prima il test rosso sul codice vecchio, poi verde.
- Registro di ogni deploy in `team/RILASCI.md`, decisioni in `team/DECISIONS.md`, problemi aperti in `team/PROBLEMS.md`, compiti in `team/TASKS.md`.
- `tools/misura_latenze.js` e `tools/sim_percorsi.py` misurano i tempi del Ledger e simulano i percorsi.

## Struttura

```
asst/        i 5 agenti (agent/agent.py, card.yaml, city.yaml, Dockerfile)
tools/       test, simulatore, misure, script di deploy
team/        registro rilasci, decisioni, problemi, compiti, scenari
docs-kit/    guide e regole del kit ufficiale (sola lettura)
reference/   esempio e scaffold ufficiali (sola lettura)
```

## Eseguire i test

Servono Python e il pacchetto `city-sdk` (installato con `city-cli`).

```bash
python tools/test_specialist_attesa.py   # un file
for f in tools/test_*.py; do python "$f" || echo "FAIL $f"; done
```

## Stato

Archivio di gara: non più in esecuzione. `docs-kit/` e `reference/` sono materiale degli organizzatori. Gli id degli agenti in `card.yaml` valevano solo per la città dell'evento.

## Squadra

p4radigm: Ismail (leader, coordinamento e rilasci), Andrei Ciubara (ospedale, rilasci), Abed (CUP), Hapca (consultorio), Ettore (pitch e monitoraggio).
