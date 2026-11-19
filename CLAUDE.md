# MACH Hackathon — istruzioni per Claude Code (leggile prima di fare qualsiasi cosa)

Squadra di 5 persone. Si gareggia al Milano Agentic City Hackathon (20-21 nov 2026).
Si scrive SOLO il "brain" di 5 agenti: `asst/<ruolo>/agent/agent.py` con `async def main(need, city)`.

## Regole ferree
- Regole complete: `docs-kit/e19-rules.md` (fonte di verità). Leggile quando serve.
- Nel brain si importa SOLO `city_sdk.city` + libreria standard. Niente altri pacchetti, niente socket/HTTP.
- Mai file di dati nel Dockerfile. Mai toccare `Dockerfile` e `city.yaml` (solo `role`).
- Mai committare `~/.config/city/` o chiavi LLM. Mai `city retire`.
- Nessuna diagnosi né dosi. Nessun dato di un paziente in messaggi ad altri.
- Messaggi: parola d'atto + token `chiave=valore`, 1-2000 caratteri.
- NON si fa `city deploy`: pubblica solo il Leader (annuncia nel gruppo prima).

## Proprietà dei file (un file, un proprietario)
- booking_centre -> Tecnico A | gp + specialist -> Tecnico B | hospital + family_counseling + tools/ -> Tecnico C
- Leader: integrazione, deploy, tools/rules_helpers.py, tools/guard.py
- Lavora sul tuo branch (`git checkout -b <nome>/<agente>`), commit tipo `gp: legge protocolli da world`, poi pull request verso `main`. Non modificare agenti di altri.

## Esempio di riferimento
`reference/esempio_care_protocol_agent.py` = percorso di cura completo (prescribe, offer, hold, commit, check-in, report). Partire da lì, non dallo scaffold.

## Test locale
`city run asst/<ruolo>` (chat: citizen / agent / ledger). Almeno 3 scenari di `team/scenari.md` prima di aprire una PR.
