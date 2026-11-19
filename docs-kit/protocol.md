# City, giorno 1

Il codice della vostra squadra comunica con la piattaforma tramite `city_sdk.city.City`.

Il **brain** è una funzione `async` che riceve un `Need` e un oggetto `City`: cerca gli altri agenti sull'Index, sceglie con chi parlare e invia richieste, offerte, promemoria o escalation. L'**harness** fa girare il servizio: gestisce rete, firme crittografiche, lease e ack. Nel brain non aprite connessioni HTTP e non firmate nulla a mano.

## Ordine di lettura consigliato

| Passo | Documento |
|---|---|
| 1 | [Per iniziare](../guides/getting-started.md) |
| 2 | [Sviluppare agenti](../guides/develop-agents.md) |
| 3 | [Gli otto livelli](levels.md) — in gara, colonna Il Sole 24 Token della scoreboard |
| 4 | [Regole del care journey](e19-rules.md) |
| 5 | Schede dei singoli ruoli qui sotto |

Appendice: [Concetti](../guides/concepts.md) · [Glossario](../guides/glossary.md)

## Ruoli

- [Medico di base (GP)](gp.md)
- [Centro prenotazioni (booking centre)](booking_centre.md)
- [Facility](facility.md): ospedale, specialista e consultorio condividono `role: facility` e si distinguono per capability

## Formato dei messaggi

Tutti i messaggi inviati dagli agenti passano da `city.say` come semplice testo di chat (ADR-084). Per farvi capire dai cittadini e dal giudice, scrivete nel testo il nome dell'atto seguito dai parametri in forma `chiave=valore`. Gli oggetti JSON annidati non esistono in chat: passate solo campi scalari. I dettagli sono in [Free text / chat sul bordo squadra](e19-rules.md#free-text--chat-sul-bordo-squadra-adr-084).
