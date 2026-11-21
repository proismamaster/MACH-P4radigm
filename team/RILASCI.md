# Rilasci

Registro di ogni deploy e rollback, per legare ogni verdetto alla versione che l'ha prodotto. Orari **UTC** (locale = UTC+1).
Chi rilascia aggiunge la riga **subito dopo** `city deploy` / `city rollback`, nella stessa PR del bump della card.

## Regole

1. **Un rilascio alla volta per la squadra**, almeno 75 s tra due deploy (quota: uno al minuto). Prima di rilasciare: `git pull`, prove dell'agente in `tools/`, `find asst -name __pycache__ -prune -exec rm -rf {} +`, `city card validate <ruolo>`.
2. **Il commit rilasciato è quello di `main`**: si rilascia solo da `main` aggiornato, mai da un ramo. La riga riporta lo SHA di `main` al momento del deploy.
3. **Attribuzione.** Una versione nuova serve subito, anche i percorsi già aperti (kit, ADR-083). Un passo di un percorso appartiene alla versione online **all'ora di quel passo** (ora del messaggio nella console), non all'ora del verdetto. Per giudicare una versione si guardano solo i percorsi **iniziati dopo** l'ora del rilascio + 1 minuto; quelli a cavallo si segnano come «misti».
4. **Una sola modifica di comportamento per rilascio, quando si può**: se due correzioni dello stesso agente vanno online insieme, i risultati non si separano più.
5. **Rollback**: `city rollback <ruolo> --to <versione>` (senza conformance). Si fa se, dopo il rilascio, compare un errore nuovo nei primi percorsi (conformance o `city --json status agent:<id>` non `deployed`, risposte mancanti, righe negative nuove). Si scrive la riga `rollback` qui, poi si apre la PR della correzione. La card **non** torna indietro: il prossimo deploy usa il numero successivo.

## Online ora

Controllato con `city --json status` alle 13:11 UTC.

| Agente | ID | Versione | Dalle (UTC) | Deployment | Rollback a |
|---|---|---|---|---|---|
| gp | `agent:rng5wcrzvhsj` | 1.0.8 | 12:54 | `dep-2d32afeb19854e3caaa323037142db3d` | 1.0.7 |
| booking_centre | `agent:ez8cb7j167p2` | 1.0.27 (#118, senza #119) | 12:07 | `dep-dd35e91a32ac49fe948493ddac02d1f9` | 1.0.26 secondo build (con #119) o 1.0.25 |
| hospital | `agent:bb01ggxymm05` | 1.0.8 | 13:17 | `dep-52f91aabb13a409192f537c97397d2ac` | 1.0.7 |
| specialist | `agent:sh35cbsy287d` | 1.0.11 | 13:10 | `dep-086fb4eecd7443579088651be26d69b7` | 1.0.10 |
| family_counseling | `agent:nkh372rd16yq` | 1.0.14 | 11:45 | `dep-a3b16f15ea954d64814b20edde0e05f6` | 1.0.13 |

Prossimi numeri (card su `main`): CUP 1.0.28, GP 1.0.8, ospedale 1.0.8, specialist 1.0.9, consultorio 1.0.15. Scale: CUP e GP un pod, concorrenza 32.

## Registro

| Ora UTC | Agente | Versione | Azione | Deployment | Commit | Contenuto (PR / commit) |
|---|---|---|---|---|---|---|
| 21/11 01:48 | hospital | 1.0.1 | deploy | `dep-92866e97327b42dcac5b6338d99d48fe` | `14b8f31` | conformance (uscita senza need_id), doppio commit (#46, #67, #74) |
| 21/11 01:51 | hospital | 1.0.2 | deploy | `dep-4669861522c1467789b731189cba2275` | `223de9d` | livelli 6-8 (#70) |
| 21/11 02:13 | booking_centre | 1.0.19 | deploy | `dep-85fbf8615be946d7a85105c086afbe1d` | `f23d670` | scadenze in giorni di agenda (#77) |
| 21/11 02:14 | hospital | 1.0.3 | deploy | `dep-2addce8b1ed04429b09abe0d81539440` | `f23d670` | scadenze in giorni di agenda (#77) |
| 21/11 02:30 | booking_centre | 1.0.20 | deploy | `dep-86b0ecb2669f4502973dcd3ef19f56bf` | `d8f018c` | messaggi con il passo successivo (#82) |
| 21/11 02:57 | specialist | 1.0.4 | deploy | `dep-3bdea6595d254e1ebd423ca375e38ac4` | `1325fe6` | scadenze in giorni di agenda (#80) |
| 21/11 03:20 | booking_centre | 1.0.21 | deploy | — | `57d3d44` | alternativa rilassata entro la scadenza (`0e32321`) |
| 21/11 03:48 | hospital | 1.0.4 | deploy | `dep-f79eb4f15c114b6e86c158a6005ec3db` | `82ae54e` | P2 con gli ID veri, prima gli slot a 24 ore (#87) |
| 21/11 03:51 | booking_centre | 1.0.22 | deploy | `dep-aac096e279f74f8d8e23c9613e4e56e3` | `45e34d3` | slot a 30 ore d'agenda (`62eb588`) |
| 21/11 03:53 | family_counseling | 1.0.8 | deploy | `dep-095cc796b9394679951c8376d4f09d6b` | `45e34d3` | slot a 30 ore d'agenda (`62eb588`) |
| 21/11 04:32 | booking_centre | 1.0.23 | deploy | — | `e88be09` | scadenza B/D dalla nascita del need, date dei partner in UTC, giorni abbreviati (`4c92cb8`) |
| 21/11 04:43 | gp | 1.0.4 | deploy | — | `597c313` | red flag del livello 8 in altre parole (`225c3c1`) |
| 21/11 07:29 | gp | 1.0.5 | deploy | — | `e439bcb` | world condiviso per ondata (`f72ce63`) |
| 21/11 09:21 | hospital | 1.0.5 | deploy (Andrei) | `dep-cf00a39451224746830c99b8bac21e0b` | `653606b` | MACH-1.3 `earliest`/`deadline` (`b5dcb99`), orologio d'agenda estrapolato e minimo 10 ore (U 4) nelle offerte ai partner, `offer_id` letto sulla sua riga (#95). Conformance PASS. |
| 21/11 09:26 | hospital | 1.0.6 | deploy (Andrei) | `dep-23e98e1ab0cb4e15ab67505ee0c87a17` | `612ad4d` | hold rifiutato dal Relay → `cancel`/`hold_refused` al CUP, history in errore non chiude il turno, log `care.hold` (#98). Conformance PASS. La 1.0.5 è rimasta online 5 minuti: i suoi effetti (offerte ai partner) si leggono insieme alla 1.0.6, che cambia solo il confirm. |
| 21/11 09:29 | booking_centre | 1.0.24 | deploy (Ismail/Opus) | `dep-3795422a70e544839eba398c31bd7b94` | `612ad4d` | correzioni della notte e #90 (offerte con generi/giorni diversi), annullamenti dopo la ricevuta verificati (#93/#97), controllo dei tempi della conferma: struttura muta 180 s → stessa confirm una volta, poi cancel facility_unavailable al cittadino e nuova ricerca (#94, log `cup.confirm`). **Senza** il filtro impostori (#86 ancora aperta). Conformance PASS. |
| 21/11 09:30 | specialist | 1.0.5 | deploy fallito (Ismail/Opus) | — | `612ad4d` | conformance FAIL `health: p99`: attesa di 20 s del consenso nel turno del check-in (#90). |
| 21/11 09:33 | specialist | 1.0.5 | deploy (Ismail/Opus) | `dep-b977d25f34314a5fb64120260501ff21` | `9f93dd1` | referto archiviato dopo 2 s anche senza consenso (#90, attesa ridotta in #101); rifiuto tardivo del Ledger abbinato a slot_id/hold_id con codice conservato, rifiuti del commit gestiti, ricevute con slot_id (#91, #92). Conformance PASS. |
| 21/11 09:34 | family_counseling | 1.0.9 | deploy (Ismail/Opus) | `dep-7199b7b16327402db6875f9ae058e455` | `d655607` | tutte le offerte in un solo messaggio (#90), anticipo minimo 10 ore e finestra MACH-1.3. Conformance PASS. |
| 21/11 09:5x | specialist | 1.0.6 | deploy (Ismail/Opus) | `dep-fa0d0d619df34f7fb289309acd4b71aa` | `d54c731` | commit di un hold rimasto senza commit a ogni turno successivo del caso (held arrivato dopo il turno della conferma: 2190006, 3370003, 2620005), log `care.held.missing`/`care.held.late` visibili (#107). Conformance PASS. |
| 21/11 10:09 | specialist | 1.0.7 | deploy (Ismail/Opus) | `dep-e266d81085594c5eadcb63e840d30232` | `bc68d4f` | lettura del caso a inizio turno: un 5xx di `city.history()` (504) riprovato una volta, nessun retry sui 4xx, secondo errore = turno senza effetti; log `care.history.error` (#110). Conformance PASS. |
| 21/11 10:03 | family_counseling | 1.0.10 | deploy fallito (Alberto/Sonnet) | — | `c9d1b28` | conformance FAIL `health: p99` (60 s, candidato non promosso, online 1.0.9): come specialist 1.0.5 alle 09:30; il consultorio 1.0.0 era fallito così anche in nottata, senza attese lunghe. |
| 21/11 10:06 | family_counseling | 1.0.10 | deploy (Alberto/Sonnet) | `dep-1db21a807504496bb2027b563b9ceab3` | `c9d1b28` | NO_CAPACITY e STALE_FENCE (`fb886bb`, `252d91d`): attesa della risposta del Ledger nella cronologia (fino a 180 s), slot rifiutato, tenuto, prenotato o passato mai riproposto, `EXPIRED` sull'hold non si riprova, rifiuti immediati del Relay e `history` in 504 gestiti, un solo giro di offerte. Conformance PASS al secondo tentativo (43,6 s). |
| 21/11 10:15 | family_counseling | 1.0.11 | deploy (Alberto/Sonnet) | `dep-651a9a35618441fbbb32234e36d9276f` | `f5451c1` | attesa della risposta del Ledger fino a 420 s (era 180): alle 10:06-10:10 il Ledger rispondeva in 208-217 s e l'attesa scadeva poco prima della risposta. Conformance PASS al primo tentativo (10,3 s). Rispetto alla 1.0.10 cambia solo questo. |
| 21/11 10:24 | family_counseling | 1.0.12 | deploy (Alberto/Sonnet) | `dep-51f2bf67c40040fe84dc12ce18fca974` | `f3f5f9f` | due difetti della 1.0.10/1.0.11 trovati nei primi percorsi: offerte sostitutive mai mandate quando il Ledger risponde dopo l'attesa (911000381, `replace:pending`) e due hold di riprova per un solo `STALE_FENCE` tra due pod (003290005, `_held_since`) (`7344846`). Include la Prova O di `tools/test_facility.py` e l'attesa paziente dell'ospedale (#113, non ancora online). Conformance PASS al primo tentativo (4,9 s). |
| 21/11 11:07 | family_counseling | 1.0.13 | deploy (Alberto/Sonnet) | `dep-97eacecfb66a4d71b0284215d69fc756` | `46cd327` | offerte sostitutive anche dopo un `cancel reason=past` (ramo R7 del confirm): `_replace_offers` segna il caso `replace:pending` per ogni cancel; `…911000382` e `…911000394` erano rimasti senza offerte dopo l'arrivo della pagina 2 (10:31 e 10:45 UTC). Rispetto alla 1.0.12 cambia solo questo. Conformance PASS al primo tentativo (8,0 s). |
| 21/11 10:45 | booking_centre | 1.0.25 | deploy (Andrei) | `dep-a6068797fa384615b5a08394f110fb2b` | `3150c17` | PR unica #116 (Abed) con #106 timeout di history, #109 nuova ricerca per lingua rara, #112 MACH-1.4, #114 contesa sugli slot tra pratiche e finestre impossibili, #115 fino a cinque offerte varie. Review di Andrei: 28 suite verdi, card valida. **Senza** il filtro impostori (#86, in review separata). Conformance PASS (18,3 s). |
| 21/11 10:47 | hospital | 1.0.7 | deploy (Andrei) | `dep-bbe98f223dff429490fb412e3eaa7e39` | `3150c17` | attesa paziente di `held` e `committed` nel turno del confirm (fino a 180 s), slot tenuti/prenotati/passati segnati per il processo con cancel `no_capacity` immediato, nuovo hold dopo un rifiuto (#113). 82 s dopo il CUP 1.0.25. Conformance PASS (39,1 s). |

| 21/11 prima delle 11:16 | booking_centre | 1.0.26 | deploy fallito (Ismail/Opus) | — | `8414968` | conformance FAIL `health: p99` (carico della città: lo stesso codice è passato al tentativo successivo, 11:16). Ora esatta non annotata. |
| 21/11 11:16 | booking_centre | 1.0.26 | deploy (Ismail/Opus) | `dep-e2aca534c0d24b7bbfd8e5ca439ed497` | `8414968` | B preferisce gli slot ad almeno 20 ore d'agenda, sempre dentro la scadenza vera (il cittadino conferma dopo 19 ore di mediana; 12 slot confermati erano già passati) (#119). Conformance PASS. |
| 21/11 11:18 | booking_centre | 1.0.26 (secondo build) | deploy (Andrei) | `dep-77ea4b5b7cd34d45b8281d7656f315fd` | `a2c00a8` | **Due build con lo stesso numero.** Il deploy di Ismail delle 11:16 (`8414968`, solo #119) e questo, partito da `main` dopo il merge della #118 con la card ancora a 1.0.26 in locale, si sono sovrapposti: i miei due tentativi delle 11:14 e 11:15 sono finiti in `QUOTA_EXCEEDED` per il suo deploy. Online da qui: #119 + #118 (Abed, completa la #86: partner incompatibili nell'Index esclusi anche dal ring e dalla memoria; recupero dopo rifiuto per `deadline` dentro il termine della pratica, caso 3130005). 29 suite verdi su `a2c00a8`. Conformance PASS (32,3 s). Per l'attribuzione: 11:16-11:18 = solo #119; dalle 11:18 = #119 + #118. Il prossimo rilascio del CUP è 1.0.27. |
| 21/11 11:27 | gp | 1.0.6 | deploy (Ismail/Opus) | `dep-3fa923f18e4242cd9735b880c02639ee` | `a098c38` | dopo `prescribe` legge la storia una volta al secondo fino a 90 s per `prescribed` (405: ricetta sul Ledger mai annunciata, il cittadino non arriva al CUP); log `gp.prescribed.late` (#122). Conformance PASS. |
| 21/11 11:35 | gp | 1.0.7 | deploy (Ismail/Opus) | `dep-00f0f71e97ab4a988ef0e4bb1ea82243` | `a4e1c70` | attesa del `prescribed` limitata a 90 s di tempo reale e a 3 errori di fila della storia (prima: 90 letture, un turno poteva durare minuti con letture lente) (#125). Conformance PASS. |
| 21/11 11:45 | family_counseling | 1.0.14 | deploy (Ismail/Opus) | `dep-a3b16f15ea954d64814b20edde0e05f6` | `c65cccd` | stato letto dalla cronologia dopo un cambio di pod: rifiuti già gestiti, riprova unica, offerte dovute dopo un cancel (Hapca, #127; 9 controlli nuovi falliscono sulla 1.0.13). Conformance PASS. |
| 21/11 11:58 | specialist | 1.0.8 | deploy (Ismail/Opus) | `dep-0529d8ed84554da29972a22e62022443` | `00cf662` | regola P2 in vigore (agenda 29/12 08:00): hold cross-ASST con `cross_asst_consent_ref`/`cross_consent_ref` quando il CUP li manda separati da `consent_ref` (#129). Conformance PASS. |
| 21/11 11:58 | booking_centre, gp | — | `city scale --min 1 --max 1 --concurrency 32` (Ismail/Opus) | — | — | era 8 (05:48). Export 10:53-11:53 UTC: alle 11:31:38-51 circa 60 cittadini scrivono al CUP insieme, 37 non ricevono mai risposta (e 5 al GP). Un solo pod: con più repliche due pod gestirebbero lo stesso caso. |
| 21/11 12:07 | booking_centre | 1.0.27 | deploy (Ismail/Opus) + `city scale --concurrency 32` | `dep-dd35e91a32ac49fe948493ddac02d1f9` | `7337b26` | **tolta la #119** (B a 20 ore): export 10:53-11:53 UTC, dopo le 11:18 i rifiuti per scadenza per offerta raddoppiano (0,45 -> 0,90) e le conferme nei falliti scendono da 16 a 1 (#131). Contiene #118. Scale riapplicato dopo il rilascio. Conformance PASS. |
| 21/11 12:54 | gp | 1.0.8 | deploy (Andrei) | `dep-2d32afeb19854e3caaa323037142db3d` | `f1f989a` | #135: `history` in 504 non chiude il turno (3 tentativi, poi escalation se red flag, nessuna ricetta alla cieca), `prescribed` atteso fino a 420 s (era 90), `world` atteso nella storia fino a 180 s (era 6). Conformance PASS (11,7 s). |
| 21/11 13:10 | specialist | 1.0.11 | deploy (Andrei) | `dep-086fb4eecd7443579088651be26d69b7` | `a926139` | #139 sopra l'attesa di Ismail (1.0.10): attesa del Ledger 420 s, rifiuto immediato del Relay sull'hold al CUP, slot presi segnati con cancel `no_capacity` subito, ricerche dei partner da agenda e pagina gia' lette (risposta subito). Card portata a 1.0.11 a mano prima del deploy: la 1.0.10 era gia' online. Conformance PASS (23,3 s). |
| 21/11 13:17 | hospital | 1.0.8 | deploy (Andrei) | `dep-52f91aabb13a409192f537c97397d2ac` | `8e982d3` | #142: ricerche dei CUP partner da agenda e pagina gia' lette in altri casi (fino a 120 s, risposta subito invece di un giro del Ledger), attesa paziente 420 s (era 180), `checked_in` letto nella cronologia. Conformance PASS (28,4 s). |
Commit: per le righe fino alle 07:29 è il commit del bump della card (il codice rilasciato è quello del suo genitore su `main`); dalle prossime, lo SHA di `main` rilasciato. Le righe con «—» sono ricostruite dai commit: chi ha fatto quei deploy può completare il deployment.
