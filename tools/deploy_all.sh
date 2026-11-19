#!/usr/bin/env bash
# SOLO LEADER. Ordine: specialist prima di hospital. Un agente alla volta, controlla lo stato tra uno e l'altro.
set -e
cd "$(dirname "$0")/../asst"
for a in booking_centre gp family_counseling specialist hospital; do
  echo ">>> deploy $a"; (cd "$a" && city deploy)
  city status "agent:$a" || true
  read -p "Controlla la console 5 minuti, poi INVIO per il prossimo..."
done
