#!/bin/sh
# Applica le migrazioni, poi esegue il comando ricevuto.
#
# Le migrazioni girano qui e non dentro l'applicazione perche' devono essere
# terminate PRIMA che il servizio accetti richieste, e perche' cosi' un comando
# una tantum (`docker compose run --rm app python sender.py sync-topics`) trova
# lo schema aggiornato senza avviare il server.
#
# `--workers 1` e' implicito in `sender.py serve` e non e' negoziabile: lo
# scheduler e' in-process, e due worker eseguirebbero il ciclo orario due volte
# raddoppiando la spesa.
set -e

# `hash-password` e' l'eccezione, e la ragione e' circolare: applicare le
# migrazioni carica la configurazione, che in produzione PRETENDE
# ADMIN_PASSWORD_HASH — cioe' esattamente il valore che quel comando serve a
# generare. Senza questa riga il primo comando della procedura di installazione
# non puo' funzionare.
case "$*" in
  *hash-password*)
    exec "$@"
    ;;
esac

if [ "${SKIP_MIGRATIONS:-false}" = "true" ]; then
  echo "migrazioni saltate (SKIP_MIGRATIONS=true)"
else
  echo "applicazione delle migrazioni..."
  alembic upgrade head
fi

exec "$@"
