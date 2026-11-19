# Medico di base (GP)

Create la cartella dell'agente:

```bash
city init agent gp
```

Impostate `role` e `capabilities` in `card.yaml` (e lo stesso `role: gp` in `city.yaml`):

```yaml
role: gp
capabilities:
  - gp
```

## Cosa fa già l'esempio di partenza

1. Rifiuta le richieste di pareri medici, diagnosi o dosaggi sollevando `OutOfScope`.
2. Davanti a una red flag o a un'emergenza invia `escalate.emergency reason=red_flag` al cittadino e si ferma.
3. Cerca il sintomo nella tabella di protocollo (letta dal Ledger con `world` o dalla copia locale di riferimento).
4. Emette la ricetta scrivendo `prescribe patient=... procedure=... priority=...` a `city:ledger`.
5. Manda la ricetta al cittadino.

Il rinnovo di una ricetta scaduta (regola P1) è il punto in cui di solito si estende questo brain.

## Comandi per il Ledger

- `world` per leggere le righe della tabella di protocollo
- `prescribe patient=... procedure=... priority=...` per emettere una nuova ricetta
- `prescription prescription_number=...` per verificare una ricetta esistente

Per approfondire: [templates/agent/SKILL.md](../../templates/agent/SKILL.md) e [Quando il giudice valuta un journey](e19-rules.md#quando-il-giudice-valuta-un-journey-adr-119).
