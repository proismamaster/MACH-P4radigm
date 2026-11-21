# Journal (la voce più recente in alto)

## 2026-11-21 04:20 — Alberto (Hhapca, con Claude) — Consultorio 1.0.7 e correzioni del CUP in main

**Fatto**
- Consultorio online 1.0.7 (tutto in `main`, fc4493d): trust ring in modalità sicura (blocca solo chi non è nel ring né in `city.find` E manda `facility=` altrui o istruzioni, dalle 10:00), niente lettura della casella senza `need_id`, `need.request` senza criteri non è una ricerca (conformance), scadenze B/D in giorni di agenda, riprova del hold una volta su `EXPIRED`/`STALE_FENCE`, `rules` riletto per P2, codici del Ledger al CUP (`cancel reason=<minuscolo>` / `hold_refused ledger_code=`), rebook dopo `fault.cancel`, idempotenza di confirm e request_id.
- CUP: 5 correzioni unite in `main` (6012ae3), NON pubblicate (online 1.0.20): orologio d'agenda senza weekend, catalogo fino a 20 pagine / ~60 s, anticipo minimo 1 ora con le 4 ore come preferenza + scadenza ricontrollata al confirm + `capacity=0` dei partner, cancel sempre con `offer_id` o frase semplice e niente date tardive dopo un rifiuto per `deadline`, giorni scritti a parole e rifiuti `day`/`gender` (test: `tools/test_cup_*.py`, 13 file verdi insieme).
- `tools/test_facility.py`: prove per ruolo (consultorio C, E, H; ospedale A, B, D, F, G, I, E, H).

**Dati (console, 200 percorsi, ~04:00 locali; letti dal sito con `/v1/team/journeys/<need_id>`)**
- 6 done, 8 escalated, 95 failed, 91 open. GP: 102 `protocol_match +2`, risponde sempre. CUP: 70 `no_booking -1`, 6 `no_alternative -1`, 2 `false_attribute -2`.
- Rifiuti dei cittadini: `deadline` 103, `past` 24, `gender` 14, `day` 8. Giorni e genere sono scritti a parole, mai in `days=`.
- Dopo il confirm del cittadino (61 percorsi): 2 ricevute, 21 `facility_cancelled` (mediana 570 s), 34 silenzio, 4 cancel del consultorio (`EXPIRED` x3, `STALE_FENCE` x1).

**Problemi**
- Non confermata la causa dei confirm senza ricevuta per ospedale e specialist: servono i messaggi del Ledger (`held`, `refused ... code=`), che gli export non hanno. `/v1/team/agents/<id>/messages` esiste ma non rispondeva (sito sovraccarico, 504); `/v1/logs` dava `DRAINING`.
- Elenco completo del ring (MACH-1.2) non nella repo: in `_RING` del consultorio 18 id.

**Prossimo passo**
- Pubblicare il CUP nella finestra 04:30-05:00 (entro le 05:30), con `city rollback agent:ez8cb7j167p2 --to 1.0.20` pronto; controllare `cup.find ... kept=` e i percorsi.
- Alle 10:00: unire e pubblicare la #86 (impostori del CUP, si unisce senza conflitti con questi merge).
- Riprovare a leggere i messaggi del Ledger quando il sito risponde; se `EXPIRED`/`STALE_FENCE` ci sono anche in ospedale e specialist, portare la riprova.

## 2026-11-21 03:55 — Andrei (Claude) — Livello 8: cittadini ostili e injection verificati

**Fatto**
- "Nuovo piano degli arrivi" (03:36) è solo la curva degli arrivi rifatta (terza volta stanotte): nessun cambio di protocollo, nessuna modifica al codice.
- `tools/test_l8_ostili.py` (nuovo, 10 controlli): GP (injection "ignora il protocollo", cittadino ostile, "non chiamare l'emergenza" con dolore al petto, dati di un altro paziente), CUP (injection "fuori scadenza + indirizzo del medico", ostile, dati per un altro cittadino, confirm di un'offerta inventata), ospedale (confirm senza consent_ref con injection, cittadino che chiede dati altrui). Tutti verdi sul codice online: nessun deploy.

**Prossimo passo**
- Livello 8 alle 04:15: guardare in console escalation, review e righe audit.

## 2026-11-21 03:40 — Andrei (Claude) — CUP: livello 8 verificato, messaggi al cittadino con il passo successivo

**Fatto**
- Livello 8 (regole P1-P3): il CUP non legge `rules`, ma P2 chiede sempre il consenso `cross_asst`, P3 esclude sempre `urgent_reserve` per B/D/P, P1 si basa su `prescription ... state=expired` del Ledger e su `PRESCRIPTION_EXPIRED` (rinnovo). Contesa del livello 7: dopo un cancel della struttura il CUP riprenota (`_cup_cancel` -> `_advance_alone`). Nessuna modifica: già coperto dai test di Abed.
- Review di proattività (-1 per messaggi "freddi"): 4 messaggi al cittadino erano solo token. Ora hanno una frase con il passo successivo: ricevuta (conservare booking_id/ledger_ref per il check-in), rifiuto della struttura (cerco un altro orario), lista d'attesa (cosa succede), offerte (rispondere con l'orario o chiedere altre date); `no_slots` dice cosa indicare. Tutto al "lei". Token invariati.
- Test: `tools/test_cup_cortesia.py` (nuovo, 4 controlli falliscono su main). Verdi anche cortesia, scadenze, l5_vincoli, medici, recovery, test_fix.

**Prossimo passo**
- Deploy CUP, poi console: review di proattività del CUP sui nuovi percorsi.

## 2026-11-21 03:25 — Andrei (Claude) — Scadenze in giorni di agenda (CUP e ospedale)

**Fatto**
- Il kit (e19-rules.md, ADR-124): sabato e domenica di agenda non esistono, dopo il venerdì si riparte dal lunedì. B = 2 giorni di agenda, D = 5. Il codice (dall'esempio del kit, quindi probabilmente in tutte le squadre) usava `now + timedelta(days=N)`: di giovedì B finiva sabato e scartava ogni slot di lunedì; di venerdì non restava quasi niente.
- Effetto: fisiatria B in inglese (solo h1, lun-mer) di giovedì/venerdì senza nessuno slot "in finestra", il CUP offriva lunedì come `relaxed=true` mescolato a slot oltre la scadenza, rifiutati con `reason=deadline`. Il verdetto contava `S` 20-47: i percorsi falliti della causa 1 in PROBLEMS.
- Correzione: `_agenda_horizon(now, days)` conta solo i giorni feriali; usata nel CUP (`fitting`, offerte dei partner) e nell'ospedale (`fitting`, risposte alle ricerche dei CUP).
- Test: `tools/test_cup_scadenze.py` (nuovo, 3 casi falliscono su main, controllo di metà settimana invariato) e prova I in `tools/test_facility.py`. Verdi anche test_cup_l5_vincoli, test_cup_medici, test_cup_recovery, test_fix e le prove dell'ospedale.

**Problemi**
- Consultorio e specialist hanno lo stesso calcolo (proprietari Hapca e Ismail): avvisati.
- Il giudice conta la scadenza così? Il kit lo dice; da verificare in console sui prossimi B di giovedì/venerdì.

**Prossimo passo**
- Deploy CUP e ospedale, poi guardare in console percorsi B di fine settimana.

## 2026-11-21 03:20 — Andrei (Claude) — Ospedale: livelli 6, 7 e 8 portati dal consultorio

**Fatto**
- L6: `fault.cancel` (o `hold.expired`, solo da Ledger o città) di una nostra prenotazione → a chi ha prenotato UN messaggio: `cancel reason=facility_cancelled booking_id=...` e sotto fino a 3 offerte, prima lo stesso medico, mai lo slot annullato; per un CUP con il suo `request_id` e i filtri lingua/genere della sua ricerca. Annullo ripetuto: nessun secondo messaggio. Codice di Hapca (`_rebook` e collegati), procedura di default VIS-FIS.
- L7: stessa `request_id` = stesse offerte parola per parola, anche se il Ledger cambia; stesso confirm = stessa ricevuta reinviata una volta, mai un secondo hold (si somma a #46).
- L8: rifiuti al CUP `cancel reason=prescription_expired|consent_missing|no_capacity` in minuscolo, gli altri `hold_refused ... ledger_code=<CODICE>`; P2 rilegge `rules` sul confirm di un CUP esterno (`_fresh_rules`).
- La correzione della conformance (#67) resta: nessuna risposta ai `need.request` senza `request_id`/`procedure`/`service_type` (prova E verde).
- Test: prove F (L6) e G (L8) nuove; A e B aggiornate a L7/L8. Su `main` fallivano 18 controlli nuovi o aggiornati; qui A, B, D, E, F, G verdi 5 volte su 5, C fallisce come atteso. `test_fix.py` verde, card valida.

**Problemi**
- Il formato dell'annullo (`fault.cancel`, `hold.expired`) non è nel kit: letto in modo largo come nel consultorio. Da verificare in console al primo annullo vero.
- `tools/test_mach12_struttura.py` sull'ospedale: 8 controlli MACH-1.2 (giorni/orari, offerte rilassate) falliscono come prima. È lavoro di livello 5, non in questo compito.

**Prossimo passo**
- Deploy dell'ospedale dopo la 1.0.1 (Opus), poi guardare in console un percorso con `fault.cancel`.
## 2026-11-21 02:45 — Andrei (Claude) — Ospedale: la causa vera di custody.ack

**Fatto**
- Dopo #67 la conformance falliva ancora. Causa: `main()` chiama `city.history(need_id=message.need_id)` anche senza need_id; le prove della suite non ne hanno, e senza need_id l'SDK legge TUTTA la casella (fino a 5 pagine firmate da 200, una dopo l'altra, `city_sdk/http.py`). L'ospedale ha ~1400 messaggi: il turno dura secondi e `custody.ack` smette di aspettare il rinnovo dopo 5 s.
- GP e CUP escono prima della lettura se manca need_id (per questo passano sempre); consultorio e specialist leggono tutta la casella ma è piccola (1 pagina). Non c'entra la dimensione del file.
- Correzione: `if not message.need_id: return` prima di `history`, come GP e CUP. Test: prova H (casella che costa 3 s letta senza need_id): fallisce su `main`, verde qui. A, B, D, E, H verdi; C come atteso; test_fix verde; card valida.

**Problemi**
- Consultorio e specialist hanno lo stesso schema: passeranno sempre meno con la casella che cresce. Avvisati Hapca e Ismail.

**Prossimo passo**
- Deploy della 1.0.1 con questa correzione (Opus), poi la PR #70 (livelli 6-8).

## 2026-11-21 03:00 — Ismail (Opus) — Livelli 5-6: city.find, orologio, pagine, riprenotazione

**Fatto (online)**
- CUP 1.0.9-1.0.18: h3 solo per `ti` (142); log `cup.partners`/`cup.partner_reply`/`cup.find` (GET /v1/logs?agent_id=agent%3Aez8cb7j167p2&q=cup.); **city.find restituisce role=hospital, non facility: il filtro scartava tutte le 26 strutture** (ora 25 partner); orologio dell'agenda = ultimo agenda_now + tempo reale x60; dopo aver chiesto una pagina del mondo aspetta nello stesso turno (prima il caso restava fermo 3-5 minuti); livello 6: cancel della struttura dopo la ricevuta riapre il caso e riprenota (prima era ignorato); `hold_refused` e codici minuscoli MACH-1.2. PR #42 di Abed (vincoli L5) unita.
- Specialist 1.0.3: risponde alle need.request dei CUP delle altre ASST (prima le ignorava). Test: tools/test_specialist_ricerca.py.
- Consultorio 1.0.3: MACH-1.2 e livelli 6-7 di Hapca (PR #44, #61). Il livello 8 di Hapca è su main, da pubblicare (1.0.4).

**Problemi**
- Ospedale fermo alla 1.0.0: conformance `custody.ack ... got renews=[] acks=[]` anche dopo la PR #67 di Andrei (sonde need.request senza request_id). Il consultorio, simile e più grande, passa.
- Al livello 4-5 i partner rispondono quasi sempre `no_availability`: scarsità vera, non bug.
- Errore mio: PR #43 ha messo su main una riga che non compilava (test fallito nascosto da `| tail -1`). Riparato con #45 prima di qualsiasi deploy. Regola: controllare l'exit code dei test, mai dietro una pipe.

**Prossimo passo**
- Andrei: causa vera di custody.ack nell'ospedale, poi livelli 6-8 nell'ospedale. Hapca: TRUST RING (impostori dalle 10:00).

## 2026-11-21 02:40 — Andrei (Claude) — Ospedale: perché la 1.0.1 non passa la conformance

**Fatto**
- Letta la suite della città (`city_conform`, nel Python di city-cli): le prove sono `need.request` con corpo `service=lab summary=visit` da `agent:t05/osp-x`, un agente che esiste solo nella suite. La suite conta come effetto ogni messaggio che l'agente *manda* (`sent`), anche se arriva durante la richiesta successiva; `custody.ack` aspetta il rinnovo del lease al massimo 5 s, e l'harness rinnova solo a brain finito.
- Causa: `_is_search` dell'ospedale prendeva ogni `need.request` da un agente per una ricerca di un CUP e rispondeva `cancel ... reason=procedure_missing` al mittente della prova. Effetto in più → `invoke.signature: effect` e `invoke.idempotency: conflict effect`; invio a un agente inesistente lento → `custody.ack` renews=[] acks=[]. Il consultorio scrive solo al Ledger (non contato in `sent`), per questo passa anche con 1744 righe.
- Correzione (`asst/hospital/agent/agent.py`, +5 righe): un `need.request` è una ricerca solo se ha `request_id`, `procedure` o `service_type`. Le ricerche vere (nostro CUP, formato del kit) li hanno sempre.
- Test: prova E in `tools/test_facility.py` (prove della suite con `city_conform.world.good_agent` + Ledger lento 1 s): su `main` 4 controlli falliscono, qui tutti verdi. Prove A, B, D verdi; C fallisce come atteso.

**Problemi**
- In locale `custody.ack` fallisce anche per l'agente di riferimento del kit: la suite in processo non aspetta il rinnovo. Conferma vera solo con il deploy.

**Prossimo passo**
- Deploy dell'ospedale (Opus sul PC di Ismail) e `city --json status agent:bb01ggxymm05`.

## 2026-11-21 01:35 — Andrei (Claude) — Ospedale: un solo commit per hold, nessun cancel dopo la ricevuta

**Fatto**
- Riprodotto 069/099 in `tools/test_facility.py`, prova D: Ledger che mette la risposta subito nella cronologia e apre anche un turno suo, cronologia con 20 ms di ritardo. Sul codice di `main` l'ospedale manda due `commit` per H-1, poi `booking.receipt` e subito `cancel ... reason=facility_cancelled` (stessa sequenza dell'Arena). 7 controlli su 9 falliscono.
- Causa: il turno del `confirm` (`_finish_booking` -> `_on_held`) e il turno della riga `held` leggono il caso prima che l'altro abbia scritto il `commit`, quindi `_our_commit` è falso in tutti e due. Il secondo `commit` è rifiutato e `_on_refused` manda il cancel.
- Correzione minima in `asst/hospital/agent/agent.py`: `_claim()` in memoria prima del primo `await` (un `hold` per slot e need, un `commit` per hold, una ricevuta per booking); `_on_refused` non annulla dopo una ricevuta valida né su `DUPLICATE` di un commit. Il file resta solo ospedale.
- Prove A, B, D verdi 10 volte su 10; C fallisce come atteso (file ridotto). `test_fix.py` verde. `city card validate hospital` ok.

**Problemi**
- La guardia vale per un processo: con più repliche dello stesso agente due turni potrebbero ancora finire su processi diversi.
- 099 ha anche 15 `hold` per 15 `confirm`: con questa correzione due confirm uguali in parallelo fanno un solo hold, ma i confirm del 099 erano su offerte diverse. Da riguardare in console dopo il rilascio.

**Prossimo passo**
- Review e rilascio dell'ospedale (Claude sul PC di Ismail), poi verificare in console un percorso fisiatria con una sola ricevuta e nessun cancel.
## 2026-11-21 01:28 — Abed — Vincoli combinati e alternative locali del CUP

**Fatto**
- Il CUP verifica insieme lingua, genere, giorno e finestra di priorità nelle offerte locali e dei partner. Legge `agenda_date` e `agenda_day` del Ledger e usa gli slot più recenti per pagina.
- Se l'insieme è vuoto, prova un giorno diverso entro la stessa scadenza. Se serve proporre una data più lontana, la presenta come alternativa e conserva lingua, genere e regola della riserva urgente.
- Nel caso 1630002, riprodotto con la frase di rifiuto vista in console, il CUP cerca un nuovo posto nella propria ASST. Il rifiuto resta valido nella pratica anche su messaggi ripetuti o consenso tardivo.

**Problemi**
- Il caso 183 fornisce il testo reale di una richiesta L5. I vincoli combinati e l'aggiornamento delle pagine sono verificati con il Ledger simulato.

**Prossimo passo**
- Review di Ismail e verifica in Arena dei vincoli combinati e del rifiuto cross-ASST dopo il rilascio.

## 2026-11-21 01:45 — Ismail (Opus) — Livello 4: partner dell'anello, alternativa rilassata, rifiuti del cittadino

**Fatto**
- CUP 1.0.3-1.0.7 (PR #19, #21, #22, #26, #27, #30): legge le offerte dei partner nel formato comune (senza `expiry`/`agenda_day`, `doctor_lang` per l'h3 con lingua rara, date MACH-1.1 senza fuso lette come UTC), manda `cross_asst_consent_ref`, scrive prima alle 6 strutture dell'anello pubblicate su Discord (la lingua del cittadino in testa) e poi a `city.find`, aspetta i partner 20 s.
- Insieme vuoto: alternativa rilassata solo sui giorni, mai sulla lingua (172: il cittadino inglese rifiuta l'h3).
- Rifiuto del cittadino (`cancel offer_id=... reason=deadline|language`): chiude l'offerta e il CUP riparte. Prima restava in silenzio e il percorso falliva (165, 166).
- Consultorio 1.0.1 (PR #20): `doctor_lang`/`doctor_gender` nelle offerte ai CUP esterni, filtro `lang=`/`gender_preference=`, accetta `cross_asst_consent_ref`.
- Ospedale: file ridotto al suo ruolo (PR #25, 1588 -> 1400 righe). Deploy 1.0.1 fallito 3 volte in conformance (`custody.ack`, `invoke.signature`), online resta 1.0.0.

**Problemi**
- La console mostra solo i messaggi col cittadino: non si vede se i partner rispondono. Verificare dai percorsi successivi se arrivano offerte con `Rete ASST.`.
- `test_facility.py` sui file ridotti: le prove dell'altro ruolo falliscono (atteso). Hospital: fallisce la prova C; consultorio: A e B.

**Prossimo passo**
- Verificare in console un percorso con offerta di un partner e uno con alternativa rilassata.
- GP 1.0.3 e ospedale 1.0.1 ancora da pubblicare.

## 2026-11-21 01:06 — Abed — Giorni richiesti e rifiuto delle offerte cross-ASST

**Fatto**
- Il CUP invia ai partner solo i giorni feriali indicati dal cittadino, nel formato `days=mon/wed`. Le regressioni locali verificano normalizzazione, assenza del campo e contenuto della richiesta.
- Il CUP mantiene l'ordine della cronologia e cerca un'alternativa quando il cittadino rifiuta l'ultimo slot. Le prove con lo SDK coprono anche una conferma tardiva e un invio che il Relay non ha ancora mostrato.

**Problemi**
- Il doppio commit in ospedale è riprodotto in locale. La causa dei percorsi 069 e 099 va confermata in Arena.

**Prossimo passo**
- Dopo il rilascio, verificare in Arena una ricerca cross-ASST con giorni richiesti e un rifiuto seguito da un'offerta valida.

## 2026-11-20 22:53 — Abed — Rinnovo P1 e disponibilità cross-ASST del CUP

**Fatto**
- Il CUP chiede al cittadino di rinnovare la ricetta scaduta con il GP e riprende la ricerca solo quando il Ledger verifica il nuovo numero.
- Il CUP riconosce il consenso cross-ASST dopo una frase e ritira lo slot annullato dal partner prima di inoltrare una conferma.
- Cinque regressioni falliscono sul codice precedente alla PR e passano con la correzione. Verificate anche le suite di squadra e la card del CUP.

**Problemi**
- Lo specialist inoltra la scadenza come cancellazione generica. Il CUP può riconoscere quel caso se il Ledger gli consegna una risposta abbinabile alla ricetta.

**Prossimo passo**
- Rileggere la PR. In Arena verificare prima un percorso cross-ASST e poi il rinnovo P1 fino alla ricevuta.

## 2026-11-20 22:36 — Ismail — Specialist online, file ridotti

**Fatto**
- Specialist 1.0.2 online alle 22:34 (consenso `report_sharing`, referto unico, `ledger_ref`), dopo 3 fallimenti con il file da 1219 righe. Ridotto a 667 righe su consiglio del mentor.
- GP e CUP ridotti con lo stesso metodo; confronto completo/ridotto identico (CUP 8 scenari, GP 6, specialist 6). PR #10 unita.
- Deploy del CUP (cross-ASST + id medico) partito alle 22:35.

**Problemi**
- Hospital e consultorio hanno ancora il file completo (1563 righe): da ridurre prima del prossimo deploy (Alberto o Ismail).

**Prossimo passo**
- CUP online prima del livello 4, poi GP 1.0.3 (messaggi cortesi, red flag del world, file ridotto).

## 2026-11-20 22:12 — Ismail — GP online, PR #7 e #8 unite

**Fatto**
- GP 1.0.2 pubblicato alle 22:03 (merge completo con `main`). Percorsi 08 e 10: ricetta VIS-FIS B, `citizen.gp.protocol_match +2`.
- PR #7: messaggi al cittadino cortesi e con il passo successivo (la review dava 0 su proattività, messaggio "curt").
- PR #8 (CUP cross-ASST di Abed) corretta e unita: il CUP scartava ogni orario con id medico fuori dalla tabella (`D-3` dell'esempio del kit), anche nella propria ASST. Test `tools/test_cup_medici.py`.

**Problemi**
- Deploy dello specialist fallito alle 22:07 per la piattaforma ("agent ingress route did not become ready in time"), rilanciato alle 22:09.
- I log della città rispondevano `503 DRAINING`. I percorsi 32, 33, 34, 38 non hanno avuto risposta durante i cambi di versione del GP: in locale il GP risponde bene, si aspetta il nuovo invio del cittadino.

**Prossimo passo**
- Specialist online prima delle 23:00, CUP 23:30-00:00, poi GP con messaggi cortesi.

## 2026-11-20 22:02 — Abed — Ricerca cross-ASST dal CUP

**Fatto**
- Riprodotto il blocco dopo l'ultima pagina dell'agenda locale. Il CUP cerca ora strutture compatibili nell'Index e invia loro solo i criteri di disponibilità. Dopo che il cittadino sceglie un orario della rete, chiede il consenso `cross_asst` prima di inoltrare i dati alla struttura scelta.
- Verificati sui mock SDK la ricerca, l'abbinamento di offerta e richiesta, il consenso valido, il rifiuto, il consenso per uno scopo diverso e la ricevuta legata alla scelta. Passano anche le regressioni locali e i test di squadra.

**Problemi**
- `world` espone il registro della propria ASST. Per gli slot remoti il CUP controlla mittente, richiesta e vincoli dell'offerta. La conferma arriva dalla struttura che prenota sul Ledger. Per una lingua rara serve una fonte che verifichi gli attributi del medico partner.

**Prossimo passo**
- Far revisionare la [PR #8](https://github.com/AndreiCiubara/MACH-P4radigm/pull/8) e provare il primo percorso cross-ASST dopo il rilascio coordinato. Il rinnovo P1 resta nel compito separato del CUP.

## 2026-11-20 21:50 — Ismail — GP sbloccato e regole di squadra

**Fatto**
- Console: 11 percorsi su 12 fermi sul GP. Causa: il GP accettava solo `symptom_code=`, i cittadini scrivono in testo libero. Bug riprodotto con un test sull'SDK vero (`tools/test_fix.py`).
- PR #6: fallback a parole chiave nel GP, red flag su tutta la storia, ricetta solo dopo `prescribed`, specialist con consenso `report_sharing`. Conflitto con `main` risolto tenendo anche il fix della risposta del Ledger in un'altra conversazione. 19 test su 19.
- Repo organizzata: `AI.md` (regole), `team/PROJECT.md`, `team/TASKS.md`, `team/PROBLEMS.md`, `team/DECISIONS.md`, questo journal, template delle PR.

**Problemi**
- CUP senza cross-ASST e P1; LLM di Abed non su GitHub (vedi `team/PROBLEMS.md`).

**Prossimo passo**
- Controllare in console che i percorsi ripartano dopo il deploy del GP; deploy dello specialist 22:30-23:00.
