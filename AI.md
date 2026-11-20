# AI.md — contratto della squadra p4radigm (per ogni AI e ogni persona)

Questo è l'unico file di regole. `CLAUDE.md` e `AGENTS.md` rimandano qui. Vale per Claude, ChatGPT/Codex e qualsiasi altro assistente.

## All'avvio di ogni sessione (obbligatorio)

1. Leggi `team/PROJECT.md` (stato attuale, 1 minuto) e `team/TASKS.md` (chi fa cosa). Lavora SOLO sul tuo compito.
2. Prima di toccare codice: `git fetch && git switch -c <nome>/<compito> origin/main`.
3. Se il task è un bug: leggi `team/PROBLEMS.md` per non ripetere strade già provate. Se è una scelta tecnica: `team/DECISIONS.md`. Se riguarda un livello: `team/LIVELLI.md`.

## Metodo (ogni modifica, nessuna eccezione)

1. **Prova prima di credere.** Parti da un fatto: una riga della console (need_id e testo vero del cittadino), una regola di `docs-kit/e19-rules.md` o un test che fallisce. Mai correggere "a intuito".
2. **Riproduci con un test** in `tools/` usando le frasi vere della console. Il test deve FALLIRE sul codice vecchio: se passa già, non hai trovato il bug.
3. **Correggi il minimo** nel tuo agente. Non riscrivere ciò che funziona, non toccare i file degli altri.
4. **Tutti i test verdi**: `tools/test_fix.py`, `tools/test_facility.py`, `tools/test_cup_medici.py` e il tuo. Poi `city card validate <agente>`.
5. **PR** con: cosa cambia, perché (need_id o regola), test eseguiti. Un'altra persona o AI la rilegge.
6. **Deploy** solo dopo il merge, un agente alla volta (sezione Deploy). Poi controlla `city --json status <agente>`: stasera i deploy finiscono anche `failed` per colpa della piattaforma e la versione può comparire dopo.
7. **Verifica in console**: il percorso successivo deve mostrare il comportamento giusto. Solo allora è "fatto".
8. **Scrivi cosa hai imparato**: bug in `team/PROBLEMS.md` (con causa), scelta in `team/DECISIONS.md` (con il perché), stato in `team/LIVELLI.md`.

## A fine sessione (obbligatorio)

1. Aggiungi in cima a `team/JOURNAL.md` una voce `## AAAA-MM-GG HH:MM — <nome> — titolo` con Fatto, Problemi, Prossimo passo.
2. Aggiorna il tuo compito in `team/TASKS.md` (stato, branch, PR).
3. Riscrivi `team/PROJECT.md` → "Stato attuale" se è cambiato qualcosa (massimo 10 righe).
4. Bug trovato → `team/PROBLEMS.md`. Scelta tecnica → `team/DECISIONS.md`.
5. Committa e apri la PR. Niente lavoro lasciato solo sul tuo PC.


Squadra p4radigm, 5 persone. Stato e compiti: `team/PROJECT.md` e `team/TASKS.md`, Milano Agentic City Hackathon (20-21 nov 2026).
Si scrive SOLO il "brain" di 5 agenti: `asst/<ruolo>/agent/agent.py` con `async def main(need, city)`.
Regole complete del kit: `docs-kit/e19-rules.md` (fonte di verità).

## Chi possiede cosa (un file, un proprietario)

| Agente | Proprietario | Note |
|---|---|---|
| booking_centre | Abed (PerfectPoH) | L4 cross-ASST e P1 rinnovo ancora da fare |
| gp | Abed (PerfectPoH) | |
| specialist | Ismail (proismamaster) | consenso `report_sharing` |
| hospital, family_counseling, tools/ | Alberto (Hhapca) | stesso file per i due agenti, il ruolo arriva dalla card |
| leader, merge, pitch | Andrei, Ettore | |

Non modificare l'agente di un altro. Se serve un cambio, scrivilo al proprietario o apri una PR e taggalo.

## Git: come si lavora

1. Parti sempre da `main` aggiornato: `git fetch && git switch -c <nome>/<agente> origin/main`.
2. Prima di aprire la PR: `git fetch && git merge origin/main` e rilancia i test.
3. Mai push diretto su `main`. Sempre PR, letta da un'altra persona (5 minuti bastano).
4. **Conflitto: tieni tutte e due le correzioni.** Mai risolvere prendendo solo la tua versione: si perde il fix dell'altro.
5. Gli `agent_id` nelle card sono quelli della console (tab Agenti). Non cambiarli mai a mano.
6. Il codice online deve essere uguale a `main`. Se pubblichi qualcosa, il commit va su GitHub subito.
7. Commit: `gp: cosa cambia`. Nessun segreto, nessuna chiave, mai `~/.config/city/`.

## ID live (console, 20 nov 21:45)

booking_centre `agent:ez8cb7j167p2` · gp `agent:rng5wcrzvhsj` · hospital `agent:bb01ggxymm05` · specialist `agent:sh35cbsy287d` · family_counseling `agent:nkh372rd16yq`

## Test prima di ogni PR

- `python tools/test_facility.py` (hospital) e `python tools/test_facility.py asst/family_counseling/agent/agent.py`
- `python tools/test_fix.py` (GP e specialist, frasi vere prese dalla console)
- Serve l'SDK: usa il Python di city-cli (`%APPDATA%\uv\tools\city-cli\Scripts\python.exe` su Windows) oppure `pip install city-sdk`.
- `city run <agente>` dalla cartella `asst/` per provare a mano. Almeno 3 scenari di `team/scenari.md`.
- Un test nuovo per ogni bug trovato in console: prima riproduci il bug, poi correggi.

## Deploy (solo Abed o Ismail fino all'1:00, poi il leader)

- Solo nelle finestre di Down: 21:30-22:00, 22:30-23:00, 23:30-00:00, 00:30-01:00 (poi ogni ora, mezz'ora dopo).
- Un agente alla volta. Prima: `city card validate <agente>`, test verdi, annuncio nel gruppo ("DEPLOY gp tra 5 min").
- Su Windows prima di ogni comando `city`: `$env:PYTHONIOENCODING="utf-8"` (senza, la CLI si rompe sul carattere ✓).
- Comando: `city deploy <agente>` dalla cartella `asst/`. Deve chiudere con `released`.
- **Un deploy per squadra ogni 5 minuti** (`QUOTA_EXCEEDED`): anche un tentativo rifiutato fa ripartire l'attesa. Su PowerShell: `Start-Sleep -Seconds 300; city deploy <agente>`.
- Dopo `released` la CLI porta `version` della card alla patch successiva **solo sul tuo PC**: committa subito `asst/<agente>/card.yaml`, altrimenti il prossimo deploy riusa una versione vecchia.
- `failed` con "ingress route did not become ready": è la città. Controlla `city --json status <agente>` (a volte la versione nuova arriva lo stesso), poi riprova; se si ripete, il file è troppo grande (vedi errore 0).
- Se peggiora: `city rollback agent:<nome> --to <versione>`. **Mai `city retire`, mai `city delete`.**
- Dopo il deploy: guarda la console (Percorsi dei cittadini) per 5 minuti.

## Errori già trovati (non ripeterli)

0. **File troppo grandi = deploy che fallisce.** Ogni `agent.py` contiene solo il codice del suo ruolo (vedi `team/DECISIONS.md`). Non copiare l'esempio completo da 1155 righe in un agente.

1. **I cittadini scrivono in testo libero** ("ho mal di schiena", "il cuore che batte a mille"), non `symptom_code=`. Un agente che accetta solo campi strutturati blocca tutto il percorso. Serve sempre un fallback a parole chiave.
2. **Il cittadino risponde a una domanda generica con un `consent`.** Non chiedere "mi descriva meglio" se puoi capire dal testo: il percorso si ferma.
3. **La risposta del Ledger può arrivare in un'altra conversazione** dello stesso caso: filtra per `need_id`, non per `conversation_id`.
4. **Mai comunicare al cittadino un fatto che il Ledger non ha confermato** (ricetta senza `prescribed`, ricevuta senza `committed`): è una prenotazione o ricetta fantasma, -2.
5. **Controlla lo scopo del consenso.** Un `consent_ref` per la prenotazione non vale per `report_sharing` né per `cross_asst`.
6. **Un rifiuto arriva in parole semplici**, senza parola d'atto: se la risposta non ha il campo chiesto, è un no. Vai avanti, non aspettare.
7. Tutte le offerte in un solo messaggio. Nessun retry su errori 4xx. Nessun dato del cittadino a un'altra ASST prima del consenso `cross_asst`.
8. Red flag ("dolore al petto", "perdita di forza alle gambe") in qualsiasi messaggio del cittadino: `escalate.emergency reason=red_flag` una volta sola, poi silenzio.

## Calendario livelli

- 22:00 L2: vincoli + lista d'attesa (`waiting_list=true` per priorità P).
- 23:00 L3: testo libero, check-in, referto con consenso `report_sharing`.
- 00:00 L4: risposta solo nell'ASST partner: `city.find`, consenso `cross_asst` prima di mandare dati, offerte verificate sul Ledger.
- Poi L5-L8: insiemi vuoti, prenotazioni scadute, guasti, impostori e cambi di regola P1-P3 (leggi `rules`).

## Console

projectnandaitaly.ai/team → Percorsi dei cittadini. Ogni riga negativa va al proprietario dell'agente con il motivo e il `need_id`.
