# Journal (la voce più recente in alto)

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
