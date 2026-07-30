-- ============================================================================
-- Ruolo di SOLA LETTURA per Edunews24 AI Visibility Monitor
-- ============================================================================
-- Da eseguire UNA VOLTA nella SQL Editor del progetto Supabase che contiene la
-- tabella `articles` (il DB editoriale).
--
-- Il servizio di monitoraggio non deve possedere alcuna credenziale in grado di
-- scrivere sul database degli articoli: se la connection string configurata ha
-- privilegi di scrittura, l'applicazione si rifiuta di partire (vedi
-- `app/db/source.py`, funzione `assert_readonly`).
--
-- Prima di eseguire: sostituisci <PASSWORD_FORTE> con una password casuale.
--   openssl rand -base64 32
-- ============================================================================


-- 1. Il ruolo -----------------------------------------------------------------
-- NOSUPERUSER / NOCREATEDB / NOCREATEROLE / NOBYPASSRLS sono gia' i default,
-- ma li scriviamo esplicitamente: questo file e' anche la documentazione di
-- cosa il servizio puo' e non puo' fare.
CREATE ROLE edunews_monitor_ro WITH
  LOGIN
  PASSWORD '<PASSWORD_FORTE>'
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOINHERIT
  NOBYPASSRLS
  CONNECTION LIMIT 5;


-- 2. Connessione e visibilita' dello schema -----------------------------------
-- Senza USAGE sullo schema il ruolo non vede nemmeno l'esistenza della tabella.
GRANT CONNECT ON DATABASE postgres TO edunews_monitor_ro;
GRANT USAGE   ON SCHEMA public     TO edunews_monitor_ro;


-- 3. L'unico privilegio concesso ----------------------------------------------
GRANT SELECT ON public.articles TO edunews_monitor_ro;


-- 4. Nessun privilegio automatico sulle tabelle future ------------------------
-- Se domani nasce `articles_v2`, il monitor NON deve vederla finche' non lo
-- decidi tu. ALTER DEFAULT PRIVILEGES agisce solo sugli oggetti creati d'ora in
-- poi dal ruolo indicato in FOR ROLE (qui: il proprietario dello schema).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON TABLES FROM edunews_monitor_ro;


-- 5. Row Level Security -------------------------------------------------------
-- ATTENZIONE: se `articles` ha RLS attiva, un ruolo NUOVO non vede NULLA finche'
-- non esiste una policy che lo nomina. Le policy scritte per `anon` (usate dal
-- frontend con la anon key) non si applicano a questo ruolo.
--
-- Verifica se RLS e' attiva:
--     SELECT relrowsecurity FROM pg_class WHERE oid = 'public.articles'::regclass;
--
-- Se il risultato e' `true`, esegui anche questa policy. E' anche un filtro
-- utile di per se': il monitor non ha alcun motivo di leggere le bozze.
--
-- CREATE POLICY articles_monitor_ro_read ON public.articles
--   FOR SELECT TO edunews_monitor_ro
--   USING (isdraft = false AND published_at IS NOT NULL);


-- 6. Verifica finale ----------------------------------------------------------
-- `can_select` deve essere true; TUTTE le altre colonne devono essere false.
-- Se una qualsiasi delle altre e' true, il servizio si rifiutera' di partire.
SELECT
  has_table_privilege('edunews_monitor_ro', 'public.articles', 'SELECT')   AS can_select,
  has_table_privilege('edunews_monitor_ro', 'public.articles', 'INSERT')   AS can_insert,
  has_table_privilege('edunews_monitor_ro', 'public.articles', 'UPDATE')   AS can_update,
  has_table_privilege('edunews_monitor_ro', 'public.articles', 'DELETE')   AS can_delete,
  has_table_privilege('edunews_monitor_ro', 'public.articles', 'TRUNCATE') AS can_truncate,
  has_schema_privilege('edunews_monitor_ro', 'public', 'CREATE')           AS can_create,
  (SELECT rolsuper      FROM pg_roles WHERE rolname = 'edunews_monitor_ro') AS is_superuser,
  (SELECT rolbypassrls  FROM pg_roles WHERE rolname = 'edunews_monitor_ro') AS bypasses_rls;


-- 7. Connection string da mettere in .env -------------------------------------
-- Prendi host e porta dalla dashboard Supabase: Project Settings > Database.
--
-- Il collegamento diretto (db.<ref>.supabase.co:5432) e' IPv6-only sui progetti
-- recenti: da un VPS senza IPv6 non funziona. Usa il pooler Supavisor in
-- SESSION mode (porta 5432 sull'host `...pooler.supabase.com`), il cui username
-- ha il suffisso del project ref:
--
--   SOURCE_DB_URL=postgresql+asyncpg://edunews_monitor_ro.<PROJECT_REF>:<PASSWORD_FORTE>@aws-0-<REGIONE>.pooler.supabase.com:5432/postgres
--
-- Se puoi usare solo la TRANSACTION mode (porta 6543), lascia
-- DB_DISABLE_PREPARED_STATEMENTS=true nel .env: senza, asyncpg fallisce con
-- "prepared statement ... already exists" appena il pooler riusa una connessione.
