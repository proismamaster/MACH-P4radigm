# Stato del progetto (leggilo per primo)

> Milano Agentic City Hackathon, squadra p4radigm: 5 agenti di una ASST simulata. Gara dal 20/11 21:00 al 21/11 16:00.

## Stato attuale (21/11 ore 13:10 locali, 12:10 UTC) — punto comune della squadra

- **Classifica:** 18° (livello 8, punteggi nascosti fino alla finale). Stop del codice alle 16:00.
- **Online** (tutti `promoted PASS`, tabella con deployment e rollback in `team/RILASCI.md` → "Online ora"): CUP 1.0.27 (#118, **senza** la #119), GP 1.0.7, ospedale 1.0.7, specialist 1.0.8 (regola P2), consultorio 1.0.14. CUP e GP: un pod, concorrenza 32 (era 8). Ogni card su `main` è un numero avanti (CUP 1.0.28, GP 1.0.8, ospedale 1.0.8, specialist 1.0.9, consultorio 1.0.15).
- **`main` verificato alle 11:45 UTC:** 31 file di test su 31 verdi, i cinque agenti compilano, cinque card valide.
- **Dove si perdono i punti (misure dalla console):** GP +2 a quasi ogni percorso; il CUP prende -1 (`no_booking`) quando la prenotazione non arriva in fondo e le strutture fanno 0. Cause misurate: il cittadino conferma 19 ore d'agenda dopo l'offerta (mediana, 3-35), quindi gli slot vicini sono già passati; rifiuti per scadenza, genere e giorno; Ledger lento (5-9 minuti per risposta, hold di circa 2 minuti).
- **Correzioni online di oggi:** CUP con 5 offerte varie, controllo dei tempi della conferma, partner verificati (la #119, slot B ad almeno 20 ore, è stata tolta alle 12:07 UTC: raddoppiava i rifiuti per scadenza); GP che aspetta `prescribed` fino a 90 s; specialist con referto senza consenso, rifiuti tardivi e commit tardivi; ospedale e consultorio con attesa paziente del Ledger e stato letto dalla cronologia dopo un rilascio.
- **Aperti:**
  - consultorio: `_MIN_LEAD` 10 ore, troppo vicino (5 cancel `past` su 6 conferme alle 10-11 UTC) — Hapca;
  - partner: rispondono quasi sempre `no_availability` mentre i verdetti contano 130-650 posti validi (ipotesi: `earliest`/`deadline` MACH-1.4 letti in un'altra base oraria) — da verificare dal vivo;
  - impostori: il filtro è nella #118 (online).
  - **regola P2 in vigore** (agenda 29/12 08:00, annuncio delle 13:01): CUP chiede il consenso `cross_asst` prima di ogni conferma a un partner; ospedale, consultorio e specialist (1.0.8) fanno l'hold cross-ASST con quel consenso. Nella ricerca ai partner vanno solo criteri (mai `citizen` o `prescription_number`).
  - **ondate:** alle 11:31 UTC ~60 cittadini al CUP insieme, 37 senza risposta con concorrenza 8. Da verificare alla prossima ondata con concorrenza 32. Ogni rilascio perde i messaggi che arrivano durante il cambio di pod: rilasciare solo se serve.
- **Regola dei rilasci (dopo il doppio build CUP 1.0.26 delle 11:16-11:18):** prima di `city deploy` si scrive nel gruppo "rilascio <agente> <versione>", si fa `git pull`, si controllano `/v1/team/deployments` e l'ultima riga di `team/RILASCI.md`; nessun altro rilascia finché non c'è la riga nuova. Un agente alla volta, almeno 90 s tra due deploy.

## Dove trovare cosa

| File | Cosa contiene |
|---|---|
| `AI.md` | Regole per tutti: git, test, deploy, errori da non ripetere |
| `team/TASKS.md` | Chi fa cosa adesso |
| `team/PROBLEMS.md` | Bug aperti e risolti |
| `team/DECISIONS.md` | Scelte tecniche e perché |
| `team/JOURNAL.md` | Diario delle sessioni, la più recente in alto |
| `team/scenari.md` | Casi di test da provare a mano |
| `team/registro-regole.md` | Cambi di regola visti in gara |
| `docs-kit/` | Regole ufficiali del kit (sola lettura) |
