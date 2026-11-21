
# Problemi

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
