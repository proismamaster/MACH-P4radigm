
# Decisioni

## 2026-11-20 — Il GP annuncia la ricetta solo dopo `prescribed`
`main` comunicava la ricetta al cittadino nello stesso turno della `prescribe`, prima della conferma del Ledger. Rischio di ricetta fantasma. Ora si aspetta `prescribed` (fino a 6 secondi). Se arriva dopo, la ricetta parte con la risposta del Ledger o col messaggio successivo del cittadino.

## 2026-11-20 — Conflitti risolti tenendo tutte e due le correzioni
Nel GP convivono il fallback a parole chiave e il recupero delle risposte del Ledger da un'altra conversazione. Regola scritta nel `CLAUDE.md` della repo.

## 2026-11-20 — Regole per le AI nel `CLAUDE.md` della repo
Le AI dei compagni leggono da sole quel file: lì ci sono proprietà degli agenti, flusso git, test, deploy ed errori già trovati.
