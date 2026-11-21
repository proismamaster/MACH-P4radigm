
# Decisioni

## 2026-11-21 08:29 — GP 1.0.5 pubblicato durante il freeze
Il Ledger rispondeva in 7-9 minuti e il GP aspettava il `world` prima di ogni ricetta: un giro intero (circa 14 ore d'agenda della finestra B) per ogni cittadino. Alberto ha dato l'OK al deploy del solo GP alle 08:29. CUP e consultorio restano al deploy delle 10:00 di Andrei. Rollback: `city rollback agent:rng5wcrzvhsj --to 1.0.4`.

## 2026-11-21 06:30 — Letture del Ledger condivise per ondata
Agenda, `world` e pagine del catalogo sono uguali per tutti i casi di un'ondata (`wave_id` nella risposta, prefisso dell'id del cittadino). Una lettura fatta per un caso vale per gli altri: 10 minuti per il `world` del GP, 5 minuti per agenda e pagine di CUP e consultorio. Si condivide solo dentro la stessa ondata, mai un'agenda in pausa, e le letture del caso stesso vincono. Rischio accettato: uno slot preso negli ultimi 5 minuti può essere offerto; la struttura rifiuta il hold e il CUP propone il successivo. Motivo: ogni giro di Ledger costava 6-9 ore d'agenda (PROBLEMS 06:15).

## 2026-11-21 06:30 — Al massimo 6 partner per ricerca
Con 25 partner per caso il CUP mandava 550 ricerche in 26 minuti e riceveva ~500 risposte, ognuna un turno con fino a 7 letture della cronologia, per 1 offerta arrivata a un cittadino. Ora: prima il partner del ring che parla la lingua del cittadino, poi quelli le cui offerte sono andate bene qui, poi i 7 che hanno offerto il 21/11 (se `city.find` li trova ancora), poi `city.find`, poi il ring; al massimo 6. Solo il turno che manda le ricerche aspetta le risposte.

## 2026-11-21 06:00 — Anticipo minimo 10 ore d'agenda (U 4), margine di 1 ora al confirm
Scelto con `tools/sim_percorsi.py`, che rigioca 21 percorsi veri della notte (agenda ricostruita, cittadino con la sua scadenza, giorni e genere dai suoi rifiuti). Minimo 4 ore: 14/21 prenotati; 10 ore: 19/21; 12 ore: la finestra B si stringe (19/21 invece di 20/21 con latenza bassa). Al confirm il CUP chiede solo 1 ora (il tempo di hold e commit), non il minimo delle offerte.

## 2026-11-20 22:53 — Il CUP riprende la pratica con la ricetta verificata
Per P1 il CUP usa un segnale di scadenza della struttura attesa o del Ledger. Registra la richiesta di rinnovo nella cronologia della pratica, chiude le offerte legate alla vecchia ricetta e verifica il nuovo numero sul Ledger. Nella stessa pratica cerca un altro slot dopo un tentativo fallito, perché la struttura deduplica gli hold per slot. La lettura preventiva di `rules` resta da verificare con il formato effettivo delle risposte in Arena.

## 2026-11-20 22:35 — Un file per agente con SOLO il codice del suo ruolo
Il mentor: il deploy controlla vulnerabilità e backdoor, i file grandi vanno in timeout (media squadra 12 minuti di conformance). Lo specialist è fallito 3 volte al passo "roll out" con 1219 righe; ridotto a 667 righe è stato rilasciato al primo colpo (1.0.2, 22:34). Ridotti anche GP (1434 → 672) e CUP (1656 → 1134). Metodo: `tools/riduci_agente.py` toglie le funzioni non raggiungibili dal ruolo, `tools/confronto_riduzione.py` verifica che versione completa e ridotta mandino esattamente gli stessi messaggi. **Non rimettere nei file il codice degli altri ruoli** (niente copia dell'esempio completo).

## 2026-11-20 — Il GP annuncia la ricetta solo dopo `prescribed`
`main` comunicava la ricetta al cittadino nello stesso turno della `prescribe`, prima della conferma del Ledger. Rischio di ricetta fantasma. Ora si aspetta `prescribed` (fino a 6 secondi). Se arriva dopo, la ricetta parte con la risposta del Ledger o col messaggio successivo del cittadino.

## 2026-11-20 — Conflitti risolti tenendo tutte e due le correzioni
Nel GP convivono il fallback a parole chiave e il recupero delle risposte del Ledger da un'altra conversazione. Regola scritta nel `CLAUDE.md` della repo.

## 2026-11-20 — Regole per le AI nel `CLAUDE.md` della repo
Le AI dei compagni leggono da sole quel file: lì ci sono proprietà degli agenti, flusso git, test, deploy ed errori già trovati.
