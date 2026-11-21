
# Problemi

## CUP 1.0.27 e ricevuta già in cronologia

- Su `5976e31`, se una ricevuta della struttura è leggibile nella cronologia prima che arrivi come messaggio, una nuova conferma del cittadino può attivare il reinvio. Alla richiesta successiva il CUP può avviare la sostituzione della visita già prenotata.
- Riprodotto con il City SDK. Verificare in Arena per lo stesso `need_id` l'ordine fra ricevuta della struttura, reinvio del CUP e ricevuta al cittadino. La prova distingue ricevute attribuibili all'offerta in corso da risposte vecchie o di altre strutture.

## Consultorio 1.0.13 e il cambio di pod (21/11, messaggi fino alle 11:23 UTC)

- **Un terzo hold dopo il cancel.** `N-2026-11-02-8909110003810002` (orari `sent_at`, UTC):

| ora | evento |
|---|---|
| 10:44:00, 10:55:42 | hold e riprova sullo slot `…20261225-1030` |
| 11:06:57 | `refused commit code=STALE_FENCE` (il secondo) |
| 11:07:03 | cancel al cittadino (pod 1.0.12, fermato alle 11:07:50 circa), `agenda` e `world page=1` chiesti |
| 11:12:09 | il cittadino conferma di nuovo lo stesso slot (push consegnato al pod nuovo alle 11:13) |
| 11:13:05 | **terzo hold** sullo slot annullato (pod 1.0.13) |
| 11:13:08 | arrivano `agenda` e `slots page=1/4` (risposta del Ledger a una richiesta di 6 minuti prima) |
| 11:22:33 | `refused hold code=EXPIRED detail=slot ... has passed` |

  Cause possibili, la correzione le copre entrambe: il rifiuto delle 11:06:57 riconsegnato al pod nuovo (la memoria della riprova era vuota e la cronologia mostrava solo il cancel dopo di esso), oppure il confirm ripetuto del cittadino su uno slot di cui la cronologia ha il cancel. Un caso simile: `…3760002` ha avuto cancel `reason=past` alle 11:13:41 e un hold sullo stesso slot alle 11:15:35.
- **`…911000396`, il caso più pulito** (nessun messaggio del cittadino in mezzo): secondo `STALE_FENCE` 11:03:33, cancel e `world page=2` 11:03:35 (pod 1.0.12); **terzo hold 11:09:15** (pod 1.0.13, il rifiuto riconsegnato dopo il rilascio delle 11:07); pagina 2 del Ledger accettata 11:09:21; `refused hold code=EXPIRED` 11:16:45; prime offerte sostitutive **11:26:42**, 23 minuti dopo il cancel e solo dopo il rifiuto del terzo hold (il push della pagina 2 trovava la memoria vuota e il `return` ai push del Ledger). Con la correzione il push della pagina 2 manda le offerte e il rifiuto riconsegnato non fa un hold.
- **Offerte sostitutive dopo `cancel past`**: `…3760002` cancel 11:13:41, pagina 2 chiesta nello stesso secondo; `…3290006` cancel EXPIRED 11:05:23, pagina 2 alle 11:11:22, offerte al cittadino alle 11:18:17. Funzionano; il ritardo viene dal Ledger (5-6 minuti) e dal push (1-6 minuti).
- **Caso con la ricerca di un CUP nello stesso `need_id`**: in `…3810002` l'`agent:yr8hjc5q7n98` ha mandato un `need.request` alle 11:09:34. Da quel momento `_family` mandava le risposte del Ledger solo alla ricerca e il desk del cittadino non completava mai le offerte sostitutive.
- Correzione sul branch `hapca/consultorio-stato-dalla-cronologia` (`_reacted_since`, `_cancelled_for`, `_owed`, `_resume_owed`, riprova solo con un hold precedente): non pubblicata, aspetta l'OK al rilascio. Prova: `tools/test_consultorio_ledger_lento.py`, funzione `cambio_di_pod`.
## CUP: ricerche ai partner e alternative dopo un rifiuto per scadenza (21/11)

- La #86 filtrava i nuovi risultati dell'Index. Il test dimostra che la lista del ring e i partner appresi potevano riportare nella ricerca una struttura con un ruolo o un servizio incompatibile. Il CUP applica la stessa esclusione alla lista finale.
- Il caso 3130005 mostra tre rifiuti per scadenza. Con una pagina di slot simulata, il CUP poteva poi offrire una data già oltre il termine della pratica, perché la ricerca locale di alternative ricalcolava la finestra dal momento della risposta. Ora il primo tentativo di alternativa usa il termine della pratica.

## Verifica della 1.0.12 in sola lettura (21/11, messaggi fino alle 10:56 UTC)

- **Tre `held` su tre dopo le 10:24 UTC finiscono in `STALE_FENCE` con il commit partito entro 2 s** (orari `sent_at`, UTC; il Ledger risponde `refused commit code=STALE_FENCE detail=the fence expired`):

| need_id | hold | `held` | commit | `STALE_FENCE` |
|---|---|---|---|---|
| `N-2026-11-02-890911000386` | 10:30:44 | 10:35:44 (300 s) | 10:35:46 | 10:40:41 (+295 s) |
| `N-2026-11-02-890911000396` | 10:41:25 | 10:46:07 (282 s) | 10:46:09 | 10:52:08 (+359 s) |
| `N-2026-11-02-8909110003810002` | 10:44:00 | 10:49:58 (358 s) | 10:50:03 | 10:55:40 (+337 s) |

  Riferimento 1.0.11, stesso schema: `…890911000386`, `held` 10:22:30, commit 10:22:31, `STALE_FENCE` 10:25:35 (+185 s). Il Ledger a 08:48 UTC rispondeva in 69 s (hold) e 82 s (commit) e prenotava; da 10:22 sta tra 184 e 359 s. La traccia con i `hold_id` è stata passata ad Andrei per i mentori (lease di un hold, rinnovo, latenza attesa).
- **Offerte sostitutive mai mandate dopo un `cancel reason=past`** (il ramo R7 di `_confirm_once`): `…911000382` (cancel 10:26:02, pagina 2 arrivata alle 10:31:14, nessuna offerta per 25 minuti) e `…911000394` (cancel 10:40:47, pagina 2 alle 10:45:04, nessuna offerta alle 10:56). Il ramo chiamava `_advance(replacing=True)` senza segnare il caso `replace:pending` (lo faceva solo `_recover`): il turno della pagina 2 trovava le offerte già mandate e non diceva niente. In `…911000386` le offerte sono partite (10:46:30) solo perché un `STALE_FENCE` successivo ha attivato `_recover`. **Correzione**: `_replace_offers`, unico punto da cui partono le offerte sostitutive (segna il caso e chiama `_advance`), usato dal ramo `past` e da `_recover`.
- **Nessun hold doppio dopo le 10:24** (le riprove di `…386`, `…396`, `…3810002` sono la riprova unica dopo `STALE_FENCE`, partita 2 s dopo il rifiuto; il doppio confirm di `…394` alle 10:36:03 ha dato un solo cancel). Doppio solo prima del rilascio: `…003290005` (10:14:19 e 10:15:24, entrambi `EXPIRED`).
- **Slot passati:** nessun `refused hold EXPIRED` dopo le 10:24; tre `cancel reason=past` al confirm (nessun hold su slot passati): `…382` slot a −10,9 h, `…386` a 0,2 h, `…394` a 0,9 h d'agenda, con confirm elaborati 197-301 s dopo l'arrivo e offerte di 10-24 ore di anticipo ormai consumate. Le riprove di `…396` (10:52:17, slot a 10,9 h) e `…3810002` (10:55:42, slot a 6,0 h) partono con il Ledger a ~6 minuti per richiesta: la seconda avrà lo slot passato quando l'hold viene creato. È il caso della riprova da non fare sotto le ~8 ore d'agenda (non fatto).
- In vivo funzionano: la prima offerta alla risposta del Ledger (`…003290006`: risposta 10:48:20, offerta 10:48:22; `…003760002`: 10:45:34 → 10:45:39), il commit entro 1-2 s da `held`, la riprova 2 s dopo il rifiuto.

## Consultorio 1.0.12 online (10:24 UTC) e prova diretta del limite della piattaforma (21/11 10:25)

- **L'attesa nella cronologia funziona:** caso 911000386, `held` alle 10:22:30 (il Ledger aveva impiegato 207 s per l'hold), **commit partito alle 10:22:31, un secondo dopo**. Prima partiva 60-190 s dopo.
- **Ma il commit fallisce lo stesso:** `refused commit code=STALE_FENCE detail=the fence expired` alle 10:25:35, 185 s dopo `held`. È la conferma diretta della stima dei dati (un hold regge poco più di 100 s, i riusciti hanno `held` → esito sotto i 98 s, i falliti da 125 s): **con il Ledger a ~3 minuti per richiesta nessun commit può riuscire, nemmeno partendo subito**. Il limite non è il nostro codice: si sblocca solo quando la latenza del Ledger scende sotto i ~100 s (alle 08-10 UTC c'erano finestre da 40-90 s e 4 commit su 9 riuscivano).
- Offerte sostitutive con `replace:pending` e riprova unica tra pod: nessuna riga `care.*.failed` nei log, nessun hold doppio nei primi percorsi della 1.0.12; la prova in vivo delle sostitutive in sospeso aspetta un caso con la pagina 2 in ritardo (911000382, cancel alle 10:26:02, pagina 2 chiesta alle 10:26:03).
- **Da fare, in rilasci separati:** (1) anticipo minimo per l'accesso diretto a 16-20 ore (senza scadenza: costa solo qualche slot), (2) niente riprova dopo `STALE_FENCE` se lo slot è a meno di ~8 ore d'agenda (la riprova costa due giri del Ledger = 7 ore alla latenza di oggi): il caso 003290005 ha fatto due hold su uno slot già passato (`EXPIRED ... has passed` a 10:17:00 e 10:18:06).

## Primi percorsi della 1.0.10 e 1.0.11 (21/11 10:10-10:16 UTC): due difetti miei, uno slot che scade

Fonte: i messaggi del consultorio (`/v1/team/agents/agent:nkh372rd16yq/messages`) subito dopo i rilasci delle 10:06 e delle 10:15.

1. **Offerte sostitutive mai mandate (911000381).** NO_CAPACITY alle 10:04:53, cancel alle 10:07:39, agenda e world richiesti alle 10:07:40 (il pod nuovo non aveva letture condivise e il caso non ne ha di sue). Il Ledger risponde alle 10:11:21, 221 s dopo, a un'attesa ormai scaduta (180 s). Il turno del push di quella risposta trovava le offerte già mandate e, per il `return` che avevo messo ai push del Ledger dopo le prime offerte, non diceva niente: il cittadino resta senza offerte (5 minuti alle 10:16). **Correzione**: il cancel segna il caso con `replace:pending`; finché le offerte sostitutive non sono partite i turni dei push del Ledger le completano.
2. **Due hold per lo stesso slot (003290005).** `refused commit STALE_FENCE` alle 10:10:50; hold di riprova alle 10:14:19 e un secondo alle 10:15:24, dal pod nuovo (rilascio delle 10:15) che rilegge lo stesso rifiuto senza averne memoria. Il secondo hold trova il primo e dà un falso NO_CAPACITY. **Correzione**: prima di riprovare si legge la cronologia: se dopo il rifiuto c'è già un nostro hold per lo slot, la riprova è in corso e non si fa niente.
3. **Latenza del Ledger 199-221 s per richiesta** (agenda e world 10:06:09 → 10:09:37; 10:06:28 → 10:10:01; 10:07:40 → 10:11:21; un hold 10:10:52 → rifiuto 10:14:11), il push 60-200 s. Con 180 s l'attesa scadeva poco prima della risposta: portata a 420 s (1.0.11). A questa latenza nessun commit può stare nella durata di un hold (circa 2 minuti), anche partendo subito.
4. **Gli slot scadono prima dell'hold.** Il caso 911000376 ha l'hold rifiutato `EXPIRED ... slot ...1030 has passed` alle 10:14:11: offerto con 10 ore d'agenda di anticipo, il giro offerta → conferma → hold dura ora 10-14 minuti reali = 10-14 ore d'agenda. L'anticipo minimo di 10 ore (`_MIN_LEAD`) non basta più per il consultorio ad accesso diretto (senza scadenza, 14 giorni d'orizzonte): da alzare a 16-20 ore, e meglio ricavarlo dalla latenza misurata. Non fatto: va in un rilascio a parte.
5. **Codice nuovo `FACILITY_CANCELLED`** (`refused hold ... detail=the facility cancelled the first booking`, 911000382 alle 10:13:54; già visto alle 02:09 per 911000248): non capito. Il cittadino riceve `cancel reason=FACILITY_CANCELLED` e nuove offerte.

## Consultorio e latenza del Ledger: NO_CAPACITY, STALE_FENCE, tempi di hold e commit (21/11, dati 10:50 locali)

Fonte: `/v1/team/agents/<id>/messages` (consultorio 1741 messaggi dal 20/11 22:30 UTC) e i percorsi `2560005` e `3290003`. Orari UTC. Lo strumento è `tools/misura_latenze.js` (si incolla nella console di `/team`; `await misura('agent:nkh372rd16yq')`).

**I due percorsi (stessa storia).** 07:30:12 messaggio del cittadino → 07:31:24 il consultorio chiede agenda e world (+71 s) → 07:33:08 risposta del Ledger → 07:34:44 prime offerte (+96 s): 15/12 10:30, 12:00, 14:30, 16:00, cioè **tutti e soli gli slot validi della pagina 1**, uguali per cinque cittadini (2710004, 2660004, 2560005, 3290003, 3200003). 07:35:33 il cittadino conferma il primo → 07:37:19 hold (+105 s) → 07:39:08 `refused hold code=NO_CAPACITY` (+109 s: un altro caso tiene lo slot) → 07:40:23 `cancel reason=NO_CAPACITY` (+69 s) e subito (70 ms) tre offerte che **riportano lo slot rifiutato come prima della lista**. Il cittadino lo riconferma alle 07:41:28, 07:57:29, 08:13:31: nessuna risposta (secondo hold mai mandato, cronologia senza novità). Percorso chiuso `failed`.

**Cause confermate (non ipotesi).**
1. *Slot rifiutato riproposto.* `_on_refused` mandava il cancel e poi calcolava le offerte sostitutive sulla cronologia letta prima: il cancel appena mandato non c'è, quindi `_withdrawn` non lo vedeva e lo slot (ancora `free=1` nella pagina del Ledger) tornava primo.
2. *Contesa.* Cinque cittadini, quattro slot, stessa lista nello stesso ordine: con capacità 1 ne passa uno. Prima ogni push di agenda/slots aggiungeva un secondo giro di offerte (4 offerte invece di 3).
3. *STALE_FENCE: il commit parte tardi.* Su 36 `held` del consultorio: 9 `committed`, 27 `refused commit STALE_FENCE detail=the fence expired`. I commit partiti entro 10 s da `held` sono riusciti tutti (0, 1, 1, 4, 7, 7, 8, 10 s; uno a 42 s); quelli partiti dopo 60 s o più sono falliti tutti (60-369 s). Contando da `held` fino alla risposta al commit, i riusciti stanno tra 12 e 98 s e i falliti partono da 125 s: l'hold regge circa due minuti. Il ritardo è il push: il Relay accetta `held` e il nostro turno parte 60-90 s dopo (caso `3200004` solo, pod fermo: `held` 08:20:49, commit 08:22:23).
4. *EXPIRED sull'hold = slot passato* (`detail=slot ... has passed`): 50 hold su 98 con risposta. Una riprova non può riuscire e costava altri 2-3 minuti reali.
5. *Il pod non è il collo di bottiglia:* il caso `3200004` era l'unico attivo (08:15-08:35) e ogni passaggio costava comunque 40-130 s; ci sono passaggi da 4-10 s (08:32:58 `held` → commit dopo 5 s → `committed` → ricevuta dopo 10 s). Lo scale non serve.

**Tempi per fase** (mediana / p90 in secondi, (n); finestre di 2 ore UTC; il Ledger e noi siamo separati):

| Fase | 20/11 22-24 | 21/11 00-02 | 02-04 | 04-06 | 06-08 | 08-10 |
|---|---|---|---|---|---|---|
| **Prima offerta** — nostro ritardo prima di chiedere al Ledger | 2/4 (3) | 37/152 (7) | 192/240 (29) | 439/523 (5) | 69/69 (4) | 53/56 (4) |
| risposta del Ledger a agenda e world | 5/7 | 39/364 | 185/230 | 451/503 | 106/106 | 44/59 |
| nostro ritardo dopo la risposta, fino all'offerta | 2/8 | 41/172 | 194/252 | 401/480 | 91/95 | 47/55 |
| **totale primo messaggio → prima offerta** | 15/17 | 120/620 | 586/668 | 1320/1367 | 275/275 | 150/153 |
| **Hold** — confirm → hold (nostro) | 9/10 (3) | 45/317 (7) | 195/653 (42) | 346/872 (30) | 107/461 (10) | 44/359 (6) |
| hold → `held` o rifiuto (Ledger) | 16/16 | 32/156 | 183/220 | 290/508 | 107/132 | 69/92 |
| **Commit** — `held` → commit (nostro) | 10/10 (2) | 1/78 (5) | 174/220 (12) | 336/369 (6) | 68/77 (6) | 8/92 (5) |
| commit → `committed` o rifiuto (Ledger) | 15/15 | 15/118 | 184/210 | 341/358 | 67/79 | 82/94 |
| `committed` → ricevuta (nostro) | 7/7 | 14/50 (4) | — | — | — | 17/17 (3) |

In ogni finestra **il nostro ritardo è pari a quello del Ledger**: ogni passaggio del Relay costa lo stesso nei due sensi. Esiti dell'intera serie: `commit STALE_FENCE` 27, `committed` 9, `hold EXPIRED` 50, `hold NO_CAPACITY` 11, `hold FACILITY_CANCELLED` 1.

**Correzione** (branch `hapca/consultorio-ledger-lento`, non ancora pubblicata): nel consultorio il turno che ha appena chiesto al Ledger rilegge la cronologia (la risposta c'è appena il Relay l'accetta, il push arriva dopo) fino a 420 s (180 s nella 1.0.10: alle 10:06-10:10 UTC il Ledger rispondeva in 208-217 s), poi lascia al push come prima; commit subito dopo `held`, ricevuta subito dopo `committed`, offerte subito dopo agenda e world. Lo slot rifiutato resta nella memoria del caso; gli slot tenuti, prenotati o passati sono segnati per tutto il processo e non si offrono né ad altri cittadini né ai CUP; un confirm su uno slot già preso riceve subito il cancel (niente hold che il Ledger rifiuterebbe dopo 100 s). EXPIRED sull'hold non si riprova; STALE_FENCE ed EXPIRED sul commit una volta sola. Un solo giro di offerte per risposta del Ledger, con in testa gli slot non offerti negli ultimi 150 s. Un rifiuto immediato del Relay (CapError su hold o commit: `EXPIRED`, `NO_CAPACITY`, `STALE_FENCE`...), che `_say` inghiottiva lasciando il confirm senza risposta, passa dallo stesso recupero; un errore incerto (429, 5xx) libera il claim e il confirm rimandato rifà l'hold (come nell'ospedale, PR #98). `history` in 504 in `main()` si rilegge tre volte invece di chiudere il messaggio come `rejected`. Il cancel nomina l'`offer_id` della riga dello slot (con l'offerta unica nominava quello della prima). Test: `tools/test_consultorio_ledger_lento.py` (53 controlli, 32 falliscono su `main`).

**Non confermato.** (a) Quanto dura davvero l'hold: dalle tempistiche 100-125 s dalla risposta del Ledger, ma la durata non è nel kit. (b) Se la lettura della cronologia ogni 1-2 s per 3 minuti pesi sul Relay: 5 casi in parallelo sono circa 5 letture al secondo, come le 24 letture da 0,25 s di prima ma più lunghe. (c) Con una sola pagina di 4 slot validi e più di 4 cittadini insieme la contesa resta: i cittadini oltre il quarto ricevono slot già offerti, in coda; il Ledger si rilegge alla pagina 2 solo quando finiscono.

**Stesso problema nelle altre strutture** (stessa misura sulla cronologia disponibile: ospedale dalle 08 UTC, specialist dalle 00 UTC): ospedale `hold NO_CAPACITY` 28 su 42, `commit STALE_FENCE` 10 su 12 (`held` → commit mediana 107 s, p90 178); specialist `hold NO_CAPACITY` 112, `hold EXPIRED` 20, `commit STALE_FENCE` 17 su 24 (`held` → commit mediana 61-87 s). Sono i file di Andrei e di Ismail: la stessa attesa e lo stesso segno degli slot presi sono da portare, non l'ho fatto.

## CUP: timeout della cronologia all'inizio del turno (21/11)

- Su `main` a `7fc36cd`, un `UPSTREAM_TIMEOUT` (504) di `city.history` nel turno della conferma usciva da `main()` e l'SDK chiudeva il messaggio come `rejected`. Il test riproduce il guasto sul CUP. Il caso 3590002 è il riferimento per lo stesso tipo di guasto lato ospedale. La causa del silenzio in quel percorso resta da verificare nei log.
- Il CUP ritenta una volta sui 5xx. Se la rilettura fallisce o l'errore è 4xx, registra `cup.history.failed` e si ferma prima di eseguire azioni che dipendono dallo stato.

## CUP, campione precedente al rilascio della 1.0.24 (21/11)

- Nei 39 export di percorsi falliti, i rifiuti del cittadino compaiono in 14 percorsi per `day`, 13 per `gender`, 11 per `deadline` e 1 per `past`. Le categorie si sovrappongono. Sono conteggi tra i falliti esportati e non misurano il tasso di errore della wave.
- I percorsi `N-2026-11-02-8909110003550003` e `N-2026-11-02-8909110003030004` hanno rifiutato per `deadline` tutte e tre le offerte per lo stesso giorno in fisiatria. Al controllo in console il CUP risultava ancora alla 1.0.23.
- Conferma senza ricevuta o annullamento visibile: **Ospedale Bicocca** `N-2026-11-02-8909110001220010`, `N-2026-11-02-8909110002990004`, `N-2026-11-02-8909110003590002`, `N-2026-11-02-8909110003610002`. In `3590002` la prima conferma arriva 55 secondi dopo l'offerta e il verdetto non registra un hold. **Specialista Bicocca** `N-2026-11-02-8909110002840005`: il verdetto registra un hold scaduto senza commit. Per stabilire il passaggio mancante vanno incrociati i log del CUP, della struttura e del Ledger per lo stesso need.

## Verdetti delle 06:00-08:38 (console, 200 percorsi, 99 chiusi letti uno per uno)

**1. Cardiologia con le righe dello specialist** (per il follow-up chiesto da Andrei). Percorso `N-2026-11-02-8909110001820005`, L4, `done`, punteggio +3:
- GP: messaggio 07:15:11 UTC → ricetta VIS-CARD B alle 07:17:34. CUP: `need.request` 07:18:35 → offerta 07:23:12 (s1, lun 14/12 14:30) → confirm 07:24:07 → ricevuta 07:28:45. Check-in del cittadino 07:30:06 (`agenda_time=2026-12-14T14:56`); lo specialist risponde alle 07:33:55 con `checkin` e `consent purpose=report_sharing`. Il cittadino non risponde; verdetto alle 07:38:26.
- Fatti: `hold`, `commit ok=false (in_pref=false, in_set=false)`, `checkin ok=true`, **`report ok=false`**, `receipt ok=true`.
- Righe: GP `protocol_match +2`; CUP **`booking_outside_set -1`**; specialist `checkin_honored +2`, **`report_missing -1`**; Ledger `honored_slot +1`. Nessuna riga di follow-up: senza referto non si vede se il protocollo lo chiedeva.
- **Specialist (Ismail/Andrei)**: archivia il referto solo quando arriva la risposta al consenso (`_on_report_consent`). Il kit: "Referto archiviato e follow-up per protocollo +2", "Referto mancante −1", e "se la risposta non contiene il campo chiesto ... lo specialista archivia il referto non condiviso. Aspettare una risposta che non arriverà lascia il percorso fermo". Da decidere: archiviare il referto non condiviso se il consenso non arriva entro poco tempo.
- **CUP**: lo slot era ~4,5 ore d'agenda dopo l'offerta (minimo 4 ore della 1.0.23). Con 4,6 minuti tra confirm e ricevuta, al commit era già passato (agenda ~15:20 per uno slot delle 14:30) → fuori dall'insieme. Il minimo di 10 ore (`e2d1518`, CUP 1.0.24 alle 10:00) lo esclude.

**2. Quattro `emergency.no_escalation -2` sul GP** (05:10-05:18 UTC): il GP ha mandato `escalate.emergency` in tutti e quattro i casi, ma 6,7-7,6 minuti dopo il messaggio (05:10:07-05:11:21 → 05:16:49-05:18:03), dopo che i cittadini avevano rimandato il messaggio (05:15:17). Il caso giudicato `ok=true` aveva l'escalation prima di quel nuovo invio. Causa: ritardo di consegna della piattaforma in quei minuti (vedi sotto), non una red flag mancata. Nessuna correzione possibile nel codice.

**3. Righe del CUP nei 99 chiusi**: `wrong_outcome` 35, `empty_set_alternative` 31.

## CAUSA CONFERMATA (21/11 06:15): il Ledger risponde in 7-9 minuti, ogni passaggio costa ore d'agenda

Dati: messaggi di CUP, GP e consultorio letti da `/v1/team/agents/<id>/messages` (21/11 04:18-05:15 UTC, 1900 messaggi del CUP, 600 del GP, 300 del consultorio) e percorsi da `/v1/team/journeys/<need_id>`. Orari UTC.

| Fatto | Misura |
|---|---|
| Risposta del Ledger al CUP | agenda p50 537 s, ricetta p50 540 s, world p50 478 s (35 richieste) |
| Risposta del Ledger a GP e consultorio | `world`/`prescribe` 440-470 s; `hold`/`commit`/`agenda` 445-585 s |
| La risposta del Ledger apre il nostro turno | 360-450 s dopo, senza altri messaggi in mezzo |
| Inizio | GP: p50 22 s alle 03:40, 246 s alle 04:10, 338 s alle 04:20 |
| Il pod non c'entra | GP: 34 messaggi su 221 a meno di 1 s l'uno dall'altro; scale a concorrenza 8 (04:48) senza effetto |
| `world` al GP | 84 risposte su 84: una pagina di slot, nessuna tabella dei protocolli, nessuna red flag |
| Ricerche ai partner | 550 in 26 minuti (22 × 25), ~500 risposte (315 `no_availability`, 99 "Ricevuto"), 45 offerte da 7 partner, 1 arrivata a un cittadino, 0 confirm |

Effetto: un minuto reale è un'ora d'agenda, quindi ogni passaggio costa 6-9 ore della finestra B (48 ore). Prima del correttivo il GP faceva 3 passaggi per una ricetta e il CUP 2-6 prima della prima offerta.

**Correzione** (`f72ce63`): world, agenda e pagine condivisi per ondata (GP 10 minuti, CUP e consultorio 5); ricetta + agenda + pagina 1 nello stesso turno; pagine mancanti 6 alla volta; al massimo 6 partner per ricerca, prima quelli che offrono; nessuna attesa nei turni aperti dalle risposte dei partner. GP 1.0.5 online dalle 08:29; CUP 1.0.24 e consultorio 1.0.9 alle 10:00. Da verificare in console: tempo cittadino → ricetta, `need.request` → prima offerta, ricerche ai partner per caso.

**Resta**: hold → commit sono due giri obbligati (il commit vuole `hold_id` e `fence` del `held`). Il ritardo è della piattaforma: non si vede se è uguale per tutte le squadre.

## CAUSA CONFERMATA dei confirm senza ricevuta: lo slot e' gia' passato quando il cittadino decide (21/11 04:25)

Un minuto reale e' un'ora d'agenda. Il cittadino risponde alle offerte dopo 3-20 minuti reali (nei dati: mediana ~176 s, p90 ~217 s, punte di 1116-1645 s), cioe' dopo 3-27 ORE d'agenda. Il CUP e le strutture offrono i primi slot disponibili (anticipo minimo 4 ore, e dopo la mia PR 1 ora): quando il cittadino conferma o rifiuta, lo slot e' gia' nel passato.

Prova (consultorio 1.0.7, percorso 8909110001400007): primo messaggio del cittadino 02:47:55, prime offerte 02:55:05 (+430 s: slot di venerdi' 27 alle 10:30, 12:00, 14:30), `confirm` alle 03:15:19, `cancel reason=EXPIRED` del consultorio UN secondo dopo (il Ledger rifiuta l'hold di uno slot passato), poi tre offerte nuove; il cittadino le rifiuta alle 03:18 con `reason=past`.

Spiega: i rifiuti `past` (24), gli `EXPIRED` del consultorio, buona parte dei `facility_cancelled` e il 97% di confirm senza ricevuta. NON spiega i 34 silenzi, ne' `STALE_FENCE`.

**Correzione fatta**: ospedale 24 ore (`9873f6f`, online dalla 1.0.4); CUP e consultorio preferenza 30 ore (`62eb588`, online da CUP 1.0.22 e consultorio 1.0.8); minimo 10 ore e margine di 1 ora al confirm (`e2d1518`) e R7 del consultorio (`b5dcb99`) si pubblicano alle 10:00. Testo originale: offrire slot ad almeno ~24 ore d'agenda (meglio 30) dall'ora dell'offerta, tenendo come minimo 4 ore; i posti vicini vanno in coda. Valori da cambiare: consultorio `_LEAD` e `fitting`/`_facility_slots`; CUP `_LEAD` (4 h -> 24+ h) e `_MIN_LEAD` (1 h -> 4 h). Entro le finestre B (2 giorni) e D (5 giorni) restano posti. Verificare in console `past` ed `EXPIRED` dopo il deploy.

## Confirm senza ricevuta e rifiuti dei cittadini (console 21/11 ~04:00 locali, 200 percorsi)

Dati dal sito: `/v1/team/journeys` e `/v1/team/journeys/<need_id>`, con il login della squadra. Orari UTC.

| Cosa | Numeri | Stato |
|---|---|---|
| Confirm del cittadino, poi ricevuta | 2 su 61 | aperto |
| Dopo il confirm: `facility_cancelled` dal CUP | 21 (mediana 570 s, max 1076 s) | causa non confermata per ospedale e specialist |
| Dopo il confirm: nessuna risposta | 34 | aperto |
| Consultorio dopo il confirm: `cancel EXPIRED` / `STALE_FENCE` | 3 / 1 | riprova del hold in 1.0.7, da verificare in console |
| Rifiuti per `deadline` / `past` / `gender` / `day` | 103 / 24 / 14 / 8 | CUP: correzioni in `main`, non pubblicate |
| CUP `no_booking -1` | 70 | come sopra |

- **Giorni e genere sono scritti a parole**: "posso venire solo lunedì o mercoledì", "solo in alcuni giorni". Mai `days=`. Con `reason=day` o `reason=gender` il cittadino rifiuta; il CUP non ne teneva conto e offriva tre slot dello stesso giorno (221, 255, 249, 244, 225, 210, 100002). Correzione: `hapca/cup-rifiuti-day-gender` (in `main`).
- **Consultorio, 5 percorsi su 8**: confirm, poi `cancel reason=EXPIRED` o `STALE_FENCE` dal Ledger (256, 229, 248, 2160002, 216 con `receipt_refused -2`). Riprova del hold una volta (1.0.7). Non si vedono i messaggi del Ledger: ipotesi del polling di 6 s troppo breve, non provata.
- **Latenza delle strutture di 8-14 minuti**: coincide con le ore di chiusura (`Strutture chiuse, orario 08:00-18:00`, un minuto reale = un'ora d'agenda); vale per tutte le squadre.
- Per confermare le cause: salvare dal pannello "Apri i log" un percorso fresco dopo il confirm, oppure leggere `/v1/team/agents/<id>/messages` quando il sito risponde.

## Livello 5/6 (console, 21/11 dalle 00:30 UTC = 01:30 locali)

Wave W01QQQ, `level 5`, `agenda_now` 19/11 (giovedì). Console: 200 percorsi, 80 `failed`, 26 `open`, 52 `done`. 52 percorsi `failed`/`open` aggiornati negli ultimi 20 minuti, letti uno alla volta (`/v1/team/journeys/<need_id>`): 47 letti, 5 in timeout. Orari UTC. `S` = `answer_set` effective/size del verdetto. Nomi dei percorsi = ultime 6 cifre dell'id.

**Cosa si è visto.** Dei 47: 21 `failed`, 17 `open` con solo il GP (in attesa del CUP: la prima risposta del CUP arriva dopo 88-211 s dalla `need.request`), 9 `open` con uno scambio o appena arrivati. Dei 21 `failed`, 20 hanno `wrong_outcome -1` e `S` non vuoto (da 4 a 297): il CUP non prenota mentre il verdetto conta posti nel mondo.

| # | Causa | Percorsi | Agente (proprietario) |
|---|---|---|---|
| 1 | **L'alternativa rilassata ignora la scadenza.** Finito l'insieme in finestra, il CUP offre 3 slot `relaxed=true` fra 8 e 12 giorni dopo (fisiatria 01/12, cardiologia 27/11) per una priorità B (2 giorni). Il cittadino rifiuta tutti e 3 nello stesso secondo con `cancel offer_id=... reason=deadline` e il CUP non risponde più. Attenzione alla versione: i percorsi letti sono del 00:07-00:17 UTC (01:07-01:17 locali), serviti da un CUP precedente alla 1.0.8 (rilasciata alle 01:20 locali). Il 630003 (00:33 UTC, CUP 1.0.10) mostra ancora l'offerta rilassata fuori scadenza (30/11 per una B), ma stavolta il CUP risponde con `partner_unavailable` dopo i rifiuti: il silenzio potrebbe essere già corretto, l'offerta fuori scadenza no. Il codice: `_cup_relaxed` chiama `fitting(priority="P")`, che non ha orizzonte. Inoltre `relaxed=true` arriva al cittadino (MACH-1.2: mai). | 15 failed: 060004, 160004, 180003, 190003, 220003, 240003, 340002, 610002, 640002, 650002, 660002, 710004, 910003, 940003, 000003. Letti per intero: 12; 240003, 940003, 000003 hanno lo stesso schema (7 messaggi, ultimo del cittadino). `S`: 20-47 (fisiatria en), 16 (en), 297 (it), 109-123 (cardiologia it). | CUP (Abed) |
| 2 | **Nessuna offerta utile dai partner.** I log live del CUP (`cup.partners`, `cup.partner_reply`) mostrano per ogni ricerca `asked=6 answered=1..6 usable_offers=0` (7 percorsi visti, `now` 19/11 05:17-08:32, priorità B). Risposte: `cancel reason=no_availability` (Lorenteggio, Giambellino, Lambrate, Corvetto, Nord) e `reason=no_slots_available` (Lambrate specialista, 7 volte). Il CUP chiude con `partner_unavailable` e «Possiamo cercare altri giorni...»; il cittadino risponde «Which offer_id?». Il verdetto dice che nel mondo c'erano slot (`S` 20-297): il CUP chiede solo a 6 partner. | 187 e 191 (open), 720002 (failed), 630003 (open); le ricerche dietro ai percorsi della causa 1 | CUP (Abed): quali partner e con quali criteri. I partner sono agenti di altre squadre. |
| 3 | **Lingua rara che nessuno parla** (`lang=hi`, `lang=am`): il CUP offriva il nostro h3 (parla solo `it`, `ti`) con `relaxed=true`; il cittadino rifiuta con `reason=lang`. Corretto in `main` (commit 87fc8a3, alle 01:23 locali): i tre percorsi sono precedenti. Dopo la correzione serve un partner con quella lingua: `S` = 4 slot in tutta la rete. | 420002, 530002, 720002 | CUP (Abed), già corretto |
| 4 | **`facility_cancelled` dopo la conferma, poi altra offerta.** Ospedale: 190003 (offerta h3 19/11 16:00, `confirm`, `cancel facility_cancelled` dopo 28 s, nessun `hold` sul Ledger nel verdetto). Partner dopo `cross_asst`: 175 (failed), 290002 e 670002 (open): offerta, consenso, `facility_cancelled`, nuova offerta. | 190003, 175, 290002, 670002 | Ospedale (Andrei) per il 190003; per i partner nessuno |
| 5 | **Consultorio: stesso slot riproposto dopo il rifiuto.** 050002: 4 offerte c1 del 17/11, `confirm` sul 10:30, `cancel reason=NO_CAPACITY` (maiuscolo; probabile slot già preso: il 150 aveva le stesse 4 offerte alla stessa ora), subito 3 offerte che includono lo stesso 10:30; seconda `confirm` alle 00:03 senza risposta. | 050002 | Consultorio (Opus; compito di Hapca) |
| 6 | **Consenso `cross_asst` rifiutato.** Offerta Nord s1 20/11, il cittadino rifiuta di condividere i dati. 630002 (failed): il CUP manda `cancel reason=consent_declined` e non offre altro (ultimo messaggio suo). 630003 (open): il CUP propone il nostro s1 del 30/11 (`relaxed`), rifiuto `deadline`, poi `partner_unavailable`. Il posto della nostra ASST dopo il rifiuto esiste solo fuori scadenza: stessa radice della causa 1. | 630002, 630003 | CUP (Abed) |

**Altro.**
- `cancel reason=partner_unavailable` / `no_slots` senza `request_id` o `offer_id` fa rispondere il cittadino «Which offer_id?» (187, 720002).
- Il consultorio funziona: il 150 ha avuto offerta, conferma e ricevuta. Il 050002 è il caso 5.
- I log del CUP (`GET /v1/logs?agent_id=agent%3Aez8cb7j167p2&q=...`) tengono solo gli ultimi secondi: non si può rileggere un percorso già chiuso, si cattura solo dal vivo. Le righe `cup.partners` e `cup.partner_reply` compaiono per un percorso mentre il CUP lo lavora.

### Failed del livello 5, uno per uno

| Percorso | Liv. | Richiesta | `S` | Cosa è successo |
|---|---|---|---|---|
| 060004 | 2 | fisiatria B en | 20/104 | 3 offerte `relaxed` h1 01/12, rifiuto `deadline`, silenzio |
| 160004 | 3 | fisiatria B en | 20/104 | idem |
| 180003 | 3 | cardiologia B it | 110/208 | 3 offerte `relaxed` s1 27/11, rifiuto `deadline` |
| 190003 | 2 | fisiatria B it | 297/520 | offerta h3 19/11 16:00, `facility_cancelled`, poi `relaxed` 01/12, `deadline` |
| 220003 | 2 | fisiatria B en | 46/130 | 3 offerte `relaxed` 01/12, `deadline` |
| 240003, 940003, 000003 | 3, 3, 2 | fisiatria B en | 46/130, 16/78, 47/130 | stesso schema (non letti per intero) |
| 340002, 640002 | 2, 3 | fisiatria B en | 47/130 | `relaxed` 01/12, `deadline` |
| 610002 | 3 | fisiatria B it | 297/442 | `relaxed` 01/12, `deadline` |
| 650002, 660002 | 3, 4 | cardiologia B it | 119/208, 109/208 | `relaxed` 27/11, `deadline` |
| 710004, 910003 | 2, 2 | fisiatria B en | 46/130, 20/104 | `relaxed` 01/12, `deadline` |
| 420002, 530002 | 4, 4 | fisiatria B hi | 4/5 | h3 offerto a `lang=hi`, rifiuto `lang` |
| 720002 | 4 | fisiatria B hi | 4/5 | `partner_unavailable`, `no_slots`, «Which offer_id?» |
| 175 | 2 | cardiologia it | 119/208 | partner: offerta, consenso, `facility_cancelled`, rifiuto del cittadino |
| 630002 | 3 | cardiologia B it | 123/208 | partner Nord s1 20/11, consenso rifiutato, `cancel consent_declined`, silenzio |
| 050002 | 3 | consultorio | 0/0 | caso 5 |

### Partner con 25 ricerche (CUP 1.0.14; 21/11 00:54-01:10 UTC = 01:54-02:10 locali)

Causa 2 chiarita da Opus: `city.find` dà `role=hospital` e il CUP filtrava `role=facility`; dalla 1.0.14 `asked=25`. Cattura dal vivo di `GET /v1/logs?agent_id=agent%3Aez8cb7j167p2&q=cup.partner` (il log tiene pochi secondi; un campione ogni ~20 s perché il pannello della console è nascosto):

| Need (ultime cifre) | Priorità | `now` agenda | asked | answered | usable_offers |
|---|---|---|---|---|---|
| 209 | B | 19/11 18:58 | 25 | 18 | 0 |
| 211 | B | 19/11 23:17 | 25 | 17 | 0 |
| 212 | B | 20/11 10:39 | 25 | 17 | 0 |
| 213 | B | 20/11 17:01 | 25 | 16 | 0 |
| 1910002 | B | 20/11 05:05 | 25 | 16 | 0 |
| 1610003 | B | 20/11 08:59 | 25 | 17 | 0 |
| 1630004 | B | 20/11 12:54 | 25 | 17 | 0 |
| 1590003 | B | 20/11 15:11 | 25 | 15 | 0 |
| 1790002 | B | 20/11 15:16 | 25 | 15 | 0 |
| 1400005 | B | 20/11 16:08 | 25 | 17 | 0 |
| 980006 | B | 20/11 18:13 | 25 | 15 | 0 |

- Risposte dei partner (somma delle 11 ricerche, righe distinte): `no_availability` 39, `facility_unavailable` 7, `policy_unavailable` 3, `temporarily_unavailable` 3, `no_slots_available` 3, `no_slot` 2, `UNAVAILABLE` 2, `NO_CAPACITY` 1 (Isola), una `data.response` (un partner risponde con l'atto sbagliato) e **2 offerte**: Gorla specialista (`agent:h6krzxx6es83`) VIS-CARD lun 23/11 10:30 e 12:00 per il 211, e Gorla ospedale (`agent:m6py14a1ej77`) VIS-FIS mar 24/11 10:30 per il 209. Per una B la scadenza è `now` + 2 giorni (21/11 e 22/11): il CUP le scarta (`usable_offers=0`), scarto giusto.
- Esito: con 25 partner, in 11 ricerche, nessuna offerta utilizzabile e nessuna prenotazione da partner. Rispondono da 15 a 18 su 25, mai tutti. Sono tutte priorità B, tutte con `now` fra 19/11 e 20/11.
- Probabile effetto collaterale: il CUP aspetta i partner prima di rispondere, e la prima risposta al cittadino tarda. I percorsi `open` sono saliti da 26 (00:30 UTC) a 33 (00:54) a 52 (01:10), e i `failed` da 80 a 93 a 90 (la lista della console copre gli ultimi 200 percorsi).
- Ipotesi: un partner che offre fuori scadenza per una B suggerisce che anche gli altri applicano la finestra: la risposta `no_availability` è coerente con il mondo esaurito entro 2 giorni. Il verdetto dei nostri `failed` (`S` fino a 297) non dice dove siano quei posti.

### Livello 6 (dalle 02:15 locali; letto alle 02:10)

Non ancora iniziato: i livelli dei percorsi in console sono 1-5 (3, 44, 84, 54, 15). Scansione dei percorsi `booked`/`done` recenti: 11 letti (livelli 3, 4, 5), tutti con ricevuta e nessun `cancel` dopo; nessun `fault.cancel` né `facility_cancelled` dopo una ricevuta. Il prossimo giro (alle :27 e :47) cerca `facility_cancelled` e `fault.cancel` dopo `booking.receipt` e se il CUP riprenota entro la scadenza.

### Giro delle 02:18 locali (01:18 UTC)

- **Percorsi aggiornati negli ultimi 25 minuti** (stato in console): 1 `booked`, 4 `done`, 20 `failed`, 44 `open`. In 25 minuti hanno concluso la prenotazione 5 percorsi, 20 sono falliti e 44 aspettano. Il taglio per `need` nato dopo le 01:50 locali (00:50 UTC) è parziale: 24 dettagli letti su 69, 8 nati dopo il taglio (tutti `open` al momento della lettura). Il conteggio completo arriva con i giri successivi (cache dei dettagli già letti).
- **Specialist 1.0.3**: `message_count` 183 (era 21 alle 00:00 locali). I suoi log non scrivono le `need.request` (query `need.request` e `rq-` senza risultati sul log dello specialist), quindi cosa risponde ai CUP delle altre ASST non si vede dalla console. Da confrontare il `message_count` nei giri successivi.
- **Livello 6**: ancora nessun `facility_cancelled` o `fault.cancel` dopo una ricevuta nei percorsi letti.
- **Ipotesi per Opus, non verificata**: `open` 26 → 33 → 52 (00:30, 00:54, 01:10 UTC) con i `done` quasi fermi fa pensare a una coda al CUP (ogni ricerca aspetta 25 partner). Da misurare: tempo fra la `need.request` e la prima risposta del CUP nei percorsi nuovi.

## Percorsi falliti e aperti (console, 20/11 23:50)

135 percorsi: 74 done, 25 escalated, 13 failed, 14 open, 3 booked. Dati da `/v1/team/journeys/<need_id>` (messaggi, verdetto, review), `/v1/team/world` (registry e slot veri), `/v1/team/deployments` (esito dei deploy). **Gli orari della console sono UTC: ora locale = UTC+1** (21:52 nella console = 22:52 da noi).

### Falliti (13)

| Percorsi | Dove si ferma | Perché (testo vero) | Stato |
|---|---|---|---|
| 001-007 (7) | GP | GP: "Mi descrivi meglio il disturbo per cui chiedi aiuto?" (20:16-20:22 UTC, 21:16 locali). Il cittadino risponde con un `consent purpose=descrizione_disturbo` o ripete il testo 32 min dopo; il GP non risponde. | Risolto: GP 1.0.2 (22:03 locali) ha il fallback a parole chiave. Percorsi chiusi, non recuperabili. |
| 050, 053, 056 (3) | CUP → specialist | Cardiologia B. Offerta del CUP alle 22:20-22:26 locali (`facility=agent:sh35cbsy287d`), `confirm` del cittadino alle 22:52-22:58 locali, poi silenzio. `no_booking -1`. Lo specialist 1.0.2 era già online dalle 22:34, quindi i deploy falliti (22:03-22:34) non spiegano il silenzio. | **Aperto, causa non nota.** Da riprodurre in locale: `confirm` del cittadino al CUP per uno slot dello specialist, poi cosa fa lo specialist. Si è prenotata una cardiologia più tardi (104, ricevuta ok). |
| 069 | Ospedale → CUP | Fisiatria B, lingua en. Il Ledger ha fatto il `commit` (slot h1 11/11 14:30, `booking_in_pref` +2) ma 1 s dopo il `confirm` il cittadino riceve `cancel offer_id=... reason=facility_cancelled`. Seconda offerta, stessa fine, poi `cancel reason=no_slots`. | Aperto, vedi "Prenotazione riuscita e annullata". |
| 099 | Ospedale → CUP | Fisiatria D. 15 `confirm`, 15 `hold`, 1 solo `commit` ok (primo slot h3 12/11 10:30). Ogni offerta annullata con `facility_cancelled`, poi `no_slots` e "Which offer_id?". Quindici slot restano in hold. | Aperto, come 069. |
| 071 | CUP | Fisiatria B, en. `cancel reason=no_slots`, ma il verdetto dà `answer_set` size 260, effective 170: gli slot validi c'erano. `wrong_outcome -1`. | Aperto, vedi "no_slots falso". |

### Aperti (14)

- 13 percorsi (091, 093, 094, 100, 106, 109, 110, 111, 112, 113, 116, 118 e 690002) finiscono con `cancel reason=no_slots Non ho trovato orari confermabili...` dal CUP e il cittadino risponde "Which offer_id?". Fisiatria (VIS-FIS, B e D, it e en) dalle 22:16; il 118 è cardiologia B. Alcuni ritentano dopo ~16 min con un nuovo `need.request`.
- 105: primo messaggio al consultorio (22:46 UTC, 23:46 locali), nessuna risposta. **Il consultorio non è online**: `/v1/team/deployments` dà 1.0.0 `failed`, stadio 4 `health`, dettaglio `p99`; `city status` dice `deployed: true` ma non vale. Il codice in locale risponde (offre lo slot con il testo vero del 105, `tools/test_facility.py` verde). Ogni cittadino che scrive al consultorio costa -4 (porta d'ingresso vuota). Da fare: ridurre il file ai soli codice del consultorio e rilanciare il deploy.
- 3 booked (103, 104, 114): ricevuta consegnata, in attesa di check-in. Normale.

### Emergenze (25)

Tutte vere: ogni primo messaggio dice "dolore al petto forte da stamattina", il GP risponde una sola volta `escalate.emergency reason=red_flag`. Nessuna escalation sbagliata.

### Prenotazione riuscita e annullata (069, 099)

Nei percorsi 069 e 099 il Ledger conferma il `commit` e il cittadino riceve anche `cancel ... facility_cancelled`. In una prova locale con il City SDK e il Ledger simulato, i turni concorrenti di `_finish_booking` e `held` hanno mandato due `commit` per lo stesso hold. Il primo viene accettato, il secondo risponde `DUPLICATE`. L'ospedale invia al CUP sia la ricevuta sia l'annullamento. La causa dei due casi in Arena resta da confermare. Alberto verifica la correlazione per hold e corregge il doppio commit e l'annullamento dopo `committed`.

### no_slots falso

Dalle 22:16 UTC ogni richiesta di fisiatria riceve `no_slots`, ma il verdetto del 071 dà `answer_set` 170 effettivi su 260.

**Ipotesi "la tabella `_DOCTORS` non corrisponde ai medici veri": smentita.** Il registry vero (`/v1/team/world`, `registry.doctors`) coincide con `_DOCTORS` di CUP e ospedale: h1 f it,en lun-mer; h2 m it mer-ven; h3 m it,ti mar,gio; s1 m it,en lun,mer,ven; s2 f it mar,gio; c1 f it,en lun-ven (`ti` è la lingua rara, coperta da `*`). Nessun medico mancante.

Righe vere (formato dello slot, id slot = `W01QQQ-asst-bicocca-<medico>-<AAAAMMGG>-<HHMM>`):
- `slot_id=W01QQQ-asst-bicocca-h1-20261102-1030 capacity=1 facility=agent:bb01ggxymm05 doctor_id=asst-bicocca-h1 procedure=VIS-FIS agenda_day=mon agenda_date=2026-11-02T10:30:00.000Z urgent_reserve=false`
- registry: `doctor_id=asst-bicocca-h1 gender=f languages=it,en days=mon,tue,wed facility=agent:bb01ggxymm05`
- registry: `doctor_id=asst-bicocca-h3 gender=m languages=it,ti days=tue,thu`

Offerta reale ogni settimana (modello di 5 giorni): VIS-FIS 40 slot (h1 15, h2 15, h3 10), 8 con `urgent_reserve`, `capacity=1`. Scadenze del kit: B entro 2 giorni, D entro 5 (le stesse del CUP). Quindi: in inglese c'è solo h1 (lun-mer): un B in inglese di giovedì ha 2 giorni senza slot di h1, risposta legittima del filtro. Ogni slot tenuto e mai rilasciato (069: 1, 099: 15 hold) è tolto per sempre agli altri.

Cause ancora in gioco, da provare con un test: (1) l'offerta fisiatria è piccola (~8 slot per giorno feriale, nessuno nel weekend) e l'agenda corre; (2) hold che non si liberano dopo un `cancel` di 069/099; (3) non c'è alternativa rilassata quando non ci sono orari (kit: "S vuoto e alternativa rilassata offerta" vale 0, nessuna prenotazione con S non vuoto vale -1); (4) `S` si calcola alla nascita del need e il cittadino arriva al CUP ~16 ore di agenda dopo.

Inoltre `cancel reason=no_slots` senza `request_id` o `offer_id` fa rispondere il cittadino "Which offer_id?": aggiungere una frase chiara con il passo successivo.

### Livello

Elenco `/v1/team/journeys`: tutti `level 1`. Nel dettaglio e nel verdetto i percorsi chiusi dalle ~21:15 UTC sono `level 2` (045, 050, 099...), quelli fino al 040 sono `level 1`. `/v1/team/wave`: wave W01QQQ numero 1, livello 1, `rate 60`, `mode standing`, `scores_hidden true`. Il livello sembra assegnato dalla città al verdetto, non dalla squadra; nessun percorso L3 visto.

## Aperti
- **Specialist e rinnovo P1**: lo specialist trasforma anche `PRESCRIPTION_EXPIRED` in `facility_cancelled`. Per quel percorso il CUP dipende da un segnale di scadenza del Ledger abbinabile alla ricetta. (Ismail)
- **Ospedale e consultorio, P2**: il controllo usa il vecchio formato degli ID e non riconosce alcuni agenti esterni; se manca il riferimento del consenso il codice può costruirne uno; il consultorio può riproporre lo slot appena annullato. (Alberto)
- **Specialist, follow-up**: la ricetta di controllo (`prescribe ... follow_up_of=`) non è implementata. (Ismail)
- **Deploy dello specialist**: due volte `ERROR` della città, "agent ingress route did not become ready in time (last 404, version '-')". Conformance tutta PASS. Chiesto ai mentor su Discord.
- **Messaggi persi durante i rollout**: i percorsi 32, 33, 34, 38 non hanno avuto risposta dal GP mentre cambiava versione (log della città in `503 DRAINING`). In locale il GP risponde bene.
- **LLM di Abed non su GitHub**: ha scritto di aver collegato Gemma, ma in repo non c'è `city.llm`.
- **city-cli su Windows**: si rompe stampando ✓ (`UnicodeEncodeError cp1252`). Soluzione: `PYTHONIOENCODING=utf-8`. Il primo `city deploy gp` (21:38) è rimasto senza output per 7 minuti ed è stato fermato.

## Risolti
- **CUP, rinnovo P1**: il rifiuto della struttura provocava una nuova offerta con la ricetta scaduta. Ora chiede il rinnovo una volta e rilegge sul Ledger il numero sostitutivo. (`tools/test_cup_recovery.py`, testato in locale)
- **CUP, consenso con testo iniziale**: l'atto `consent` veniva letto solo a inizio messaggio. Ora viene riconosciuto anche dopo una frase, con scopo e mittente verificati. (`tools/test_cup_recovery.py`, testato in locale)
- **CUP, slot partner ritirato durante il consenso**: il CUP ignorava il ritiro prima della conferma. Ora abbina mittente e identificativi, invalida l'offerta e ripropone gli orari ancora disponibili. (`tools/test_cup_recovery.py`, testato in locale)
- **GP, DUPLICATE annunciato senza verifica** e **rinnovo non annunciato** se c'era già una ricetta nella pratica: ora rilegge la ricetta dopo DUPLICATE e controlla per numero di ricetta. (review 22:15, test in `tools/test_fix.py`)
- **GP, red flag nascoste del livello 8**: ora legge `red_flags` dalla tabella di protocollo del `world`.
- **Specialist**: check-in con `ledger_ref`; un solo referto anche con due risposte concorrenti al consenso.
- **CUP, medico sconosciuto e lingua**: un medico fuori dalla tabella si accetta solo per cittadini che parlano italiano e senza preferenza di genere.
- **CUP, id medico fuori dalla tabella** (`D-3`): ogni orario veniva scartato, anche nella propria ASST. (PR #8, `tools/test_cup_medici.py`)
- **Messaggi "curt"**: la review dava 0 su proattività al GP. (PR #7)
- **GP fermo sul testo libero** (11 percorsi su 12): la tabella `_KEYWORDS` dell'esempio era stata tolta. Ripristinato il fallback a parole chiave.
- **Specialist senza consenso del referto**: ora chiede `report_sharing`, usa solo un consenso con quello scopo, archiviazione senza condivisione se il cittadino rifiuta.
- **`main` con gli ID vecchi**: sistemato dalla PR #5.
