# Journal (la voce più recente in alto)

## 2026-11-20 21:50 — Ismail — GP sbloccato e regole di squadra

**Fatto**
- Console: 11 percorsi su 12 fermi sul GP. Causa: il GP accettava solo `symptom_code=`, i cittadini scrivono in testo libero. Bug riprodotto con un test sull'SDK vero (`tools/test_fix.py`).
- PR #6: fallback a parole chiave nel GP, red flag su tutta la storia, ricetta solo dopo `prescribed`, specialist con consenso `report_sharing`. Conflitto con `main` risolto tenendo anche il fix della risposta del Ledger in un'altra conversazione. 19 test su 19.
- Repo organizzata: `AI.md` (regole), `team/PROJECT.md`, `team/TASKS.md`, `team/PROBLEMS.md`, `team/DECISIONS.md`, questo journal, template delle PR.

**Problemi**
- CUP senza cross-ASST e P1; LLM di Abed non su GitHub (vedi `team/PROBLEMS.md`).

**Prossimo passo**
- Controllare in console che i percorsi ripartano dopo il deploy del GP; deploy dello specialist 22:30-23:00.
