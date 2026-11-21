# Revisione del codice — 21/11 ore 06:35, aggiornata alle 08:40 (Alberto, con Claude)

Base: `main` a f72ce63. Online: CUP 1.0.23, **GP 1.0.5 (08:29, contiene f72ce63)**, consultorio 1.0.8, ospedale 1.0.4, specialist 1.0.4. CUP 1.0.24, ospedale 1.0.5 e consultorio 1.0.9 alle 10:00 (Andrei).
Fonte dei fatti: percorsi di `/v1/team/journeys/<need_id>`, messaggi di CUP, GP e consultorio da `/v1/team/agents/<id>/messages` (21/11 04:18-05:15 UTC), scoreboard, test in `tools/`, protocollo MACH-1.3.

Legenda: ✅ gestito e provato (test o console) · 🟡 gestito ma non provato in Arena · ❌ non gestito / bug noto.

## 1. La causa principale, confermata (05:00-05:15 UTC)

| Fatto | Misura | Fonte |
|---|---|---|
| Il Ledger risponde tardi | agenda p50 537 s, ricetta p50 540 s, world p50 478 s (35 richieste del CUP); stesso ritardo per GP (`world`, `prescribe` 440-470 s) e consultorio (`hold`, `commit`, `agenda` 445-585 s) | messaggi degli agenti |
| La risposta del Ledger apre il nostro turno tardi | dopo un `slots`/`agenda`/`prescription` il CUP agisce 360-450 s dopo, senza altri messaggi in mezzo | messaggi del CUP |
| Il GP non è in coda per colpa sua | 34 messaggi su 221 a meno di 1 s l'uno dall'altro; 35-49 messaggi ogni 10 minuti | messaggi del GP |
| I cittadini rispondono presto | offerta → risposta in 4-5 minuti | percorsi |
| Il ritardo è cominciato alle 04:10 UTC | GP: p50 22 s alle 03:40, 246 s alle 04:10, 338 s alle 04:20 | percorsi |
| Tutte le squadre salgono piano | +29 / +95 punti in 4 minuti, noi 2848 (18° su 26) | `/v1/scoreboard` |

Conclusione: ogni passaggio (noi → Ledger → noi, noi → struttura) costa oggi 6-9 minuti reali, cioè 6-9 ore d'agenda. Il numero di passaggi decide quante prenotazioni restano dentro la finestra B (48 ore dalla nascita del need).

Sprechi nostri, confermati:
- **GP**: aspettava il `world` prima di ogni ricetta. 84 risposte `world` su 84 erano una pagina di slot, senza tabella dei protocolli né red flag. Costo: un giro di Ledger per cittadino.
- **CUP**: chiedeva ricetta + agenda, poi il world, poi una pagina alla volta: 2-4 giri prima della prima offerta.
- **CUP → partner**: 550 ricerche in 26 minuti (22 × 25 partner), ~500 risposte (315 `no_availability`, 99 "Ricevuto"), ognuna un turno con fino a 7 letture della cronologia. 45 offerte da 7 partner, 1 arrivata a un cittadino, 0 confirm ai partner.
- Lo scale a concorrenza 8 (05:48) non ha cambiato i tempi: il collo di bottiglia non era il pod.

## 2. Correzioni in `main` (GP online dalle 08:29, il resto alle 10:00)

| Commit | Agente | Cosa | Effetto stimato con il ritardo di oggi |
|---|---|---|---|
| f72ce63 | GP | il `world` letto per un cittadino vale 10 minuti per tutta l'ondata: la ricetta parte al primo turno | -1 giro (~14 ore d'agenda) per ogni percorso |
| f72ce63 | CUP | agenda e pagine condivise per ondata (5 minuti); ricetta, agenda e pagina 1 nello stesso turno; pagine mancanti 6 alla volta | prima offerta dopo 1 giro invece di 2-4 |
| f72ce63 | CUP | al massimo 6 partner per ricerca (prima quelli che offrono); solo il turno che manda le ricerche aspetta | ~4 volte meno traffico e turni |
| f72ce63 | consultorio | agenda e pagina 1 condivise per ondata, anche per le ricerche degli altri CUP (MACH-1.3: 10 s) | prima offerta senza giro di Ledger |
| e2d1518 | CUP, consultorio | anticipo minimo 10 ore (U 4), margine 1 ora al confirm | simulazione: 19/21 prenotati invece di 14/21 |
| b5dcb99 | consultorio, ospedale, CUP | finestra MACH-1.3 (`earliest=`/`deadline=`), B senza preferenza a 30 ore, R7 slot passati al confirm | — |

Prove: 21 file di test verdi (nuovo `tools/test_cup_ritardo.py`, `test_gp_l8.py` esteso), `test_facility` verde su consultorio e ospedale. Conformance locale: fallisce solo `custody.ack`, come per l'agente di riferimento del kit (JOURNAL 02:45); la conferma vera è al deploy.

Rischi noti delle correzioni:
- Pagine condivise vecchie fino a 5 minuti: uno slot preso nel frattempo viene rifiutato dalla struttura e il CUP propone il successivo.
- Se il Ledger mettesse red flag nel `world` a metà ondata, il GP le vedrebbe entro 10 minuti (non subito).

## 3. Problemi aperti

| # | Stato | Problema | Nota |
|---|---|---|---|
| 3.1 | ❌ | Con 6-9 minuti per passaggio una B (48 ore) non entra: GP ~3 passaggi, CUP 2-6, confirm → ricevuta 5-6 | dipende dalla piattaforma; le correzioni tolgono 2-4 passaggi |
| 3.2 | 🟡 | La scadenza B/D del CUP parte da "messaggio al CUP − 21 ore": se il GP risponde tardi la stima è troppo avanti | con il GP al primo turno l'errore si riduce |
| 3.3 | 🟡 | hold → commit: due giri di Ledger obbligati (il commit vuole `hold_id` e `fence` del `held`) | non si può accorciare |
| 3.4 | 🟡 | Elenco del ring incompleto; riga `facts` MACH-1.3 da postare su Discord | Alberto |
| 3.5 | ❌ | `test_facility` non vale per lo specialist (48 fallite, file non toccato) | test pensato per ospedale e consultorio |

## 4. Cosa non posso confermare
- Se il ritardo di consegna sia uguale per tutte le squadre: vedo solo i nostri messaggi. Lo scoreboard dice che tutte salgono piano.
- Se il nostro traffico verso i partner contribuisca al ritardo della città.
- L'effetto reale delle correzioni: si vede solo dopo il deploy.

## 5. Piano
1. ✅ GP 1.0.5 online alle 08:29 (OK di Alberto). Alle 10:00 Andrei pubblica CUP 1.0.24 + #86, ospedale 1.0.5, consultorio 1.0.9, uno al minuto; il GP non serve.
2. Dalle 10:15: misurare in console il tempo cittadino → ricetta (GP) e need.request → prima offerta (CUP), il numero di ricerche ai partner per caso, `past`/`EXPIRED` e ricevute.
3. Cercare in console un verdetto di cardiologia con le righe dello specialist (per il follow-up).
4. Riga `facts` MACH-1.3 per ospedale, specialist e consultorio su Discord.
5. Se resta tempo: la stessa lettura condivisa nell'ospedale.
