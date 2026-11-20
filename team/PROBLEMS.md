
# Problemi

## Aperti
- **CUP senza cross-ASST**: non usa `city.find` né il consenso `cross_asst`. Serve per L4 (00:00). Proprietario: Abed.
- **CUP senza rinnovo P1**: non gestisce `PRESCRIPTION_EXPIRED`.
- **LLM di Abed non su GitHub**: ha scritto di aver collegato Gemma, ma in repo non c'è `city.llm`.
- **city-cli su Windows**: si rompe stampando ✓ (`UnicodeEncodeError cp1252`). Soluzione: `PYTHONIOENCODING=utf-8`. Il primo `city deploy gp` (21:38) è rimasto senza output per 7 minuti ed è stato fermato.

## Risolti (in PR #6, da pubblicare)
- **GP fermo sul testo libero** (11 percorsi su 12): la tabella `_KEYWORDS` dell'esempio era stata tolta. Ripristinato il fallback a parole chiave.
- **Specialist senza consenso del referto**: ora chiede `report_sharing`, usa solo un consenso con quello scopo, archiviazione senza condivisione se il cittadino rifiuta.
- **`main` con gli ID vecchi**: sistemato dalla PR #5.
