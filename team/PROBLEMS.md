
# Problemi

## Percorsi falliti e aperti (console, 20/11 23:50)

135 percorsi: 74 done, 25 escalated, 13 failed, 14 open, 3 booked. Dati da `/v1/team/journeys/<need_id>` (messaggi, verdetto, review).

### Falliti (13)

| Percorsi | Dove si ferma | Perché (testo vero) | Stato |
|---|---|---|---|
| 001-007 (7) | GP | GP: "Mi descrivi meglio il disturbo per cui chiedi aiuto?". Il cittadino risponde con un `consent purpose=descrizione_disturbo` o ripete il testo 32 min dopo; il GP non risponde. | Risolto: GP 1.0.2 (22:03) ha il fallback a parole chiave. Percorsi chiusi, non recuperabili. |
| 050, 053, 056 (3) | CUP → specialist | Cardiologia B. Offerta del CUP 21:20-21:26 (`facility=agent:sh35cbsy287d`), `confirm` del cittadino 21:52-21:58, poi silenzio. Lo specialist è online solo dalle 22:34 (1.0.2): prima la conferma è andata a un agente non pronto. `no_booking -1`. | Causa esterna al codice. Resta il rischio: il CUP non ha un recupero se la struttura tace. |
| 069 | Ospedale → CUP | Fisiatria B, lingua en. Il Ledger ha fatto il `commit` (slot h1 11/11 14:30, `booking_in_pref` +2) ma 1 s dopo il `confirm` il cittadino riceve `cancel offer_id=... reason=facility_cancelled`. Seconda offerta, stessa fine, poi `cancel reason=no_slots`. | Aperto, vedi "Prenotazione riuscita e annullata". |
| 099 | Ospedale → CUP | Fisiatria D. 15 `confirm`, 15 `hold`, 1 solo `commit` ok (primo slot h3 12/11 10:30). Ogni offerta annullata con `facility_cancelled`, poi `no_slots` e "Which offer_id?". Quindici slot restano in hold. | Aperto, come 069. |
| 071 | CUP | Fisiatria B, en. `cancel reason=no_slots`, ma il verdetto dà `answer_set` size 260, effective 170: gli slot validi c'erano. `wrong_outcome -1`. | Aperto, vedi "no_slots falso". |

### Aperti (14)

- 13 percorsi (091, 093, 094, 100, 106, 109, 110, 111, 112, 113, 116, 118 e 690002) finiscono con `cancel reason=no_slots Non ho trovato orari confermabili...` dal CUP e il cittadino risponde "Which offer_id?". Fisiatria (VIS-FIS, B e D, it e en) dalle 22:16; il 118 è cardiologia B. Alcuni ritentano dopo ~16 min con un nuovo `need.request`.
- 105: primo messaggio al consultorio (22:46), nessuna risposta. Il consultorio è ancora 1.0.0 con il file da 1563 righe e `message_count` 0.
- 3 booked (103, 104, 114): ricevuta consegnata, in attesa di check-in. Normale.

### Emergenze (25)

Tutte vere: ogni primo messaggio dice "dolore al petto forte da stamattina", il GP risponde una sola volta `escalate.emergency reason=red_flag`. Nessuna escalation sbagliata.

### Prenotazione riuscita e annullata (069, 099)

Il Ledger conferma il `commit` ma il cittadino riceve `cancel ... facility_cancelled`. Il CUP traduce ogni `cancel` della struttura in `facility_cancelled` (`booking_centre/agent/agent.py:759-767`) e perde il codice reale. Ipotesi forte, da provare con un test: l'ospedale manda due `commit` per lo stesso hold (il turno di `_finish_booking` e il turno del messaggio `held` del Ledger si accavallano, `_our_commit` guarda una storia non ancora aggiornata); il secondo `commit` viene rifiutato, `_on_refused` (`hospital/agent/agent.py:1155`) manda `cancel` al CUP e il CUP lo gira al cittadino. Conseguenze: prenotazione fantasma sul Ledger, nuove offerte, hold mai rilasciati. Da fare: test con Ledger finto che risponde `held` due volte; in `_on_refused` non annullare se per quell'hold c'è già un `committed` nella storia. File dell'ospedale: Alberto.

### no_slots falso

Dalle 22:16 ogni richiesta di fisiatria riceve `no_slots`, ma il verdetto del 071 dà 170 slot validi. Sospetti, in ordine: `fitting()` e la tabella `_DOCTORS` dell'ospedale (lingua, giorni, orizzonte per priorità) scartano tutto quando `agenda_now` avanza (alle 23:50 è 12/11 21:56, passa 1 ora di agenda al minuto); la lettura delle pagine del `world` (`_answer_search` torna senza rispondere quando chiede la pagina successiva); gli hold del 099 sottraggono slot. Da fare: test con righe `world` e `now` reali. Inoltre `cancel reason=no_slots` senza `request_id` o `offer_id` fa rispondere il cittadino "Which offer_id?": aggiungere `request_id`.

### Livello

Elenco `/v1/team/journeys`: tutti `level 1`. Nel dettaglio e nel verdetto i percorsi chiusi dalle ~21:15 sono `level 2` (045, 050, 099...), quelli fino al 040 sono `level 1`. `/v1/team/wave`: wave W01QQQ numero 1, livello 1, `rate 60`, `mode standing`, `scores_hidden true`. Il livello sembra assegnato dalla città al verdetto, non dalla squadra; nessun percorso L3 visto.

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
