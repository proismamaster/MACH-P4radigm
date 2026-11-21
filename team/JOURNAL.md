# Journal (la voce più recente in alto)

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
