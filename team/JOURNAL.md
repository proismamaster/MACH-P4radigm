# Journal (la voce più recente in alto)

## 2026-11-21 11:30 — Alberto (Hhapca, con Claude) — Consultorio 1.0.12 online; con il Ledger a 3 minuti nessun commit può riuscire

**Fatto**
- **1.0.12 online dalle 10:24 UTC** (`dep-51f2bf67c40040fe84dc12ce18fca974`, conformance PASS al primo tentativo in 4,9 s), da `main` @ `f3f5f9f`: offerte sostitutive in sospeso (`replace:pending`) e riprova unica anche tra pod (`_held_since`), più la Prova O di `tools/test_facility.py` e l'attesa paziente dell'ospedale (#113, non online). Card 1.0.13 e riga nel registro in `main` (`c6a9fd3`). Rollback: `city rollback agent:nkh372rd16yq --to 1.0.11`.
- Prova in vivo: caso 911000386, `held` alle 10:22:30 e **commit alle 10:22:31**, ma `STALE_FENCE` alle 10:25:35. Con 3 minuti di Ledger a ogni richiesta l'hold scade prima che il commit sia processato, anche partendo subito.

**Problemi**
- Il collo di bottiglia è la latenza del Ledger (199-221 s per richiesta, push 60-200 s): finché non scende sotto i ~100 s nessun team può prenotare. Il nostro codice è ora al meglio per quando scenderà.
- Resta da fare, in rilasci separati: anticipo minimo 16-20 ore per l'accesso diretto; niente riprova dopo `STALE_FENCE` se lo slot è a meno di ~8 ore d'agenda (003290005: due hold su uno slot già passato).
- Da verificare in vivo: le offerte sostitutive in sospeso (911000382 aspetta la pagina 2).

**Prossimo passo**
- Rimisurare con `await misura('agent:nkh372rd16yq')` quando la latenza del Ledger scende, e guardare `held` → commit contro `STALE_FENCE`.

## 2026-11-21 11:22 — Alberto (Hhapca, con Claude) — Consultorio 1.0.11 online; due difetti miei trovati in console, correzione pronta

**Fatto**
- **1.0.11 online dalle 10:15 UTC** (`dep-651a9a35618441fbbb32234e36d9276f`, conformance PASS al primo tentativo in 10,3 s): attesa della risposta del Ledger fino a 420 s (era 180: il Ledger risponde in 199-221 s). `main` @ `9d2ae23`, card 1.0.12, riga nel registro dei rilasci.
- Letti i primi percorsi dopo i rilasci (10:10-10:16 UTC): trovati e riprodotti con test (falliscono sul codice online) due difetti: (1) **offerte sostitutive mai mandate** quando la risposta del Ledger arriva dopo l'attesa: il `return` che avevo messo ai push del Ledger lascia il cittadino senza offerte (911000381, 5 minuti); (2) **due hold di riprova** per un solo `STALE_FENCE` quando il rifiuto lo legge anche il pod del rilascio (003290005): falso NO_CAPACITY sul secondo. Correzioni sul branch `hapca/consultorio-sostitutive` (`replace:pending`, `_held_since`), test 58 controlli verdi, 29 programmi verdi, card valida.

**Problemi**
- Non pubblicato: le correzioni sono sul branch, online c'è ancora la 1.0.11 con i due difetti.
- Gli slot scadono prima dell'hold (911000376: `EXPIRED ... has passed` alle 10:14:11): il giro offerta → hold dura 10-14 minuti reali e l'anticipo minimo è 10 ore d'agenda. Da alzare a 16-20 ore per l'accesso diretto, meglio dalla latenza misurata: rilascio a parte.
- A 199-221 s per richiesta del Ledger nessun commit sta nella durata di un hold (circa 2 minuti), anche partendo subito: finché la latenza non scende il collo di bottiglia non è il nostro codice.

**Prossimo passo**
- OK al rilascio di `hapca/consultorio-sostitutive` (1.0.12), poi rimisurare con `await misura('agent:nkh372rd16yq')`.
- Poi l'anticipo minimo per l'accesso diretto.

## 2026-11-21 11:10 — Alberto (Hhapca, con Claude) — Consultorio 1.0.10 online (NO_CAPACITY, STALE_FENCE, attesa del Ledger)

**Fatto**
- Il ramo `hapca/consultorio-ledger-lento` è in `main` (`c9d1b28`, avanzamento semplice) e il consultorio è **online alla 1.0.10 dalle 10:06 UTC** (`dep-1db21a807504496bb2027b563b9ceab3`, conformance PASS in 43,6 s). Card a 1.0.11 e riga nel registro dei rilasci in `main` (`2887797`). Rollback pronto: `city rollback agent:nkh372rd16yq --to 1.0.9`.
- Contenuto: vedi la voce delle 11:05 qui sotto e `team/PROBLEMS.md` (casi 2560005 e 3290003, tempi per fase).

**Problemi**
- Il primo deploy (10:03 UTC) è fallito in conformance, stadio `health`, dettaglio `p99` (60 s): il candidato non è stato promosso, online è rimasta la 1.0.9. Stesso esito di specialist 1.0.5 alle 09:30 (Ismail lo ha attribuito all'attesa di 20 s nel turno del check-in) e del consultorio 1.0.0 in nottata, quando non c'erano attese lunghe. Riprovato dopo 3 minuti con lo stesso codice, che ha le attese di 180 s: PASS. Quindi le attese non fanno fallire la conformance di per sé; la causa resta incerta (lo stadio `health` viene prima di ogni prova sul brain: 5 richieste di riscaldamento e 20 misurate, tutte sotto 0,3 s). Se capita ancora: riprovare dopo 75 s prima di cambiare il codice.
- Non ancora verificato in Arena: i percorsi iniziati prima delle 10:08 UTC sono della 1.0.9.

**Prossimo passo**
- Dopo le 10:10 UTC rilanciare `await misura('agent:nkh372rd16yq')` (`tools/misura_latenze.js`) e leggere sui percorsi nuovi: `held` → commit sotto i 10 s, `committed` contro `commit STALE_FENCE`, `hold NO_CAPACITY` e `hold EXPIRED`, prima offerta.
- Se la 1.0.10 peggiora qualcosa di nuovo nei primi percorsi: rollback alla 1.0.9 e riga `rollback` nel registro.

## 2026-11-21 11:05 — Alberto (Hhapca, con Claude) — Consultorio: NO_CAPACITY, STALE_FENCE e tempi di hold e commit

**Fatto** (branch `hapca/consultorio-ledger-lento`, 3 commit sopra `main`; NON pubblicato, online resta la 1.0.9)
- Riprodotti i percorsi 2560005 e 3290003 dalla console (`/v1/team/journeys/<need>` e i messaggi del consultorio): cinque cittadini ricevono le stesse quattro offerte, il primo che conferma tiene lo slot, gli altri `NO_CAPACITY` dopo ~100 s, e il cancel è seguito da offerte che **citano di nuovo lo slot rifiutato** (il cancel appena mandato non è nella cronologia da cui si calcolano). Il cittadino lo riconferma e resta senza risposta (07:41, 07:57, 08:13).
- Misurati i tempi **separati** (tabella in `team/PROBLEMS.md`, strumento `tools/misura_latenze.js`): prima offerta, hold, commit. In ogni finestra il nostro ritardo è pari a quello del Ledger; 27 commit su 36 rifiutati `STALE_FENCE`: i commit partiti entro 10 s da `held` riescono tutti, quelli oltre 60 s falliscono tutti.
- Correzioni: attesa paziente della risposta (commit subito dopo `held`, ricevuta subito dopo `committed`, offerte subito dopo agenda e world); slot rifiutato mai riproposto; slot tenuti, prenotati o passati segnati per tutto il processo (anche per le ricerche dei CUP) e un confirm su uno slot già preso riceve subito il cancel; EXPIRED sull'hold non si riprova (è uno slot passato); un solo giro di offerte per risposta del Ledger; rifiuti immediati del Relay (CapError su hold e commit) e `history` in 504 gestiti come nell'ospedale (#98); `offer_id` del cancel letto sulla riga giusta.
- Test: `tools/test_consultorio_ledger_lento.py` (53 controlli, 32 falliscono su `main`); tutti gli altri verdi (28 programmi), card valida. `test_facility.py` ora spegne l'attesa paziente nei test.

**Problemi**
- Non confermato: la durata dell'hold (dai dati circa 2 minuti, non nel kit) e l'effetto reale delle correzioni, che si vede solo dopo il deploy.
- Il file del consultorio passa da 2026 a 2236 righe: i deploy fin qui (2020 righe) sono passati, questo non è provato. Rollback pronto: `city rollback agent:nkh372rd16yq --to 1.0.9`.
- **Ospedale e specialist hanno lo stesso schema** (`hold NO_CAPACITY` 28 su 42 e 112, `commit STALE_FENCE` 10 su 12 e 17 su 24; `held` → commit mediana 107 s e 61-87 s). Sono file di Andrei e di Ismail: l'attesa paziente e il segno degli slot presi sono da portare lì (Ismail ha già #107 sul commit tardivo dello specialist).
- `tools/test_mach12_struttura.py asst/hospital/agent/agent.py` fallisce in 7 punti già su `main` (fixture dell'ospedale vecchie), non per questa modifica.

**Prossimo passo**
- Pubblicare il consultorio (serve l'OK), poi rilanciare `await misura('agent:nkh372rd16yq')` sui percorsi nuovi: `held` → commit sotto i 10 s, `committed` contro `STALE_FENCE`, `hold NO_CAPACITY` e `hold EXPIRED`.

## 2026-11-21 10:38 — Abed — Recupero dei timeout della cronologia del CUP

**Fatto**
- Riprodotto un timeout di `city.history` sulla conferma del cittadino. Il CUP ritenta la lettura una volta su un errore 5xx e usa la cronologia recuperata per inoltrare la conferma.

**Problemi**
- Se la cronologia resta indisponibile, il CUP registra l'errore e chiude il turno senza dedurre offerte, consensi o ricevute. Il prossimo messaggio farà una nuova lettura.

**Prossimo passo**
- Review della PR e verifica in città dopo un rilascio. Per i rilasci già online dal giro delle 10:29–10:34 confrontare i percorsi nati dopo le 10:35 e seguire `confirm → hold → commit → ricevuta` per ogni conferma senza esito.

## 2026-11-21 10:35 — Andrei (Claude) — Ospedale 1.0.5 online; 1.0.6: un confirm non resta mai senza risposta (3590002)

**Dove si ferma la catena in 3590002** (dato di Ismail, #94: il CUP ha inoltrato il confirm, la struttura non ha mai risposto per 32 minuti, nessun hold nel verdetto). In locale, con un confirm valido, l'ospedale manda sempre l'hold. Nel codice ci sono due strade che portano al silenzio, tutte e due nell'ospedale:
1. **Il Relay rifiuta l'hold subito** con una CapError (`EXPIRED`, `NO_CAPACITY`, `CONSENT_MISSING`, `STALE_FENCE`: è quello che dava al consultorio `cancel EXPIRED` un secondo dopo il confirm). `_say` la inghiottiva: niente al CUP, niente hold sul Ledger. Il caso più probabile con un confirm rapido: due cittadini B confermano lo stesso slot vicino, il secondo prende `NO_CAPACITY`.
2. **`city.history` in errore (504) in `main()`**: l'eccezione esce dal brain, l'harness registra "agent crashed" e chiude il messaggio come `rejected`. Il confirm non torna più.

**Correzione** (`andrei/ospedale-hold-mai-muto`, ospedale 1.0.6): un rifiuto definitivo dell'hold passa da `_on_refused`, come un `refused hold` del Ledger: il CUP riceve `cancel reason=no_capacity|consent_missing` o `hold_refused ledger_code=...` e cerca un altro orario. Un errore incerto (5xx, 429) libera il claim: il confirm rimandato dal watchdog del CUP (#94, dopo 180 s) rifà l'hold. `DUPLICATE` = l'hold c'è già, si va avanti. Se history fallisce, il turno continua con il solo messaggio. Righe di log `care.hold` e `care.hold.failed code=` (con `/v1/logs?agent_id=agent%3Abb01ggxymm05&q=care.hold`) per vedere dal vivo dove si ferma. Test: Prova N in `tools/test_facility.py` (3 casi falliscono su `main`).

**Rilasci**: ospedale 1.0.5 alle 09:21 UTC (`dep-cf00a394…`, `main` @ `653606b`). La 1.0.6 è un rilascio a parte: i risultati delle 2 versioni restano separati in `team/RILASCI.md`. Stesso `city.history` non protetto in `main()` di CUP, specialist e consultorio: da valutare da chi li segue.

## 2026-11-21 10:07 — Abed — Controllo degli annullamenti del CUP

**Fatto**
- Riprodotta la riapertura di una prenotazione dopo un annullamento estraneo o con riferimenti contraddittori. Il CUP ora verifica il mittente e abbina i riferimenti alla ricevuta attiva, anche dopo una prima riprenotazione.
- Registrati in `PROBLEMS.md` i rifiuti per giorno, genere e scadenza prima della 1.0.24 e le cinque conferme senza ricevuta visibile, con la struttura scelta.

**Problemi**
- Al controllo in console risultava visibile CUP 1.0.23. Il confronto con la 1.0.24 richiede casi nati dopo il rilascio.

**Prossimo passo**
- Rivedere la PR e verificare un annullamento autentico in Arena. Sul campione dopo il rilascio confrontare i motivi di rifiuto e ogni conferma senza ricevuta.
## 2026-11-21 10:25 — Andrei (Claude) — Ospedale: review di `main`, catena confirm → hold (caso tipo 3590002), registro dei rilasci

**Catena del confirm, provata in locale** (CUP vero + ospedale vero, orologio finto a 60x; script in scratchpad): con un confirm del cittadino 55 s dopo l'offerta il CUP inoltra subito `confirm ... slot_id= consent_ref= facility=agent:...` all'ospedale, e l'ospedale manda l'`hold` al Ledger nello stesso turno, anche con il Ledger che risponde al turno dopo, con `held` e `committed` in turni separati e con il confirm ripetuto (un solo hold). Se il confirm arriva all'ospedale, l'hold parte. Dove la catena si può fermare senza hold:
- **CUP, in silenzio**: `_cup_confirm` esce senza dire niente se `uncertain_confirmation` è rimasto vero (un 5xx o DUPLICATE sull'inoltro di un confirm precedente dello stesso need), se l'offerta non è nell'ultimo lotto mandato, se manca il consenso, se c'è già un confirm in sospeso per un'altra offerta.
- **CUP, con messaggio**: `slot_expired` (1870004: confirm 04:08:54, risposta 04:13:24 dopo 4,5 minuti di turno; lo slot era a 1 ora).
- **Ledger**: risponde in 7-9 minuti (PROBLEMS 06:15). Il giudice conta i fatti scritti fino a un minuto dopo la fine del percorso: un hold mandato ma non ancora scritto dal Ledger non compare nel verdetto.
- Per 3590002 serve il JSON del percorso (console → Journeys): se dopo il confirm il CUP tace è il CUP; se il CUP risponde `facility_cancelled` è l'ospedale o il Ledger. L'export non ha i messaggi tra agenti: per vedere il confirm all'ospedale servono `/v1/team/agents/agent:bb01ggxymm05/messages` o `/v1/logs` dal vivo.

**Review di `b5dcb99` per l'ospedale** (l'unica differenza tra la 1.0.4 online e `main`): per B e U l'ospedale offriva ai CUP partner lo slot più vicino oltre **4 ore**, calcolate sull'`agenda_now` **grezzo** del Ledger (vecchio di ore d'agenda quando arriva). Un CUP di un'altra squadra che non manda `earliest=` riceveva slot già vicini o passati: confirm, hold rifiutato, nessun hold nel verdetto. Corretto (`andrei/ospedale-orologio`):
- orologio d'agenda estrapolato (`_agenda_now`, uguale a CUP e consultorio) nelle risposte alle ricerche;
- anticipo minimo 10 ore (U 4) nelle offerte, come CUP e consultorio;
- `_our_offer` legge la riga dell'offerta, non tutto il messaggio: un confirm con il solo `offer_id` della seconda offerta faceva l'hold sulla prima.
- Test: Prove L e M nuove in `tools/test_facility.py`, Prova K aggiornata (N-1 a 5 ore e N-2 a 8 ore non si offrono più per B e D). Tutte le suite verdi; `test_mach12_struttura.py` ha gli stessi fallimenti di `main` (offerte rilassate MACH-1.2 mai fatte nell'ospedale).

**Registro dei rilasci**: nuovo `team/RILASCI.md` (ora UTC, versione, deployment, commit, contenuto, rollback; regole di attribuzione: un passo appartiene alla versione online all'ora del passo).

## 2026-11-21 09:40 — Andrei (Claude) — 24 percorsi falliti della console: cause e correzioni

**Fatto** (percorsi di Andrei dalla console, 21/11 01:36-04:19 UTC)
- Gia' coperti da Hapca su `main`: data dei partner senza Z (`audit false_attribute -2`, 134/191/293), scadenza B dalla ricetta (rifiuti `deadline`), slot passati (`past`, `slot_expired`), ritardo del Ledger (f72ce63), giorni abbreviati.
- **Specialist**: archivia il referto anche se il cittadino non risponde al consenso (attesa breve di 20 s, poi referto non condiviso; condiviso solo con un consent_ref `report_sharing`). Era `report_missing -1` (1820005). Test: `tools/test_specialist_referto.py`; aggiornati i casi dello specialist in `tools/test_fix.py` (la risposta tardiva non crea un secondo referto).
- **CUP**: le tre offerte coprono entrambi i generi di medico e piu' giorni (`_cup_varied`): giovedi' e venerdi' solo uomini in fisiatria, il cittadino ha preferenze nascoste e risponde una volta (12 percorsi su 24 rifiutati con `gender`/`day`). Test: `tools/test_cup_varieta.py`.
- **Consultorio**: tutte le offerte in UN messaggio (prima una per messaggio; 256 e 1970005 confermati dopo 18-34 minuti, gia' scaduti). Test: prova C di `tools/test_facility.py`.
- **GP** (2010003, nessuna risposta): su `main` il GP prescrive subito con quel testo; il silenzio era l'attesa del `world` con il Ledger a 7-9 minuti, tolta da f72ce63.
- Tutti i 23 file di test verdi; card valide.

## 2026-11-21 08:40 — Alberto (Hhapca, con Claude) — Tutto quello fatto da solo (04:30-08:40)

**Fatto** (in ordine; tutto su `main`, test verdi a ogni passo)
- 05:30 `4c92cb8` → **CUP 1.0.23 online** (05:32): scadenza B/D dalla nascita del need (messaggio al CUP − 21 ore: il cittadino scrive al CUP 19,5-20,6 minuti dopo il primo messaggio al medico, 17 percorsi); B senza la preferenza a 30 ore (oltre la scadenza vera); date dei partner inoltrate in UTC con la Z (audit `false_attribute -2` in 293, 134, 191); giorni abbreviati (`lun/mer/ven`, 288).
- 05:41 `225c3c1` → **GP 1.0.4 online** (05:43): red flag del livello 8 scritte in altro modo (fitta al petto, dolore toracico, non sento più le gambe, pain in my chest...); red flag del `world` riconosciute con due terzi delle parole; il GP non prescrive senza aver letto il `world`.
- 05:48 `city scale booking_centre|gp --min 1 --max 1 --concurrency 8` (approvato). Misurato dopo: nessun effetto sui tempi (il collo di bottiglia è il Ledger, non il pod).
- 05:57 `b5dcb99`: MACH-1.3 nelle strutture. Consultorio e ospedale rispettano `earliest=`/`after=`/`deadline=` con data e ora; l'ospedale per B e U offre il primo slot dopo il minimo (niente preferenza a 24 ore); consultorio con orologio d'agenda estrapolato e regola R7 (al confirm uno slot passato → `cancel reason=past` + nuove offerte); il CUP manda `mach=1.3 earliest= deadline=` nelle ricerche ai partner.
- 06:03 `e2d1518`: anticipo minimo 10 ore d'agenda (U 4) in CUP e consultorio, margine di 1 ora al confirm. Scelto con `tools/sim_percorsi.py`, che rigioca 21 percorsi veri: 19/21 prenotati invece di 14/21 con 4 minuti di latenza.
- 06:15 misura in console (messaggi degli agenti, `/v1/team/agents/<id>/messages`): **il Ledger risponde in 7-9 minuti** a CUP, GP e consultorio, e la risposta apre il nostro turno 6-7 minuti dopo. Il GP aspettava il `world` a ogni ricetta (84 su 84 senza protocolli né red flag); il CUP faceva 2-4 giri prima di offrire e scriveva a 25 partner per caso (550 ricerche in 26 minuti, 1 offerta utile). Dettagli in `team/PROBLEMS.md` e `team/REVISIONE.md`.
- 06:31 `f72ce63`: world, agenda e pagine del catalogo condivisi per ondata (GP 10 minuti, CUP e consultorio 5), ricetta + agenda + pagina 1 nello stesso turno, pagine mancanti 6 alla volta, al massimo 6 partner (prima quelli che offrono), niente attese nei turni aperti dalle risposte dei partner. Nuovo `tools/test_cup_ritardo.py`.
- 08:29 **GP 1.0.5 online** (OK di Alberto durante il freeze, per il ritardo del Ledger). Card a 1.0.6 (`e439bcb`).
- CUP e consultorio **non** pubblicati: restano per il deploy delle 10:00 di Andrei (PROJECT.md delle 08:30).

**Problemi**
- Con 6-9 minuti per passaggio una B (48 ore) entra a fatica anche con le correzioni: hold → commit restano due giri obbligati.
- Conformance locale: fallisce solo `custody.ack`, come per l'agente di riferimento del kit; la conferma vera è al deploy (il GP 1.0.5 l'ha passata).
- `tools/test_facility.py` non vale per lo specialist (48 fallite su un file non toccato).

**Prossimo passo**
- 10:00 (Andrei): CUP 1.0.24 + #86, ospedale 1.0.5, consultorio 1.0.9. GP no.
- 10:15: in console tempo cittadino → ricetta (GP) e `need.request` → prima offerta (CUP), ricerche ai partner per caso (≤ 6), `past`/`EXPIRED`, ricevute.
- Riga `facts` MACH-1.3 per ospedale, specialist e consultorio su Discord.

## 2026-11-21 04:15 — Andrei (Claude) — CUP: protezione dagli impostori (pronta, da pubblicare alle 10:00)

**Fatto**
- Le offerte dei partner erano già controllate (solo da chi abbiamo interrogato, `request_id`, `facility` = mittente, procedura, priorità, scadenza, riserva U, lingua/genere/giorni del medico dalla tabella). Il buco era la scelta dei partner da `city.find`: bastava la capability.
- `_cup_trusted_peers`: ruolo della famiglia giusta (fisiatria: hospital/facility; cardiologia: specialist_care/specialist/facility), `no_clinical_advice` dichiarato (solo se l'Index riporta il campo per qualcuno, così non svuota mai la lista), reputazione più alta prima. Le strutture dell'anello da Discord restano.
- Test: `tools/test_cup_impostori.py` (nuovo, 3 casi falliscono su main, 2 di controllo). Verdi tutti i test del CUP, `test_l8_ostili`, `test_fix`.

**Prossimo passo**
- Pubblicare alle 10:00 (non durante il livello 8: troppi deploy fanno perdere messaggi).
## 2026-11-21 06:35 — Alberto (Hhapca, con Claude) — Ritardo del Ledger: meno passaggi in GP, CUP e consultorio
- Misurato in console (04:43-05:15 UTC, messaggi degli agenti): il Ledger risponde 7-9 minuti dopo la richiesta e la risposta apre il nostro turno 6-7 minuti dopo, per CUP, GP e consultorio. Iniziato verso le 04:10 UTC. Lo scale a concorrenza 8 non ha cambiato niente.
- Il GP aspettava il `world` prima di ogni ricetta: 84 `world` su 84 senza protocolli né red flag. Il CUP faceva 2-4 giri di Ledger prima di offrire e mandava 25 ricerche ai partner per caso (550 in 26 minuti, 1 offerta utile).
- f72ce63 in `main`: world, agenda e pagine condivisi per ondata (GP 10 min, CUP e consultorio 5 min), richieste in parallelo, pagine 6 alla volta, al massimo 6 partner. Test verdi; non pubblicato (freeze 06-10, serve l'OK).
- Dettagli e piano in `team/REVISIONE.md`.

## 2026-11-21 04:32 — Andrei (Claude) — Ospedale: prima gli slot ad almeno 24 ore d'agenda

**Fatto**
- Dalla causa trovata da Hapca (PROBLEMS 04:25: il cittadino decide dopo 3-27 ore d'agenda, lo slot è già passato): nelle offerte dell'ospedale ai CUP prima gli slot ad almeno 24 ore d'agenda (`_DECISION_LEAD`), i vicini in coda (mai una lista più vuota di prima). U invariata. Vale anche per la riprenotazione del livello 6.
- Test: prova K (fallisce su main). Ospedale TUTTO OK.
- **Il CUP e il consultorio hanno bisogno della stessa cosa** (CUP: `_LEAD`/`_MIN_LEAD` in `fitting` e nelle offerte dei partner; consultorio: `_LEAD`). Hapca o io, prima delle 05:30.

## 2026-11-21 04:40 — Andrei (Claude) — Ospedale: P2 con gli ID veri; follow-up dello specialist in sospeso

**Fatto**
- `_other_asst` cercava la squadra nell'id (`agent:<team>/<slug>`); gli ID della città non ce l'hanno (`agent:ez8cb7j167p2`), quindi era sempre falso. Per i CUP di altre ASST: `cross_asst_consent_ref` ignorato (hold col consenso sbagliato, `CONSENT_MISSING` con P2 attiva) e nessun blocco senza consenso cross. Ora, se l'id non ha la squadra, è "altra ASST" ogni agente che non è uno dei nostri cinque (`_OUR_AGENTS`, ID fissi di AI.md).
- Test: prova J in `tools/test_facility.py` (2 controlli falliscono su main, il controllo col nostro CUP passa). Ospedale TUTTO OK; test_l8_ostili e test_fix verdi.
- Il consultorio ha lo stesso `_other_asst` (Hapca).
- Follow-up dello specialist: non implementato. Il kit dice solo "lo decide lo specialista quando il percorso lo richiede"; nessun verdetto visto lo mostra. Serve un percorso di cardiologia in console con le righe del verdetto dello specialist.

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
