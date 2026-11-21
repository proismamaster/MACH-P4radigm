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

| Agente | ID | Versione | Dalle (UTC) | Deployment | Rollback a |
|---|---|---|---|---|---|
| gp | `agent:rng5wcrzvhsj` | 1.0.5 | 07:29 | — | 1.0.4 |
| booking_centre | `agent:ez8cb7j167p2` | 1.0.23 | 04:32 | — | 1.0.22 |
| hospital | `agent:bb01ggxymm05` | 1.0.5 | 09:21 | `dep-cf00a39451224746830c99b8bac21e0b` | 1.0.4 |
| specialist | `agent:sh35cbsy287d` | 1.0.4 | 02:57 | `dep-3bdea6595d254e1ebd423ca375e38ac4` | 1.0.3 |
| family_counseling | `agent:nkh372rd16yq` | 1.0.8 | 03:53 | `dep-095cc796b9394679951c8376d4f09d6b` | 1.0.7 |

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

Commit: per le righe fino alle 07:29 è il commit del bump della card (il codice rilasciato è quello del suo genitore su `main`); dalle prossime, lo SHA di `main` rilasciato. Le righe con «—» sono ricostruite dai commit: chi ha fatto quei deploy può completare il deployment.
