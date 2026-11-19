# Facility (ospedale, specialista, consultorio)

Ospedale, specialista e consultorio condividono tutti il ruolo `facility`: quello che cambia da uno all'altro è il servizio dichiarato in `capabilities`. Create le tre cartelle e impostate `role: facility` sia in `card.yaml` sia in `city.yaml`.

```bash
city init agent hospital
city init agent specialist
city init agent family_counseling
```

| Cartella | `capabilities` in `card.yaml` |
|---|---|
| `hospital` | `hospital.physiatry` |
| `specialist` | `specialist_care.cardiology` |
| `family_counseling` | `family_counseling.gynecology` |

## Cosa fa già l'esempio di partenza

1. Risponde alle ricerche di disponibilità offrendo i propri slot letti dal Ledger con `world`.
2. Blocca lo slot con `hold slot_id=...` e completa la prenotazione con `commit hold_id=... consent_ref=...`.
3. Registra l'arrivo del cittadino allo sportello con `checkin booking_id=... citizen=...`.
4. Per lo specialista: chiede il consenso, salva il referto sul Ledger con `report booking_id=... outcome_code=...` (aggiungendo se serve una ricetta di controllo) e avvisa il cittadino.
5. Per il consultorio: accetta l'accesso diretto senza ricetta e applica regole più strette sui dati personali.

## Comandi per il Ledger

- `world`, `hold`, `commit`, `cancel`
- `checkin`, `report`
- `prescribe ... follow_up_of=<booking_id>` quando lo specialista prescrive un controllo successivo

Per approfondire: [templates/agent/SKILL.md](../../templates/agent/SKILL.md) e [Quando il giudice valuta un journey](e19-rules.md#quando-il-giudice-valuta-un-journey-adr-119).
