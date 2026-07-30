# Edunews24 AI Visibility Monitor

Misura se e quando i motori di risposta AI — ChatGPT, Perplexity, Claude —
citano `edunews24.it` quando un lettore italiano fa una domanda sui temi che il
giornale copre: scuola, università, concorsi, lavoro, ricerca.

Ogni ora genera domande realistiche in italiano derivate dal catalogo editoriale
reale, le manda in parallelo a tutti i provider configurati con la ricerca web
attiva, estrae le fonti citate e registra se `edunews24.it` compare. Il risultato
è una serie storica e una dashboard che risponde a una sola domanda operativa:
**su quali argomenti il giornale è invisibile, e quali articoli vengono
effettivamente citati.**

## Cosa NON fa

**Non aumenta le citazioni.** Mandare query a un'API non modifica l'indice di
retrieval del provider: il volume di traffico non ha alcun effetto sul
posizionamento. È uno strumento di misura, non di ottimizzazione. Il valore è il
ciclo di feedback editoriale — sapere dove si è invisibili — non il numero in sé.

Non fa scraping delle interfacce consumer, non usa proxy o user-agent
falsificati, non aggira rate limit o captcha. Solo API ufficiali con chiavi
proprie, a basso volume, dentro i termini di servizio.

---

## Avvio rapido

Servono: Docker, un progetto Supabase con la tabella degli articoli, un secondo
Postgres per il monitoraggio, e almeno una chiave API.

```bash
# 1. Il ruolo di sola lettura sul database editoriale.
#    Esegui sql/readonly_role.sql nella SQL Editor di Supabase.
#    Leggi i commenti: se `articles` ha RLS attiva serve anche la policy.

# 2. La configurazione.
cp .env.example .env
$EDITOR .env          # SOURCE_DB_URL, MONITOR_DB_URL, le chiavi API

# 3. L'hash della password di amministratore.
docker compose build
docker compose run --rm --no-deps app python sender.py hash-password
#    → stampa la riga gia' pronta, apici compresi, da incollare nel .env.
#      Funziona con il .env ancora incompleto: e' il comando che genera un
#      valore che la configurazione poi pretende.

# 4. Il segreto dei token.
openssl rand -base64 48
#    → incollalo in JWT_SECRET

# 5. Su.
docker compose up -d

# 6. Il primo popolamento del catalogo.
docker compose run --rm app python sender.py sync-topics
```

La porta si imposta con **`APP_PORT`** nel `.env` (default 8000); `BIND_ADDRESS`
resta `127.0.0.1`.

**Mettila dietro un reverse proxy con TLS**: il cookie di sessione è `Secure` e
il browser non lo invia su HTTP, quindi in HTTP puro il login risponde 200 e poi
401 a ogni richiesta, senza dire perché. La procedura completa, con la
configurazione di Caddy e nginx, è in `docs/runbook.md`.

---

## La riga di comando

```bash
python sender.py serve                      # API + scheduler (default del container)
python sender.py sync-topics [--full]       # aggiorna lo snapshot dei topic
python sender.py generate-queries --count N # genera query senza inviarle
python sender.py run-once [--limit N] [--provider X]   # un ciclo immediato
python sender.py cost-report [--days N]     # la spesa
```

Nel container si eseguono così:

```bash
docker compose run --rm app python sender.py generate-queries --count 20
```

`run-once` fa **chiamate a pagamento**. Stampa la spesa corrente prima di
partire e rispetta il tetto giornaliero.

---

## Come funziona

```
  articles (Supabase, SOLA LETTURA)
        │  sync-topics
        ▼
     topics ──► generatore (MASTER) ──► queries
                                          │
                                          ▼
                          esecutori (SLAVE), uno per provider
                                          │
                             ┌────────────┴────────────┐
                             ▼                         ▼
                     parser a 3 livelli          contabilità
                             │                         │
                             ▼                         ▼
                    probes + citations            budget / kill switch
                             │
                             ▼
                       daily_rollup ──► API ──► dashboard
```

**Due database, separati per costruzione.** Quello editoriale è letto da un
ruolo Postgres che possiede solo `SELECT`; se le credenziali configurate possono
scrivere — su `articles` o su qualunque altra tabella dello schema —
l'applicazione **si rifiuta di partire**. Quello di monitoraggio è un progetto
distinto, gestito con Alembic.

**Il generatore** ruota sul catalogo per coprire il massimo numero di argomenti:
metà del lotto orario va sulle notizie delle ultime 72 ore, dove la citazione si
decide; il resto su archivio e domande di categoria. Cinque strategie, con le
FAQ scritte dalla redazione come prima scelta. Un validatore scarta qualunque
domanda che nomini il giornale — una query che contiene il brand falsa la misura.

**Il parser** estrae le citazioni in tre livelli: campo strutturato del provider,
ripiego sui link nel testo, e infine la menzione del brand senza link (segnale
diverso, registrato a parte). Se un URL è avvolto in un redirect da cui il
dominio reale non è ricavabile, si registra `unresolved` invece di indovinare.

---

## Le tre discipline che tengono onesta la misura

1. **I probe falliti non entrano in nessun denominatore.** Un'ora di disservizio
   di un provider non deve somigliare a un crollo di visibilità. Un probe in cui
   il modello ha risposto *senza cercare* è marcato `no_search`: non è «non
   citato», è «non misurato».
2. **`retrieval` e `memory` non si mescolano mai.** Il primo misura se il
   retrieval pesca il giornale, il secondo se il modello lo ricorda. La loro
   media non è nessuna delle due.
3. **Nessuna percentuale senza il suo denominatore.** L'API restituisce ogni
   tasso come numeratore, denominatore e intervallo di confidenza di Wilson al
   95%. Sotto i dieci casi il tasso non viene nemmeno calcolato: si mostra un
   tratto. La dashboard disegna l'intervallo in scala, così un dato incerto
   *sembra* incerto.

---

## Provider

| Provider | Stato | Note |
|---|---|---|
| OpenAI | attivo | Responds API, tool `web_search`, `tool_choice: required` |
| Perplexity | attivo | Sonar API; dichiara il costo esatto della chiamata |
| Anthropic | attivo | Messages API, tool server-side di web search |
| Google Gemini | **spento per default** | vedi sotto |

**Gemini richiede una decisione, non una chiave.** I termini dell'API vietano
esplicitamente di raccogliere e analizzare in modo programmatico i link dei
risultati di grounding — che è ciò che questo servizio fa. L'adapter è scritto e
funzionante ma parte solo con `GEMINI_ENABLED=true`, da impostare dopo un parere
legale o un permesso scritto da Google. Il testo dei termini è citato in
`docs/providers.md`.

I parametri di ogni provider sono verificati sulla documentazione ufficiale alla
data indicata in `docs/providers.md`. Cambiano spesso: quando un adapter smette
di trovare citazioni, si riparte da lì.

---

## Documentazione

| File | Contenuto |
|---|---|
| `docs/providers.md` | Endpoint, path di estrazione delle citazioni, prezzi e trappole di ogni provider, con la data di verifica |
| `docs/design.md` | Token di design, scala tipografica, elemento firma, e la rilettura critica delle scelte |
| `docs/runbook.md` | Cosa fare quando: aggiungere un provider, aggiornare i prezzi, leggere la dashboard, un provider cambia API |
| `sql/readonly_role.sql` | Lo SQL del ruolo di sola lettura, da eseguire a mano |
| `pricing.yaml` | Listini versionati, con la data dell'ultimo aggiornamento |

---

## Sviluppo

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Postgres usa e getta per i test
docker run -d --name edunews24-pg-test \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=monitor \
  -p 55432:5432 postgres:17-alpine

TEST_DB_URL="postgresql+asyncpg://postgres:test@localhost:55432/monitor" \
  .venv/bin/python -m pytest

.venv/bin/ruff check . && .venv/bin/mypy app

# Frontend, con proxy verso il backend su :8000
cd frontend && npm install && npm run dev
```

Stack: Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, APScheduler,
structlog. Frontend React 18 + Vite + TypeScript + Tailwind v4 + TanStack Query
+ Recharts, costruito in fase di build dell'immagine e servito da FastAPI come
file statici — nessun server Node in produzione.
