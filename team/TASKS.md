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
| CUP: parser del consenso con testo prima dell'atto, slot partner ritirato durante il consenso | Abed | `asst/booking_centre/`, `tools/test_cup_recovery.py` | testato in locale, in revisione | `abed/cup-rinnovo-p1` | 00:00 (L4) |
| CUP: rinnovo P1 (`PRESCRIPTION_EXPIRED` → GP) | Abed | `asst/booking_centre/`, `tools/test_cup_recovery.py` | testato in locale, in revisione | `abed/cup-rinnovo-p1` | prima di L8 |
| CUP: lettura preventiva di `rules` | Abed | `asst/booking_centre/` | da verificare con il formato del Ledger in Arena | — | prima di L8 |
| Collegamento LLM (Gemma) su GitHub | Abed | il suo agente | da pushare | — | subito |
| Ospedale e consultorio: formato ID nel controllo P2, mai inventare il consent_ref, non riproporre lo slot annullato | Alberto | `asst/hospital/`, `asst/family_counseling/` | da fare | — | prima di L4 |
| Ospedale e consultorio: verifica in console, ospedale giù | Alberto | `asst/hospital/`, `asst/family_counseling/`, `tools/` | dall'1:00 | — | — |
| Scenari di test fino a 15, registro regole, righe negative dalla console | Ettore | `team/scenari.md`, `team/registro-regole.md` | in corso | — | — |
| Pitch e vision 2027 | Ettore | `team/pitch.md` | in corso | — | sabato 14:00 |
| Merge delle PR e decisioni | Andrei | tutto (solo merge) | dall'1:00 | — | — |

## Deploy

Fino all'1:00 pubblicano solo Abed o Ismail, nelle finestre di Down, un agente alla volta, annunciando nel gruppo. Procedura in `AI.md`.
