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

if [ "${SKIP_MIGRATIONS:-false}" = "true" ]; then
  echo "migrazioni saltate (SKIP_MIGRATIONS=true)"
else
  echo "applicazione delle migrazioni..."
  alembic upgrade head
fi

exec "$@"
