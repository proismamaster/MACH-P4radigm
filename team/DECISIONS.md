
# Decisioni

## 2026-11-21 11:20 — Offerte sostitutive in sospeso e riprova una sola volta anche tra pod
Dopo un cancel le offerte sostitutive possono non partire nello stesso turno (il Ledger risponde dopo l'attesa): il caso resta segnato `replace:pending` e il primo turno con agenda e slots le manda, altrimenti il `return` ai push del Ledger (che evita un secondo giro di offerte a ogni risposta) lascerebbe il cittadino senza offerte. Le offerte sostitutive partono da un solo punto, `_replace_offers`, che segna il caso: il ramo `reason=past` del confirm non lo faceva (000382, 911000394 senza offerte per 25 minuti). La riprova dopo `STALE_FENCE` controlla la cronologia: un nostro hold dopo il rifiuto significa che la riprova è già in corso, anche se l'ha fatta un altro pod (nel rilascio le due versioni leggono lo stesso rifiuto).

## 2026-11-21 11:00 — Il consultorio aspetta la risposta del Ledger nella cronologia, non nel push
Il Ledger risponde in 40-130 s e il push della sua risposta apre il nostro turno 40-90 s dopo (pod fermo, un solo caso: `held` 08:20:49, commit 08:22:23); un hold regge circa due minuti e 27 commit su 36 sono finiti in `STALE_FENCE`. Dopo agenda/world, hold e commit il turno rilegge la cronologia (la risposta c'è appena il Relay l'accetta) fino a 420 s (180 s alla prima versione: alle 10:06-10:10 UTC il Ledger rispondeva in 208-217 s e l'attesa scadeva poco prima della risposta), ogni secondo per 30 s e poi ogni 2 s, e prosegue subito; scaduta l'attesa vale il push come prima. In cloud il brain gira dopo il `202` del push (`defer`) e un messaggio riconsegnato mentre gira non lo rilancia (`_hold_redelivery`), quindi un turno lungo non si duplica. Rischio accettato: più letture della cronologia (circa una al secondo per ogni attesa aperta). Prova: `tools/test_consultorio_ledger_lento.py`, classe `Arena`.

## 2026-11-21 11:00 — Gli slot presi si segnano per tutto il processo; un solo giro di offerte
Il consultorio tiene ogni slot della sua struttura, quindi sa cosa è tenuto, prenotato o passato (`_GONE`): `held` e `full` valgono 150 s, `booked` e `past` per sempre; il caso che tiene lo slot non vede come preso il proprio hold. Gli slot segnati non si offrono né ad altri cittadini né ai CUP e un confirm su uno slot già preso riceve subito il cancel (senza un hold che il Ledger rifiuterebbe dopo 100 s). Lo slot rifiutato resta anche nella memoria del caso (`refused:`): il cancel appena mandato non è ancora nella cronologia da cui si calcolano le offerte sostitutive. Ogni risposta del Ledger (agenda, slots) dopo le offerte non ne aggiunge più (prima 3 in più a ogni push) e gli slot non offerti negli ultimi 150 s vanno in testa (`_spread`): i cittadini scelgono la prima offerta, la stessa prima scelta per tutti è un NO_CAPACITY certo. Con una pagina da 4 slot validi e più di 4 cittadini insieme la contesa resta.

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
