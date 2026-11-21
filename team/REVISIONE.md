# Revisione del codice — 21/11 ore 05:50 (Alberto, con Claude)

Base: `main` a 597c313. Online: CUP 1.0.23, GP 1.0.4, consultorio 1.0.8, ospedale 1.0.4, specialist 1.0.4.
Fonte dei fatti: 200+ percorsi letti da `/v1/team/journeys/<need_id>` e gli export JSON del 21/11, test in `tools/`, protocollo MACH-1.3 (Discord).

Legenda: ✅ gestito e provato (test o console) · 🟡 gestito ma non provato in Arena · ❌ non gestito / bug noto.

## 1. Il percorso, passo per passo

| Passo | Chi | Come è gestito | Stato |
|---|---|---|---|
| Primo messaggio, testo libero | GP | parole chiave → `symptom_code`, una sola domanda di chiarimento | ✅ (102 `protocol_match +2`) |
| Red flag (dolore al petto, forza alle gambe) | GP | lista fissa + parafrasi (1.0.4) + red flag del `world` con 2/3 delle parole | ✅ test_gp_l8, test_l8_ostili |
| Red flag nascosta solo nel `world` | GP | il GP aspetta il `world` 6 s e non prescrive mai senza averlo letto | 🟡 se il `world` tarda oltre 6 s il GP aspetta il turno successivo (prima restava muto: 201) |
| Ricetta solo dopo `prescribed` | GP | sì, mai annunciata prima | ✅ |
| Rinnovo P1 (`PRESCRIPTION_EXPIRED`) | CUP → GP | il CUP chiede il rinnovo, il GP emette il nuovo numero e il CUP rilegge sul Ledger | ✅ test_cup_recovery |
| Giorni e genere | CUP | `days=`, giorni scritti a parole e abbreviati (`lun/mer/ven`), rifiuti `day`/`gender` imparati, un'offerta per giorno della settimana | 🟡 i rifiuti dei cittadini non sono sempre coerenti col testo (318) |
| Finestra di priorità | CUP | B/D contate dalla ricetta (~20 ore d'agenda prima del messaggio al CUP), in giorni d'agenda | 🟡 MACH-1.3 conferma: la scadenza parte dal primo messaggio al medico |
| Anticipo degli slot | CUP, consultorio, ospedale | minimo 4 ore; preferenza 30 ore solo per D e senza priorità; per B/U il primo slot dopo le 4 ore | 🟡 |
| Partner (altre ASST) | CUP | 25 partner + `city.find`, attesa 20 s, date inoltrate in UTC con la Z | ✅ (audit `false_attribute` corretto in 1.0.23) |
| Confirm → hold → commit → ricevuta | strutture | riprova del hold su `EXPIRED`/`STALE_FENCE` (consultorio), scadenza ricontrollata al confirm (CUP) | ❌ vedi 2.1 |
| Check-in, referto, consenso `report_sharing` | ospedale, specialist | sì | ✅ test_fix, test_facility |
| Impostori, injection | consultorio (modalità sicura), CUP (#86 alle 10:00) | filtro solo su chi è fuori dal ring E sospetto | 🟡 elenco del ring incompleto |
| Cambio di regola P1/P2/P3 | tutti | `rules` riletto per P2 (consultorio), riserva U esclusa sotto U, rinnovo P1 | ✅ test_mach12_struttura |

## 2. Problemi aperti, in ordine di peso

### 2.1 ❌ Il CUP elabora il confirm 4 minuti dopo (la perdita più grande rimasta)
Console 21/11 L7-L8: 319 confirm alle 04:17:06, risposta del CUP alle 04:21:05; 310 primo confirm alle 04:02:09 mai elaborato, secondo alle 04:18:10, risposta alle 04:22:39. Quattro minuti reali sono quattro ore d'agenda: lo slot passa e arriva `slot_expired` o `facility_cancelled`. Su 61 percorsi con confirm, 2 ricevute.

Causa più probabile, non confermata: i turni del CUP sono lunghi (attesa partner 20 s, attese del Ledger fino a 6 s, paging fino a 60 s) e il pod li serve in fila. Il CUP ha 5218 messaggi.

Correzione proposta, già pronta (serve il tuo ok, il sistema l'ha bloccata): `city scale booking_centre --min 1 --max 1 --concurrency 8` (e lo stesso per `gp`). Un solo pod tiene la memoria condivisa; il codice ha già un lock per need.
Correzione nel codice per le 10:00: un turno di `confirm` non deve aspettare partner o pagine; abbassare `_PAGING_SECONDS` a 20.

### 2.2 🟡 Strutture e finestra B dei CUP esterni
Consultorio (`_LEAD` 30 h) e ospedale (`_DECISION_LEAD` 24 h) preferiscono slot lontani anche per una ricerca B di un altro CUP: oltre la scadenza vera (circa 20 ore rimaste). MACH-1.3: chi chiede manda `deadline=` e `after=` con data e ora; le strutture devono rispettarli. Oggi il consultorio legge `after=`/`before=` solo come ora del giorno (HH:MM): un `after=` con data viene ignorato senza errori.

### 2.3 🟡 Giorni e genere non dichiarati
"Solo in alcuni giorni" senza nomi: il CUP impara solo dai rifiuti. Con offerte su giorni diversi e più di una tornata può bastare; i rifiuti `day` su un giorno nominato dal cittadino (318) restano non spiegati.

### 2.4 🟡 Prima risposta delle strutture 8-14 minuti
Coincide con l'orario di chiusura (08:00-18:00 d'agenda): vale per tutte le squadre.

### 2.5 🟡 Elenco del ring
18 id nel consultorio, 17 nel CUP. Mancano CUP, GP e consultori delle altre ASST. Con la modalità sicura non blocca nessuno; per MACH-1.3 serve postare una riga `facts` per le nostre tre strutture su Discord.

## 3. Cosa non posso confermare
- I messaggi del Ledger (`held`, `refused ... code=`) non sono negli export: la causa dei 34 confirm senza risposta resta un'ipotesi (coda del CUP).
- Le soglie (20 ore d'agenda prima del CUP, 4 ore minime, 30 ore preferite) vengono dai dati di stanotte, non dal kit.

## 4. Piano per le 10:00 (dopo il freeze)
1. Scale del CUP e del GP (se approvato) — subito, non è un deploy di codice.
2. #86 di Andrei (impostori del CUP).
3. Confirm del CUP senza attese lunghe; `_PAGING_SECONDS` 20.
4. Consultorio e ospedale: rispettare `deadline=`/`after=` di MACH-1.3 e, per B, il primo slot dopo le 4 ore.
5. Riga `facts` MACH-1.3 per ospedale, specialist e consultorio su Discord.
