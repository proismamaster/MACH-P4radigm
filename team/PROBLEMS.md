
# Problemi

## Aperti
- **Specialist e rinnovo P1**: lo specialist trasforma anche `PRESCRIPTION_EXPIRED` in `facility_cancelled`. Per quel percorso il CUP dipende da un segnale di scadenza del Ledger abbinabile alla ricetta. (Ismail)
- **Ospedale e consultorio, P2**: il controllo usa il vecchio formato degli ID e non riconosce alcuni agenti esterni; se manca il riferimento del consenso il codice può costruirne uno; il consultorio può riproporre lo slot appena annullato. (Alberto)
- **Specialist, follow-up**: la ricetta di controllo (`prescribe ... follow_up_of=`) non è implementata. (Ismail)
- **Deploy dello specialist**: due volte `ERROR` della città, "agent ingress route did not become ready in time (last 404, version '-')". Conformance tutta PASS. Chiesto ai mentor su Discord.
- **Messaggi persi durante i rollout**: i percorsi 32, 33, 34, 38 non hanno avuto risposta dal GP mentre cambiava versione (log della città in `503 DRAINING`). In locale il GP risponde bene.
- **LLM di Abed non su GitHub**: ha scritto di aver collegato Gemma, ma in repo non c'è `city.llm`.
- **city-cli su Windows**: si rompe stampando ✓ (`UnicodeEncodeError cp1252`). Soluzione: `PYTHONIOENCODING=utf-8`. Il primo `city deploy gp` (21:38) è rimasto senza output per 7 minuti ed è stato fermato.

## Risolti
- **CUP, rinnovo P1**: il rifiuto della struttura provocava una nuova offerta con la ricetta scaduta. Ora chiede il rinnovo una volta e rilegge sul Ledger il numero sostitutivo. (`tools/test_cup_recovery.py`, testato in locale)
- **CUP, consenso con testo iniziale**: l'atto `consent` veniva letto solo a inizio messaggio. Ora viene riconosciuto anche dopo una frase, con scopo e mittente verificati. (`tools/test_cup_recovery.py`, testato in locale)
- **CUP, slot partner ritirato durante il consenso**: il CUP ignorava il ritiro prima della conferma. Ora abbina mittente e identificativi, invalida l'offerta e ripropone gli orari ancora disponibili. (`tools/test_cup_recovery.py`, testato in locale)
- **GP, DUPLICATE annunciato senza verifica** e **rinnovo non annunciato** se c'era già una ricetta nella pratica: ora rilegge la ricetta dopo DUPLICATE e controlla per numero di ricetta. (review 22:15, test in `tools/test_fix.py`)
- **GP, red flag nascoste del livello 8**: ora legge `red_flags` dalla tabella di protocollo del `world`.
- **Specialist**: check-in con `ledger_ref`; un solo referto anche con due risposte concorrenti al consenso.
- **CUP, medico sconosciuto e lingua**: un medico fuori dalla tabella si accetta solo per cittadini che parlano italiano e senza preferenza di genere.
- **CUP, id medico fuori dalla tabella** (`D-3`): ogni orario veniva scartato, anche nella propria ASST. (PR #8, `tools/test_cup_medici.py`)
- **Messaggi "curt"**: la review dava 0 su proattività al GP. (PR #7)
- **GP fermo sul testo libero** (11 percorsi su 12): la tabella `_KEYWORDS` dell'esempio era stata tolta. Ripristinato il fallback a parole chiave.
- **Specialist senza consenso del referto**: ora chiede `report_sharing`, usa solo un consenso con quello scopo, archiviazione senza condivisione se il cittadino rifiuta.
- **`main` con gli ID vecchi**: sistemato dalla PR #5.
