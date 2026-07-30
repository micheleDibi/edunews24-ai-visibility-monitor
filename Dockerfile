# syntax=docker/dockerfile:1.7

# =============================================================================
# Stadio 1 — build del frontend
# =============================================================================
FROM node:20-alpine AS frontend

WORKDIR /build

# Prima solo i manifest: se le dipendenze non cambiano, questo strato resta in
# cache e `npm ci` non viene rieseguito a ogni modifica del codice.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Si costruisce in `dist/` e non nel default (`../app/static`), che qui non
# esiste: lo stadio Python lo copia da solo.
RUN VITE_OUT_DIR=dist npm run build


# =============================================================================
# Stadio 2 — dipendenze Python
# =============================================================================
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# `build-essential` serve solo a compilare argon2-cffi e asyncpg se non ci sono
# wheel per l'architettura: sta in questo stadio e non finisce nell'immagine.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
COPY app/__init__.py ./app/
RUN pip install --no-cache-dir .


# =============================================================================
# Stadio 3 — runtime
# =============================================================================
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    TZ=Europe/Rome

# Utente non root. Creato prima di copiare, cosi' `--chown` funziona.
RUN groupadd --system --gid 1001 monitor \
 && useradd --system --uid 1001 --gid monitor --home-dir /app --no-create-home monitor

WORKDIR /app

# Solo le librerie installate, non la toolchain di compilazione.
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=monitor:monitor app/ ./app/
COPY --chown=monitor:monitor alembic/ ./alembic/
COPY --chown=monitor:monitor sql/ ./sql/
COPY --chown=monitor:monitor alembic.ini pricing.yaml sender.py pyproject.toml ./
COPY --chown=monitor:monitor docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Il build del frontend dove FastAPI lo serve.
COPY --from=frontend --chown=monitor:monitor /build/dist ./app/static

USER monitor

EXPOSE 8000

# `curl` non c'e' nell'immagine slim e installarlo per un healthcheck sarebbe
# superficie in piu': si usa la libreria standard di Python.
#
# La porta si legge da PORT invece di essere fissata a 8000: con un valore
# scritto a mano, cambiare PORT nel .env avrebbe reso il container
# permanentemente `unhealthy` mentre il servizio funzionava.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request;p=os.environ.get('PORT','8000');sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/api/health',timeout=4).status==200 else 1)"]

# L'entrypoint applica le migrazioni, poi passa il comando.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "sender.py", "serve"]
