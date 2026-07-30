# Runbook

Cosa fare quando. Organizzato per situazione, non per componente.

---

## Avviare il servizio in produzione

Serve una macchina con Docker e Docker Compose v2. Nient'altro: né Python né
Node, sono dentro l'immagine.

### 1. Prima di toccare il server: i due database

**Il ruolo di sola lettura** sul progetto Supabase che contiene `articles`.
Esegui `sql/readonly_role.sql` nella SQL Editor. Leggi i commenti:

* il **punto 5** riguarda RLS. Se `articles` ha row level security attiva, un
  ruolo nuovo **non vede nulla** finché non esiste una policy che lo nomina —
  nemmeno le righe pubbliche, perché le policy scritte per `anon` non si
  applicano a un ruolo diverso. Verificalo con
  `SELECT relrowsecurity FROM pg_class WHERE oid = 'public.articles'::regclass;`
* il **punto 6** è la verifica: `can_select` deve essere `true`, **tutto il
  resto `false`**. Se qualcosa è `true` l'applicazione si rifiuterà di partire.

**Il secondo progetto Supabase** per il database di monitoraggio. Crealo vuoto:
le tabelle le fa Alembic all'avvio.

Per entrambi prendi la connection string da *Project Settings → Database* e usa
il **pooler Supavisor in session mode** (porta 5432 sull'host
`...pooler.supabase.com`), non il collegamento diretto: `db.<ref>.supabase.co` è
IPv6-only sui progetti recenti e da un VPS senza IPv6 non si connette. Nota il
suffisso del project ref nello username: `edunews_monitor_ro.<REF>`.

### 2. Sul server

```bash
git clone https://github.com/micheleDibi/edunews24-ai-visibility-monitor.git
cd edunews24-ai-visibility-monitor
cp .env.example .env
```

### 3. I segreti

```bash
# JWT_SECRET (base64: non contiene `$`, quindi non serve quotarlo)
openssl rand -base64 48

# ADMIN_PASSWORD_HASH — l'immagine va costruita prima
docker compose build
docker compose run --rm --no-deps app python sender.py hash-password
```

`hash-password` e' l'unico comando che NON carica la configurazione e NON
applica le migrazioni, ed e' voluto: in produzione la configurazione pretende
`ADMIN_PASSWORD_HASH`, cioe' esattamente il valore che questo comando genera.
Stampa la riga gia' pronta con gli apici, da incollare nel `.env`.

**L'hash contiene `$` e va fra apici singoli nel `.env`.** Compose interpola i
`$` nei valori di `env_file`: senza gli apici l'hash viene ridotto a spazzatura,
il login risponde 401 con la password giusta e non c'è niente nei log che
spieghi perché. La stessa regola vale per qualunque password o connection string
che contenga `$`.

```ini
ADMIN_PASSWORD_HASH='$argon2id$v=19$m=65536,t=3,p=4$...'
```

### 4. La porta

```ini
APP_PORT=8000        # la porta SULLA MACCHINA. Cambia solo questa.
BIND_ADDRESS=127.0.0.1
```

`APP_PORT` è l'unica che ti interessa. `PORT` è la porta interna al container e
non c'è motivo di toccarla.

**Lascia `BIND_ADDRESS=127.0.0.1`.** Non è prudenza generica: il cookie di
sessione è `Secure` e il browser non lo invia su HTTP, quindi esponendo la porta
direttamente otterresti un login che risponde 200 e poi 401 a ogni richiesta.

### 5. Su

```bash
docker compose up -d
docker compose logs -f app          # Ctrl-C quando vedi "scheduler avviato"
curl -s localhost:8000/api/health | python3 -m json.tool
docker compose run --rm app python sender.py sync-topics
```

Se l'avvio si interrompe, il messaggio dice cosa fare: vedi *«L'applicazione non
parte»* più sotto.

### 6. Il reverse proxy con TLS

Obbligatorio, per la ragione al punto 4. Con Caddy sono due righe in
`/etc/caddy/Caddyfile`:

```
visibilita.edunews24.it {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy prende il certificato da sé. Con nginx serve `certbot` e:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

`X-Forwarded-For` non è decorativo: senza, il freno sul login conta tutti i
tentativi come provenienti dal proxy e basta un attacco per bloccare anche te.

Il firewall deve lasciare aperte solo 80 e 443. `APP_PORT` è su localhost e non
va esposta.

### 7. La prima verifica reale

```bash
# Le domande generate sono plausibili? Non spende nulla.
docker compose run --rm app python sender.py generate-queries --count 20

# Il primo ciclo vero. QUESTO spende: 5 query per il numero di provider.
docker compose run --rm app python sender.py run-once --limit 5

# Cosa hanno risposto davvero
docker compose run --rm app python sender.py cost-report --days 1
```

Poi apri la dashboard e guarda *Esplora probe*: apri una riga e confronta le
citazioni estratte con `raw_response`. È il momento in cui si scopre se il
parser di un provider ha bisogno di una correzione — vedi *«Un provider ha
cambiato API»*.

Da qui in avanti il ciclo orario gira da sé al minuto 7.

### 8. Aggiornare

```bash
git pull && docker compose up -d --build
```

Le migrazioni girano da sé all'avvio. Il container si ferma e riparte: un ciclo
in corso viene interrotto e chiuso come `failed` al riavvio successivo, senza
perdere i probe già scritti.

---

## Il login non funziona anche con la password giusta

Nel 99% dei casi il servizio è raggiunto in **HTTP**. Il cookie di sessione è
`Secure` e il browser non lo invia su una connessione non cifrata: il login
risponde 200, il cookie non torna indietro, e ogni richiesta successiva dà 401.

**Soluzione**: metti TLS davanti (Caddy, nginx, Traefik). Solo per una prova in
locale puoi impostare `COOKIE_SECURE=false` — mai in produzione.

Se invece la risposta è **429**, il freno del login è scattato: cinque tentativi
falliti per indirizzo in un quarto d'ora. Il conteggio è in memoria, quindi un
riavvio del container lo azzera.

---

## Aggiungere un provider

1. **Verifica la documentazione ufficiale corrente**, non la memoria e non
   `docs/providers.md`, che è una fotografia datata. Servono quattro cose: URL
   dell'endpoint, come si attiva la ricerca web, il **path esatto** delle
   citazioni nella risposta, e dove leggere token e numero di ricerche.

2. **Scrivi l'adapter** in `app/clients/<nome>_client.py`, con `name`,
   `supports_retrieval`, `model`, `probe(query, mode)` e `close()`. Copia la
   struttura di `perplexity_client.py`, che è il più semplice.

3. **Registralo** in `COSTRUTTORI` in `app/clients/registry.py`, e aggiungi la
   chiave API in `Settings` e in `.env.example`. Senza chiave l'adapter resta
   disattivato con un log informativo, non un errore.

4. **Aggiungi il listino** in `pricing.yaml`: token per milione e la tariffa per
   ricerca o per richiesta. Un modello assente dal listino fa cadere il costo a
   zero, e il kill switch non protegge più.

5. **Il colore della serie** in `SERIE_PROVIDER` in `frontend/src/lib/format.ts`,
   con un **tratteggio diverso** dagli altri: le serie non si distinguono solo
   per colore.

6. **Un test** in `tests/test_adapters.py` con una risposta finta costruita dal
   campione JSON della documentazione. È il test che protegge dal guasto peggiore
   del sistema — un nome di campo sbagliato non solleva un'eccezione, restituisce
   zero citazioni, e zero citazioni somiglia a «il giornale non è citato».

---

## Un provider ha cambiato API

**Il sintomo**: il citation rate di quel provider crolla a zero mentre gli altri
restano stabili, e i probe risultano `ok`. Nessun errore da nessuna parte.

**La diagnosi**, in ordine:

1. Apri *Esplora probe*, filtra per quel provider, apri una riga recente e
   guarda **`raw_response`**. Se c'è ma le fonti sono vuote, il path di
   estrazione non corrisponde più.
   ```sql
   SELECT id, provider, jsonb_pretty(raw_response)
   FROM probes WHERE provider = 'openai' AND status = 'ok'
   ORDER BY created_at DESC LIMIT 1;
   ```
2. Confronta la forma reale con quella documentata in `docs/providers.md`.
3. Correggi la funzione di estrazione nell'adapter e **aggiorna il test** con la
   nuova forma, tenendo anche la vecchia se il provider serve entrambe.
4. Aggiorna `docs/providers.md` con la nuova data di verifica.

Se `raw_response` è `null`: la retention l'ha azzerato dopo
`RAW_RETENTION_DAYS`. Non significa che non c'era. Per indagare, esegui un
`run-once --provider <nome> --limit 1` e guarda il probe appena creato.

---

## Aggiornare `pricing.yaml`

L'applicazione scrive un warning a ogni avvio se `updated:` è più vecchio di
`PRICING_MAX_AGE_DAYS` (90 giorni). Un kill switch che calcola su prezzi di un
anno fa non protegge nulla.

1. Apri la pagina dei prezzi di ciascun provider — l'URL è in `source_url`
   accanto a ogni voce.
2. Aggiorna i numeri **e il campo `updated:`**.
3. Aggiorna `USD_EUR_RATE` nel `.env`: i listini sono in USD, il database in EUR.
4. `pytest tests/test_pricing.py` verifica che ogni modello configurato esista
   nel listino.

**Attenzione all'unità**, che cambia fra provider e fra generazioni: OpenAI e
Anthropic fatturano **per ricerca**, Perplexity **per richiesta** a fasce (e
dichiara il costo esatto nella risposta, che ha la precedenza su ogni stima),
Gemini 2.5 per richiesta e Gemini 3 per singola query di ricerca. Una domanda
che ne fa cinque costa cinque volte.

---

## La spesa è più alta del previsto

```bash
docker compose run --rm app python sender.py cost-report --days 7
```

Guarda la colonna **`stimati`**: conta i probe il cui costo è stato dedotto dal
listino perché il provider non ha dichiarato l'uso dei token. Se è alta, la
spesa reale può scostarsi e va confrontata con la fattura.

Le leve, dalla più efficace:

| Leva | Effetto |
|---|---|
| `ANTHROPIC_MAX_USES` | Tetto duro alle ricerche per richiesta. È l'unico freno vero sui provider che fatturano a ricerca |
| `DAILY_QUERY_BUDGET` | Query distinte al giorno. Il lotto orario si ridimensiona da sé |
| `OPENAI_SEARCH_CONTEXT_SIZE` | `low` recupera meno pagine, e le pagine recuperate si pagano come token di input |
| `MEMORY_MODE_SAMPLE_RATE` | I probe in memoria costano una frazione: alzarlo non incide quasi |
| `MAX_DAILY_SPEND_EUR` | Il freno assoluto. Al superamento i cicli si saltano con `skipped_budget` |

Il kill switch controlla **prima** di spendere. Quando scatta, la dashboard
mostra un banner e i cicli riprendono da sé quando la finestra si azzera.

---

## Leggere la dashboard

**Comincia da «Dove sei invisibile».** È la sezione operativa: articoli sondati
più volte e mai citati, dal più sondato. Apri una riga per vedere le domande
fatte, le risposte ricevute e **chi è stato citato al posto tuo**. Quella lista è
il compito editoriale.

**Il distintivo «recuperato ma non citato»** è la distinzione che conta di più
in quella lista: significa che il giornale è comparso fra le fonti mostrate al
modello, che però non l'ha usato. Non è un problema di indicizzazione — è un
problema di qualità percepita del pezzo su quella domanda. Sono due azioni
diverse.

**Ogni percentuale ha una banda sotto.** È l'intervallo di confidenza al 95%,
disegnato in scala: se è larga, il numero non è affidabile. Un tratto al posto
della cifra significa meno di dieci casi — il conteggio si mostra, la percentuale
no, perché su tre casi non è una misura.

**Il delta compare solo quando è significativo.** Se gli intervalli dei due
periodi si sovrappongono, la variazione è rumore e la dashboard lo dice invece di
mostrare una freccia.

**La colonna «memoria» nella tabella provider non si confronta con le altre.** È
separata da un filetto per questo: misura se il modello *ricorda* il giornale,
non se il retrieval lo *trova*.

**`unresolved` nella classifica dei domini** è la quota di misura che non
abbiamo: URL avvolti in un redirect da cui il dominio reale non è ricavabile. Si
dichiara invece di indovinarlo.

---

## Il ciclo orario non parte

```bash
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
```

`prossime_esecuzioni` dice quando partirà. Se `scheduler` è `spento`, manca
`SCHEDULER_ENABLED=true`.

Se è attivo ma non produce probe, le cause in ordine di probabilità:

1. **Budget esaurito** → `/api/costs`, o il banner in dashboard.
2. **`topics` vuota** → `sender.py sync-topics`.
3. **Tutte le domande già eseguite di recente** → la finestra di deduplica è
   `QUERY_DEDUP_WINDOW_DAYS` (14 giorni). Con un catalogo piccolo si esaurisce.
4. **Nessun provider configurato** → i log lo dicono all'avvio.

**Mai due container insieme sullo stesso database di monitoraggio.** Lo scheduler
è in-process: due istanze eseguirebbero il ciclo orario due volte, raddoppiando
spesa e probe. Per lo stesso motivo `--workers 1` non è negoziabile.

---

## Le migrazioni

L'entrypoint del container esegue `alembic upgrade head` prima di avviare il
servizio. Per saltarlo (per esempio se applichi le migrazioni da un job separato)
imposta `SKIP_MIGRATIONS=true`.

A mano:
```bash
docker compose run --rm app alembic upgrade head
docker compose run --rm app alembic current
```

**Alembic contro un pooler in transaction mode** funziona perché
`DB_DISABLE_PREPARED_STATEMENTS=true` disattiva i prepared statement di asyncpg.
Con `false` e un pooler davanti si ottiene `prepared statement already exists`
appena una connessione viene riusata.

---

## Retention e spazio

Il job notturno (3:20, ora di Roma) azzera `raw_response` dopo
`RAW_RETENTION_DAYS` (30) e `answer_text` dopo `ANSWER_RETENTION_DAYS` (180).
Le **righe non si cancellano mai** e `daily_rollup` non si pota: le metriche
storiche devono restare leggibili, altrimenti i numeri del passato cambierebbero
retroattivamente.

Se lo spazio su Supabase preoccupa, abbassa `RAW_RETENTION_DAYS`: è la colonna
che pesa. Ma tenerne almeno qualche giorno serve, perché è l'unico modo di
verificare il parser quando un provider cambia API.

---

## Il rollup sembra sbagliato

È **idempotente**: ricalcola da zero dai probe grezzi e sovrascrive, invece di
incrementare. Rieseguirlo non raddoppia nulla.

```bash
docker compose run --rm app python -c "
import asyncio
from app.db.session import get_sessionmaker, dispose_engine
from app.services import rollup
async def main():
    async with get_sessionmaker()() as s:
        print(await rollup.ricalcola(s, giorni=30))
    await dispose_engine()
asyncio.run(main())
"
```

Il job notturno ricalcola gli ultimi 3 giorni, così un ciclo finito dopo
mezzanotte o un paio di notti di container spento si recuperano da sé.

---

## L'applicazione non parte

Il messaggio nei log dice cosa fare. I due casi:

**`SourceDbWritableError`** — le credenziali del DB editoriale possono scrivere.
Il messaggio elenca esattamente quali privilegi sono di troppo. È un rifiuto
deliberato: un servizio di misura non deve poter modificare ciò che misura.
Crea il ruolo con `sql/readonly_role.sql`.

**`SourceTableMissingError`** — la tabella non esiste, oppure il ruolo non ha
`USAGE` sullo schema e quindi non la vede, oppure RLS è attiva e manca la policy.

---

## Dove guardare quando qualcosa non torna

| Domanda | Dove |
|---|---|
| Il servizio sta bene? | `GET /api/health` |
| Quanto ho speso? | `GET /api/costs`, o `cost-report` |
| Cosa ha fatto l'ultimo ciclo? | `GET /api/runs`, o *Stato del sistema* |
| Cosa ha risposto davvero il provider? | *Esplora probe* → riga → `raw_response` |
| Le domande generate sono plausibili? | `generate-queries --count 20` |
| I prezzi sono aggiornati? | `updated:` in `pricing.yaml`, e il warning all'avvio |
