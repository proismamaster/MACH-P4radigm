
# Problemi

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
