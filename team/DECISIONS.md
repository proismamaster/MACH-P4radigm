
# Decisioni

## 2026-11-20 22:35 — Un file per agente con SOLO il codice del suo ruolo
Il mentor: il deploy controlla vulnerabilità e backdoor, i file grandi vanno in timeout (media squadra 12 minuti di conformance). Lo specialist è fallito 3 volte al passo "roll out" con 1219 righe; ridotto a 667 righe è stato rilasciato al primo colpo (1.0.2, 22:34). Ridotti anche GP (1434 → 672) e CUP (1656 → 1134). Metodo: `tools/riduci_agente.py` toglie le funzioni non raggiungibili dal ruolo, `tools/confronto_riduzione.py` verifica che versione completa e ridotta mandino esattamente gli stessi messaggi. **Non rimettere nei file il codice degli altri ruoli** (niente copia dell'esempio completo).

## 2026-11-20 — Il GP annuncia la ricetta solo dopo `prescribed`
`main` comunicava la ricetta al cittadino nello stesso turno della `prescribe`, prima della conferma del Ledger. Rischio di ricetta fantasma. Ora si aspetta `prescribed` (fino a 6 secondi). Se arriva dopo, la ricetta parte con la risposta del Ledger o col messaggio successivo del cittadino.

## 2026-11-20 — Conflitti risolti tenendo tutte e due le correzioni
Nel GP convivono il fallback a parole chiave e il recupero delle risposte del Ledger da un'altra conversazione. Regola scritta nel `CLAUDE.md` della repo.

## 2026-11-20 — Regole per le AI nel `CLAUDE.md` della repo
Le AI dei compagni leggono da sole quel file: lì ci sono proprietà degli agenti, flusso git, test, deploy ed errori già trovati.
