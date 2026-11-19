# Centro prenotazioni (booking centre)

Create la cartella dell'agente:

```bash
city init agent booking_centre
```

Impostate `role` e `capabilities` in `card.yaml` (e lo stesso `role: booking_centre` in `city.yaml`):

```yaml
role: booking_centre
capabilities:
  - booking_centre
```

## Cosa fa già l'esempio di partenza

1. Controlla che la ricetta sia valida chiedendo `prescription prescription_number=...` al Ledger.
2. Chiede al cittadino eventuali consensi e preferenze (giorni, genere del medico).
3. Propone gli slot trovati con `world` entro la scadenza prevista dalla priorità, cercando nelle altre ASST solo se nella propria non c'è disponibilità.
4. Chiede alla struttura (`facility`) di confermare il posto e gira al cittadino la ricevuta `booking.receipt`.

## Comandi per il Ledger

- `prescription prescription_number=...` per verificare la ricetta
- `world` (con filtri opzionali `procedure=`, `facility=`, `day=`, `page=`) per consultare medici e slot della vostra ASST
- Nota sulle prenotazioni: `hold` e `commit` sul Ledger li esegue l'agente `facility`, non il centro prenotazioni. Voi coordinate la scelta e consegnate la ricevuta finale al cittadino.

Per approfondire: [templates/agent/SKILL.md](../../templates/agent/SKILL.md) e le [regole del care journey](e19-rules.md).
