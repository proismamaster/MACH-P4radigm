# Compiti (uno per persona, nessuna sovrapposizione)

Aggiorna la tua riga quando cambi stato. Un compito tocca solo i file indicati.

| Compito | Chi | File che può toccare | Stato | Branch / PR | Scadenza |
|---|---|---|---|---|---|
| GP: sintomi in testo libero + ricetta dopo `prescribed` | Ismail | `asst/gp/` | online 1.0.2 (22:03) | PR #6 | fatto |
| GP: messaggi cortesi con passo successivo (review proattività) | Ismail | `asst/gp/` | unito, da pubblicare | PR #7 | prossima finestra |
| Specialist: follow-up (`prescribe ... follow_up_of=`) | Ismail | `asst/specialist/` | da fare | — | — |
| GP e specialist: red flag del world, DUPLICATE, ledger_ref, referto unico | Ismail | `asst/gp/`, `asst/specialist/` | specialist online; GP da pubblicare | PR #10 | 23:30 |
| Ridurre hospital/consultorio al solo codice dei due ruoli (`tools/riduci_agente.py` + confronto) | Alberto | `asst/hospital/`, `asst/family_counseling/` | da fare | — | prima del prossimo deploy |
| Specialist: consenso `report_sharing` + messaggi cortesi | Ismail | `asst/specialist/` | online 1.0.2 (22:34) | PR #6, #7, #10 | fatto |
| CUP: ricerca cross-ASST con `city.find` e consenso `cross_asst` | Abed | `asst/booking_centre/` | online 1.0.1 dalle 22:47 secondo il passaggio di turno; da verificare in Arena | PR #8, #13 | 00:00 (L4) |
| CUP L4: giorni richiesti al partner e ripresa dopo il rifiuto dell'ultima offerta | Abed | `asst/booking_centre/`, `tools/test_cup_medici.py`, `tools/test_cup_recovery.py` | testato in locale, in revisione | PR #34 · `abed/cup-l4-preferenze` | L4 |
| CUP: parser del consenso con testo prima dell'atto, slot partner ritirato durante il consenso | Abed | `asst/booking_centre/`, `tools/test_cup_recovery.py` | unito su main | PR #14 | 00:00 (L4) |
| CUP: rinnovo P1 (`PRESCRIPTION_EXPIRED` → GP) | Abed | `asst/booking_centre/`, `tools/test_cup_recovery.py` | unito su main, verifica in Arena da fare | PR #14 | prima di L8 |
| CUP: lettura preventiva di `rules` | Abed | `asst/booking_centre/` | da verificare con il formato del Ledger in Arena | — | prima di L8 |
| Collegamento LLM (Gemma) su GitHub | Abed | il suo agente | da pushare | — | subito |
| Ospedale e consultorio: formato ID nel controllo P2, mai inventare il consent_ref, non riproporre lo slot annullato | Alberto | `asst/hospital/`, `asst/family_counseling/` | da fare | — | prima di L4 |
| Ospedale e consultorio: verifica in console, ospedale giù | Alberto | `asst/hospital/`, `asst/family_counseling/`, `tools/` | dall'1:00 | — | — |
| Scenari di test fino a 15, registro regole, righe negative dalla console | Ettore | `team/scenari.md`, `team/registro-regole.md` | in corso | — | — |
| Pitch e vision 2027 | Ettore | `team/pitch.md` | in corso | — | sabato 14:00 |
| Merge delle PR e decisioni | Andrei | tutto (solo merge) | dall'1:00 | — | — |

## Fase 5 (dalle 01:30 del 21/11) — capo: Ismail. Deploy: solo Claude sul PC di Ismail

Livello 5 «Vincoli combinati»: priorità, lingue e disponibilità si sovrappongono. Online: CUP 1.0.8, GP 1.0.3, consultorio 1.0.1, specialist 1.0.2, ospedale 1.0.0.

| Compito | Chi | File che può toccare | Stato | Branch / PR |
|---|---|---|---|---|
| CUP L5: vincoli combinati (lingua + genere + giorni + priorità) dentro la finestra; insieme vuoto = alternativa rilassata sui giorni; dopo `consent_declined` offrire un posto della nostra ASST | Abed | `asst/booking_centre/`, `tools/test_cup_*.py` | unito su main | PR #42 · `abed/cup-l5` |
| Ospedale: doppio commit sullo stesso slot (069, 099: commit, poi ricevuta e annullamento) con la riproduzione del Ledger simulato | Andrei | `asst/hospital/`, `tools/test_facility.py` | unito su main (PR #46 via #60), da pubblicare: online ospedale 1.0.0 | PR #46, #60 · `andrei/hospital-doppio-commit` |
| Ospedale: conformance 1.0.1 (`custody.ack` renews=[], `invoke.signature` effect, `invoke.idempotency` conflict effect) | Andrei | `asst/hospital/`, `tools/test_facility.py` | causa trovata, test verdi (prova E), da pubblicare | `andrei/hospital-conformance` |
| Ospedale L6-L8 dal consultorio: riprenotazione dopo `fault.cancel`/hold scaduto, stessa request_id = stesse offerte, stesso confirm = stessa ricevuta, codici del Ledger al CUP, P2 con `rules` riletto | Andrei | `asst/hospital/`, `tools/test_facility.py` | test verdi (prove F, G; A, B aggiornate), da pubblicare | `andrei/hospital-l6-l8` |
| Console: ogni 20 minuti tabella dei percorsi falliti e aperti del livello 5 (need_id, agente, causa, testo vero) in `team/PROBLEMS.md` | Sonnet (PC di Ismail) | `team/PROBLEMS.md` | da fare | `sonnet/console-l5` |
| Deploy, review delle PR, specialist follow-up | Claude (Opus) | `asst/specialist/`, card | in corso | — |

## Chiusura (21/11 04:20) — Alberto

| Compito | Stato | Branch / PR |
|---|---|---|
| Consultorio: L6-L8, trust ring (modalità sicura), conformance, riprova del hold, scadenze in giorni di agenda | online 1.0.7, in `main` | `hapca/consultorio-riprova-hold`, `hapca/trust-ring` |
| CUP: orologio, paging, anticipo minimo, cancel con id, rifiuti day/gender | online (CUP 1.0.21-1.0.23) | `hapca/cup-orologio`, `-pagine`, `-lead`, `-deadline`, `-rifiuti-day-gender` |
| CUP: partner incompatibili e scadenza delle alternative | in revisione | `abed/cup-partner-verificati` (PR #118, integra la #86) |
| Ospedale e specialist: riprova su `EXPIRED`/`STALE_FENCE` | solo se i messaggi del Ledger lo confermano | — |

## Da solo (21/11 04:30-08:40) — Alberto con Claude, su tutti gli agenti

| Compito | Stato | Commit |
|---|---|---|
| CUP: scadenza dalla nascita del need, B senza preferenza 30 ore, date dei partner in UTC, giorni abbreviati | online 1.0.23 (05:32) | `4c92cb8` |
| GP: red flag del livello 8 parafrasate e del `world` con 2/3 delle parole | online 1.0.4 (05:43) | `225c3c1` |
| Scale di CUP e GP a concorrenza 8 | fatto alle 05:48, nessun effetto misurato | — |
| MACH-1.3: finestra `earliest=`/`deadline=` in consultorio e ospedale, R7 al confirm, token nelle ricerche del CUP | in `main`, alle 10:00 (ospedale 1.0.5, consultorio 1.0.9, CUP 1.0.24) | `b5dcb99` |
| Anticipo minimo 10 ore (U 4), margine 1 ora al confirm, simulazione dei percorsi | in `main`, alle 10:00 | `e2d1518` |
| Ritardo del Ledger: letture condivise per ondata, richieste in parallelo, al massimo 6 partner | GP online 1.0.5 (08:29); CUP e consultorio alle 10:00 | `f72ce63` |
| Console dopo il rilascio: tempi GP e CUP, ricerche ai partner, `day`/`gender`/`past`/`deadline`, ricevute | Abed: dati precedenti al rilascio registrati; campione successivo da raccogliere | `abed/cup-verifica-annullamenti` |
| CUP: verificare il mittente e i riferimenti degli annullamenti dopo la ricevuta | Abed: online in CUP 1.0.24 | PR #93 / #97 · `abed/cup-verifica-annullamenti` |
| CUP: riprovare la lettura della cronologia su 5xx senza perdere i riferimenti della conferma | Abed: in revisione | PR #106 · `abed/cup-history-timeout` |
| Verdetto di cardiologia con le righe dello specialist (per il follow-up) | da cercare in console | — |
| Riga `facts` MACH-1.3 per le nostre strutture su Discord | Alberto | — |
| Consultorio: NO_CAPACITY (2560005, 3290003), STALE_FENCE, EXPIRED, attesa paziente, rifiuti del Relay; misura di hold e commit separata dalla prima offerta | online 1.0.13 (11:07 UTC); il cambio di pod (terzo hold, offerte dovute, caso con ricerca di un CUP) è corretto in `hapca/consultorio-stato-dalla-cronologia`, da pubblicare | `fb886bb`, `252d91d`, `46cd327` |
| Ospedale e specialist: stessa attesa paziente e stesso segno degli slot presi (NO_CAPACITY 28/42 e 112, STALE_FENCE 10/12 e 17/24) | da fare, file di Andrei e di Ismail | — |

## Deploy

Fino all'1:00 pubblicano solo Abed o Ismail, nelle finestre di Down, un agente alla volta, annunciando nel gruppo. Procedura in `AI.md`.
