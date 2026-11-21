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
| CUP L5: vincoli combinati (lingua + genere + giorni + priorità) dentro la finestra; insieme vuoto = alternativa rilassata sui giorni; dopo `consent_declined` offrire un posto della nostra ASST | Abed | `asst/booking_centre/`, `tools/test_cup_*.py` | verificato in locale, in revisione | `abed/cup-l5` |
| Ospedale: doppio commit sullo stesso slot (069, 099: commit, poi ricevuta e annullamento) con la riproduzione del Ledger simulato | Andrei | `asst/hospital/`, `tools/test_facility.py` | da fare | `andrei/hospital-doppio-commit` |
| Console: ogni 20 minuti tabella dei percorsi falliti e aperti del livello 5 (need_id, agente, causa, testo vero) in `team/PROBLEMS.md` | Sonnet (PC di Ismail) | `team/PROBLEMS.md` | da fare | `sonnet/console-l5` |
| Deploy, review delle PR, specialist follow-up | Claude (Opus) | `asst/specialist/`, card | in corso | — |

## Deploy

Fino all'1:00 pubblicano solo Abed o Ismail, nelle finestre di Down, un agente alla volta, annunciando nel gruppo. Procedura in `AI.md`.
