"""Configurazione dell'applicazione, letta da variabili d'ambiente / `.env`.

Un solo punto di verita' per ogni parametro. Nessun `os.getenv` sparso nel
codice: se un valore serve, si aggiunge qui con un default esplicito e un
commento che spiega *perche'* quel default.

Regola non negoziabile: nessun default inventato per credenziali o endpoint.
`SOURCE_DB_URL` e `MONITOR_DB_URL` non hanno default — se mancano,
l'applicazione non parte.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `app/core/config.py` → parents[2] = radice del repository.
# Pydantic Settings ignora silenziosamente il file se non esiste (in container
# le variabili arrivano da `env_file:` del compose, non da un `.env` copiato).
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === Ambiente ===========================================================
    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "json"
    # Fuso orario di tutta la schedulazione e di ogni aggregato giornaliero.
    # Il giornale e' italiano: "oggi" significa oggi a Roma, non a UTC.
    tz: str = "Europe/Rome"

    # === DB sorgente — SOLA LETTURA =========================================
    # Ruolo Postgres con il solo privilegio SELECT su `source_table`.
    # Vedi `sql/readonly_role.sql`. All'avvio l'app verifica di non poter
    # scrivere e si ferma se puo'.
    source_db_url: str
    source_schema: str = "public"
    source_table: str = "articles"

    # === DB monitoraggio — lettura/scrittura, progetto SEPARATO =============
    monitor_db_url: str
    monitor_pool_size: int = 5
    monitor_max_overflow: int = 5
    # Supavisor/pgbouncer in TRANSACTION mode riusa le connessioni tra client:
    # i prepared statement di asyncpg esplodono con "prepared statement _pg_N
    # already exists". Disattivarli costa nulla al nostro volume (poche
    # centinaia di query all'ora) e rende l'app indifferente alla modalita' del
    # pooler. Metti `false` solo su un Postgres senza pooler.
    db_disable_prepared_statements: bool = True

    # === Provider LLM — chiave assente significa adapter disattivato =========
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    perplexity_api_key: str | None = None

    # I model ID vivono in configurazione, non nel codice: i provider li
    # deprecano piu' in fretta di quanto si rifattorizzi un adapter.
    # Scelte verificate il 2026-07-30, vedi docs/providers.md.
    openai_model: str = "gpt-5.6-luna"  # il piu' economico non deprecato
    perplexity_model: str = "sonar"
    anthropic_model: str = "claude-sonnet-5"
    # gemini-2.5-flash ha 1.500 richieste con grounding al giorno gratis, che
    # coprono interamente le nostre; la generazione 3 fattura per singola query
    # di ricerca e costa molto di piu' allo stesso volume.
    gemini_model: str = "gemini-2.5-flash"

    # Gemini e' DISATTIVATO per default e non e' una dimenticanza. I termini
    # dell'API vietano esplicitamente cio' che questo servizio fa con i
    # risultati di grounding: "cache, frame, syndicate, resell, analyze, train
    # on, or otherwise learn from Grounded Results", e fra gli esempi di
    # violazione "using programmatic or automated means to collect Links, using
    # Links to build an index". Abilitalo solo dopo un parere legale o un
    # permesso scritto da Google. Vedi docs/providers.md.
    gemini_enabled: bool = False

    # Dimensione del contesto di ricerca. Su OpenAI incide sui token recuperati
    # (che paghi come input); su Perplexity e' anche la fascia di prezzo per
    # richiesta, dove "low" e' il default piu' economico.
    openai_search_context_size: Literal["low", "medium", "high"] = "medium"
    perplexity_search_context_size: Literal["low", "medium", "high"] = "low"

    # Versione del tool di web search di Anthropic. La piu' recente attiva il
    # "dynamic filtering", che annida i blocchi della risposta e complica
    # l'estrazione: la versione base tiene il layout piatto.
    anthropic_web_search_tool: str = "web_search_20250305"
    # Tetto di ricerche per richiesta: e' l'unico freno di spesa vero, perche'
    # ogni ricerca costa a parte.
    anthropic_max_uses: int = 5

    # Localizzazione dichiarata delle richieste. Senza, i risultati pendono
    # verso la geografia di default del provider e le domande italiane
    # sull'istruzione fanno emergere meno domini italiani: sarebbe un bias
    # sistematico contro il giornale, cioe' una misura sbagliata.
    probe_country: str = "IT"
    probe_city: str = "Roma"
    probe_region: str = "Lazio"

    anthropic_max_tokens: int = 4096

    # === Comportamento del monitor ==========================================
    # Query DISTINTE al giorno. Il numero di probe e' questo x n_provider.
    daily_query_budget: int = 200
    max_concurrency_per_provider: int = 3
    # Le chiamate con web search sono lente: 120s non e' un margine generoso.
    probe_timeout_seconds: int = 120
    own_domain: str = "edunews24.it"

    # Modalita' `memory`: stessa domanda senza strumenti, per misurare se il
    # brand e' entrato nella conoscenza parametrica del modello. E' una metrica
    # DIVERSA da `retrieval` e non va mai mescolata con essa.
    memory_mode_sample_rate: float = 0.1

    # === Generatore di query ================================================
    query_rewrite_enabled: bool = True
    # Modello economico per la naturalizzazione: una chiamata per lotto.
    query_rewrite_model: str = "gpt-5-mini"
    query_rewrite_provider: Literal["openai", "anthropic", "gemini"] = "openai"
    # Configurabile per poter puntare a un endpoint compatibile o a un proxy
    # senza toccare il codice.
    openai_base_url: str = "https://api.openai.com/v1"

    # Composizione del lotto orario, in percentuale. Devono sommare a 100.
    bucket_fresh_pct: int = 50  # published_at nelle ultime 72h
    bucket_recent_pct: int = 20  # tra 3 e 30 giorni
    bucket_archive_pct: int = 20  # rotazione per last_probed_at NULLS FIRST
    bucket_category_pct: int = 10  # domande di categoria, non legate a un articolo

    # Una query gia' eseguita in questa finestra non viene rimandata.
    query_dedup_window_days: int = 14

    # === Budget (kill switch) ===============================================
    max_daily_spend_eur: float = 5.0
    max_monthly_spend_eur: float = 100.0
    # I listini dei provider sono in USD, il DB e la dashboard in EUR.
    # Tasso configurabile: nessuna chiamata a un servizio di cambio a runtime,
    # che sarebbe una dipendenza esterna in piu' per una precisione che qui non
    # serve. Aggiornalo quando aggiorni `pricing.yaml`.
    usd_eur_rate: float = 0.92
    pricing_file: str = "pricing.yaml"
    # Warning nei log se `pricing.yaml` non viene aggiornato da troppo tempo.
    pricing_max_age_days: int = 90

    # === Retention ==========================================================
    # `raw_response` serve a verificare il parser, non a essere conservato per
    # sempre: su Supabase lo spazio si paga. Gli aggregati in `daily_rollup`
    # restano comunque per sempre.
    raw_retention_days: int = 30
    answer_retention_days: int = 180

    # === Auth (un solo amministratore) ======================================
    admin_password_hash: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    # Un solo utente: niente refresh token, solo un access token a TTL lungo.
    access_token_ttl_seconds: int = 60 * 60 * 24 * 7
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # === Server =============================================================
    host: str = "0.0.0.0"
    port: int = 8000
    scheduler_enabled: bool = True

    # ------------------------------------------------------------------
    # Validatori
    # ------------------------------------------------------------------
    @field_validator("source_db_url", "monitor_db_url")
    @classmethod
    def _must_be_asyncpg(cls, v: str) -> str:
        """SQLAlchemy async richiede il driver asyncpg, non `postgresql://` nudo.

        E' l'errore di configurazione piu' frequente e produce un messaggio
        criptico di SQLAlchemy: meglio intercettarlo qui.
        """
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                f"deve iniziare con 'postgresql+asyncpg://' (ricevuto: '{v.split('://')[0]}://...')"
            )
        return v

    @field_validator("memory_mode_sample_rate")
    @classmethod
    def _rate_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("MEMORY_MODE_SAMPLE_RATE deve stare tra 0.0 e 1.0")
        return v

    @model_validator(mode="after")
    def _buckets_sum_to_100(self) -> Settings:
        total = (
            self.bucket_fresh_pct
            + self.bucket_recent_pct
            + self.bucket_archive_pct
            + self.bucket_category_pct
        )
        if total != 100:
            raise ValueError(f"le percentuali dei bucket devono sommare a 100, sommano a {total}")
        return self

    @model_validator(mode="after")
    def _production_requires_secrets(self) -> Settings:
        """In produzione i segreti non possono restare vuoti.

        In sviluppo si tollera l'assenza, cosi' `sync-topics` e
        `generate-queries` girano senza dover prima configurare l'auth.
        """
        if self.env != "production":
            return self
        mancanti = [
            nome
            for nome, valore in (
                ("JWT_SECRET", self.jwt_secret),
                ("ADMIN_PASSWORD_HASH", self.admin_password_hash),
            )
            if not valore
        ]
        if mancanti:
            raise ValueError(f"in produzione servono: {', '.join(mancanti)}")
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET deve essere lungo almeno 32 caratteri")
        return self

    # ------------------------------------------------------------------
    # Derivati
    # ------------------------------------------------------------------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def repo_root(self) -> Path:
        return _REPO_ROOT

    @computed_field  # type: ignore[prop-decorator]
    @property
    def qualified_source_table(self) -> str:
        """Nome della tabella sorgente qualificato con lo schema."""
        return f"{self.source_schema}.{self.source_table}"

    @property
    def enabled_providers(self) -> list[str]:
        """Provider con la chiave API presente, in ordine di priorita'.

        Chiave assente = adapter disattivato con un log informativo, non un
        errore: si deve poter girare con un solo provider configurato.
        """
        coppie = (
            ("openai", self.openai_api_key),
            ("perplexity", self.perplexity_api_key),
            ("anthropic", self.anthropic_api_key),
            # Anche con la chiave presente, Gemini resta spento se non lo
            # abiliti esplicitamente: vedi il commento su `gemini_enabled`.
            ("gemini", self.gemini_api_key if self.gemini_enabled else None),
        )
        return [nome for nome, chiave in coppie if chiave]


@lru_cache
def get_settings() -> Settings:
    return Settings()
