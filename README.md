# MACH — repo di squadra

```
asst/        -> i 5 agenti (creati con `city init agent`, vedi SETUP sotto)
reference/   -> esempio completo e scaffold ufficiali (sola lettura)
docs-kit/    -> regole e guide del kit (sola lettura)
tools/       -> simulatore, script di deploy, helper condivisi
team/        -> scenari.md, registro-regole.md, DOMANDE.md
CLAUDE.md    -> istruzioni per Claude Code
```

## SETUP (Leader, una volta sola, dopo `city login`)
```bash
mkdir asst && cd asst
city init agent booking_centre
city init agent hospital
city init agent gp
city init agent specialist
city init agent family_counseling
```
Poi in ogni `card.yaml` / `city.yaml` imposta `role` e `capabilities`:

| Cartella | card role | capabilities | city.yaml role |
|---|---|---|---|
| booking_centre | booking_centre | booking_centre | booking_centre |
| hospital | facility | hospital.physiatry | facility |
| gp | gp | gp | gp |
| specialist | facility | specialist_care.cardiology | facility |
| family_counseling | facility | family_counseling.gynecology | facility |

(Verifica con `docs-kit/e19-rules.md`, sezione 3; la tabella dipende dal posto assegnato alla squadra: controllalo in console, Assignment.)

Poi sostituisci ogni `agent/agent.py` con `reference/esempio_care_protocol_agent.py` come punto di partenza e committa.
