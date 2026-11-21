// Misura i tempi di una struttura (consultorio, ospedale, specialist) dai messaggi della console.
//
// Uso: apri https://projectnandaitaly.ai/team (gia' loggato), incolla tutto il file nella console del
// browser e lancia, ad esempio:
//     await misura('agent:nkh372rd16yq')                      // consultorio, finestre di 2 ore
//     await misura('agent:nkh372rd16yq', { bucketHours: 1 })  // finestre di un'ora
// Restituisce { fasi, esiti, eventi } e stampa le tabelle (mediana e p90 in secondi, n = eventi).
//
// Le tre fasi sono separate (21/11, console):
//  - PRIMA OFFERTA, dal primo messaggio del cittadino: nostro ritardo prima di chiedere al Ledger
//    (msg_a_ledger), risposta del Ledger a agenda e world (ledger), nostro ritardo dopo la risposta
//    (risposta_a_offerta), totale.
//  - HOLD: nostro ritardo dal confirm all'hold (confirm_a_hold), risposta del Ledger (hold_a_held).
//  - COMMIT: nostro ritardo da `held` al commit (held_a_commit: e' quello che decide lo STALE_FENCE),
//    risposta del Ledger (commit_a_esito), poi la ricevuta (committed_a_ricevuta).
// "Nostro ritardo" parte da accepted_at del messaggio che riceviamo: comprende il push del Relay.

window.misura = async function misura(agentId, { bucketHours = 2, max = 4000 } = {}) {
  const enc = encodeURIComponent(agentId);
  let all = [], before = null;
  while (all.length < max) {
    const r = await fetch(`/v1/team/agents/${enc}/messages?limit=100${before ? '&before=' + encodeURIComponent(before) : ''}`,
                          { credentials: 'include' });
    if (!r.ok) break;
    const j = await r.json();
    all.push(...j.messages);
    before = j.next_before;
    if (!before) break;
  }
  const ME = agentId, LEDGER = 'city:ledger';
  const txt = m => (m.envelope.body && m.envelope.body.text) || '';
  const head = m => txt(m).split(/\s/)[0];
  const T = m => Date.parse(m.envelope.sent_at), A = m => Date.parse(m.accepted_at);
  const secs = (a, b) => Math.round((a - b) / 1000);
  const ms = all.slice().sort((a, b) => T(a) - T(b));
  const byNeed = {};
  for (const m of ms) (byNeed[m.envelope.need_id || ''] = byNeed[m.envelope.need_id || ''] || []).push(m);
  const eventi = [];
  const add = (fase, at, valore, need) => { if (valore !== null && valore >= 0) eventi.push({ fase, at, valore, need: need.slice(-9) }); };
  const esiti = {};

  for (const [need, list] of Object.entries(byNeed)) {
    const citizenMsg = list.find(m => m.sender.startsWith('citizen:'));
    // Prima offerta (un caso di accesso diretto: il primo messaggio e' del cittadino).
    if (citizenMsg) {
      const req = list.find(m => m.sender === ME && m.recipient === LEDGER && T(m) >= A(citizenMsg));
      const reply = req && list.find(m => m.sender === LEDGER && /^(slots|agenda)$/.test(head(m)) && T(m) >= T(req));
      const offer = list.find(m => m.sender === ME && m.recipient.startsWith('citizen:') && /^offer/.test(head(m)));
      if (req && reply && offer) {
        const at = citizenMsg.envelope.sent_at;
        add('msg_a_ledger', at, secs(T(req), A(citizenMsg)), need);
        add('ledger', at, secs(T(reply), T(req)), need);
        add('risposta_a_offerta', at, secs(T(offer), A(reply)), need);
        add('prima_offerta_totale', at, secs(T(offer), T(citizenMsg)), need);
      }
    }
    for (let i = 0; i < list.length; i++) {
      const hold = list[i];
      if (!(hold.sender === ME && hold.recipient === LEDGER && /^hold$/.test(head(hold)))) continue;
      const at = hold.envelope.sent_at;
      const confirm = [...list.slice(0, i)].reverse().find(m => m.sender !== ME && m.sender !== LEDGER && /\bconfirm\b/.test(txt(m)));
      if (confirm) add('confirm_a_hold', at, secs(T(hold), A(confirm)), need);
      const reply = list.slice(i + 1).find(m => m.sender === LEDGER && (/^held$/.test(head(m)) || /^refused hold/.test(txt(m))));
      if (!reply) continue;
      add('hold_a_held', at, secs(T(reply), T(hold)), need);
      if (!/^held$/.test(head(reply))) {
        const code = (txt(reply).match(/code=(\S+)/) || [, '?'])[1];
        esiti['hold ' + code] = (esiti['hold ' + code] || 0) + 1;
        continue;
      }
      const holdId = (txt(reply).match(/hold_id=(\S+)/) || [])[1];
      const commit = list.slice(i + 1).find(m => m.sender === ME && m.recipient === LEDGER && /^commit$/.test(head(m)) && txt(m).includes(holdId));
      if (!commit) { esiti['held senza commit'] = (esiti['held senza commit'] || 0) + 1; continue; }
      add('held_a_commit', at, secs(T(commit), A(reply)), need);
      const result = list.slice(list.indexOf(commit) + 1).find(m => m.sender === LEDGER && (/^committed$/.test(head(m)) || /^refused commit/.test(txt(m))));
      if (!result) { esiti['commit senza esito'] = (esiti['commit senza esito'] || 0) + 1; continue; }
      add('commit_a_esito', at, secs(T(result), T(commit)), need);
      if (/^committed$/.test(head(result))) {
        esiti['committed'] = (esiti['committed'] || 0) + 1;
        const receipt = list.find(m => m.sender === ME && /^booking\.receipt$/.test(head(m)) && T(m) >= T(result));
        if (receipt) add('committed_a_ricevuta', at, secs(T(receipt), A(result)), need);
      } else {
        const code = (txt(result).match(/code=(\S+)/) || [, '?'])[1];
        esiti['commit ' + code] = (esiti['commit ' + code] || 0) + 1;
      }
    }
  }
  const bucket = at => { const d = new Date(at); d.setUTCMinutes(0, 0, 0); d.setUTCHours(Math.floor(d.getUTCHours() / bucketHours) * bucketHours); return d.toISOString().slice(5, 16).replace('T', ' ') + 'Z'; };
  const quant = (a, p) => a.slice().sort((x, y) => x - y)[Math.min(a.length - 1, Math.floor(a.length * p))];
  const gruppi = {};
  for (const e of eventi) ((gruppi[e.fase] = gruppi[e.fase] || {})[bucket(e.at)] = gruppi[e.fase][bucket(e.at)] || []).push(e.valore);
  const fasi = [];
  for (const [fase, per] of Object.entries(gruppi))
    for (const [finestra, v] of Object.entries(per).sort())
      fasi.push({ fase, finestra, n: v.length, mediana_s: quant(v, 0.5), p90_s: quant(v, 0.9) });
  fasi.sort((a, b) => (a.fase < b.fase ? -1 : a.fase > b.fase ? 1 : a.finestra < b.finestra ? -1 : 1));
  console.table(fasi);
  console.table(Object.entries(esiti).map(([esito, n]) => ({ esito, n })));
  return { fasi, esiti, eventi };
};
