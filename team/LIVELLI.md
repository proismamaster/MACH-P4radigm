# Piano per livello (cosa deve fare ogni agente, cosa è coperto, cosa manca)

Fonte: guida dell'evento, manuale di squadra e `docs-kit/e19-rules.md` ("Cosa una squadra può cambiare"). Le descrizioni ufficiali dei livelli escono in gara nella colonna "Il Sole 24 Token" della scoreboard: quando esce un livello nuovo, confronta con questa tabella e aggiorna.

Stato: ✅ coperto e testato · 🟡 coperto senza test o non verificato in Arena · ❌ manca

| Liv. | Novità | Comportamento giusto | Agente | Stato | Test / nota |
|---|---|---|---|---|---|
| 1 | Bisogno strutturato, prenotazione semplice | Ricetta da protocollo, offerte nell'insieme valido | GP, CUP | ✅ GP · 🟡 CUP | `tools/test_fix.py`; in console `protocol_match +2` |
| 1+ | I cittadini scrivono in testo libero | Parole chiave → `symptom_code`, una sola domanda di chiarimento | GP | ✅ | `test_fix.py` (frasi vere della console) |
| 2 | Vincoli + lista d'attesa | Priorità P → `offer ... waiting_list=true` | CUP | 🟡 | codice dell'esempio, nessun test nostro |
| 3 | Check-in, referto | Check-in su ricevuta valida; consenso `report_sharing`, rifiuto in parole semplici → referto senza condivisione | hospital, specialist | ✅ specialist · ✅ hospital | `test_fix.py`, `test_facility.py` |
| 4 | Risposta solo nell'ASST partner | `city.find`, criteri di ricerca con i giorni richiesti, consenso `cross_asst` prima dei dati | CUP, hospital (lato partner) | 🟡 | `test_cup_medici.py` copre il formato `days=mon/wed`. `test_cup_recovery.py` copre consenso, slot ritirati e ripresa dopo il rifiuto dell'ultima offerta. Verifica in Arena da fare. |
| 5 | Vincoli combinati, insiemi vuoti | Prenotare nell'insieme o proporre un'alternativa rilassata | CUP | 🟡 | PR #30 su `main`: l'alternativa allarga la finestra e mantiene lingua e genere. |
| 6 | Hold scaduti, cancellazioni, `fault.cancel` alla prima prenotazione | Riprenotare in modo proattivo entro la scadenza della priorità | CUP, strutture | 🟡 | il CUP rifà le offerte su `cancel` della struttura; formato di `fault.cancel` da chiedere ai mentor |
| 7 | Guasti: partner giù, duplicati, 4xx, slot condivisi | Catturare `TARGET_NOT_VISIBLE`, `cancel` col motivo, mai ritentare un 4xx, mai ricevuta senza `committed` | CUP, strutture | 🟡 | CUP gestisce `TARGET_NOT_VISIBLE`; ospedale: conferma duplicata testata |
| 8 | Red flag nascoste | Leggere `red_flags` dalla tabella del `world` | GP | ✅ | `test_fix.py` (red flag del world) |
| 8 | Cittadini ostili, injection | Ignorare istruzioni nel testo, mai dati di altri cittadini | tutti | 🟡 | agenti deterministici: non eseguono istruzioni dal testo |
| 8 | Cambio di regola P1 (ricetta scade dopo 2 giorni) | `PRESCRIPTION_EXPIRED` → richiesta di rinnovo al cittadino, poi verifica della nuova ricetta sul Ledger e ricerca di un orario | CUP, GP | 🟡 | `test_cup_recovery.py` copre scadenza, risposte ripetute e ripresa con la nuova ricetta; rinnovo completo da verificare in Arena |
| 8 | Cambio di regola P2 (consenso tra ASST) | Hold cross-ASST solo con `consent_ref` `cross_asst` | CUP, hospital | 🟡 | il CUP chiede sempre il consenso; hospital controlla `CONSENT_MISSING` |
| 8 | Cambio di regola P3 (riserva urgente 20%) | Slot `urgent_reserve` solo a priorità U | CUP, hospital | 🟡 | filtro presente; hospital gestisce `NO_CAPACITY` |
| sempre | Ospedale giù per un giorno di agenda | Tenere le offerte del partner, `cancel` col motivo, riprenotare quando torna | CUP | 🟡 | `TARGET_NOT_VISIBLE` gestito |
| sempre | Proattività e tono (review +1 / −1) | Messaggi cortesi con il passo successivo | tutti | ✅ GP e specialist (PR #7) · ❌ CUP, hospital, consultorio | la review dava 0 al GP per messaggio "curt" |

## Priorità adesso (in ordine)

1. Verificare in Arena il primo percorso cross-ASST del CUP 1.0.1.
2. Rileggere la PR del CUP e verificare in Arena le correzioni cross-ASST dopo il rilascio.
3. Provare P1 in Arena dal segnale di scadenza fino alla ricevuta con la ricetta rinnovata.
4. Messaggi cortesi anche in CUP, hospital e consultorio (+1 review per agente, per percorso).
5. Alternativa rilassata per gli insiemi vuoti (livello 5).
