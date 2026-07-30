"""Implementazione dei sottocomandi di `sender.py`.

`sender.py` alla radice e' volutamente sottile: tutta la logica sta qui, cosi'
i comandi sono importabili e testabili senza lanciare un processo.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import structlog

from app.core.config import Settings, get_settings
from app.core.logging import setup_logging

log = structlog.get_logger(__name__)

# Fasi non ancora consegnate. Meglio un messaggio esplicito che un comando che
# esiste nell'help ma esplode con un ImportError.
NON_ANCORA_IMPLEMENTATI: dict[str, str] = {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sender.py",
        description=(
            "Edunews24 AI Visibility Monitor — misura se e quando i motori di "
            "risposta AI citano edunews24.it."
        ),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_serve = sub.add_parser("serve", help="avvia API + scheduler (default del container)")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)

    p_run = sub.add_parser("run-once", help="esegue un ciclo immediato, per test")
    p_run.add_argument("--limit", type=int, default=None, help="numero massimo di query")
    p_run.add_argument("--provider", default=None, help="limita a un solo provider")

    p_gen = sub.add_parser("generate-queries", help="genera e salva query senza inviarle")
    p_gen.add_argument("--count", type=int, default=20)

    p_sync = sub.add_parser("sync-topics", help="aggiorna lo snapshot dei topic dal DB editoriale")
    p_sync.add_argument(
        "--full",
        action="store_true",
        help="rilegge tutto e disattiva i topic non piu' pubblicati (default: incrementale)",
    )

    p_cost = sub.add_parser("cost-report", help="stampa la spesa stimata")
    p_cost.add_argument("--days", type=int, default=30)

    sub.add_parser(
        "hash-password",
        help="genera l'hash per ADMIN_PASSWORD_HASH (non richiede configurazione)",
    )

    return parser


# ---------------------------------------------------------------------------
# Comandi
# ---------------------------------------------------------------------------


async def cmd_sync_topics(args: argparse.Namespace, settings: Settings) -> int:
    from app.db.session import dispose_engine, get_sessionmaker
    from app.db.source import (
        SourceDbWritableError,
        SourceTableMissingError,
        assert_readonly,
        dispose_source_engine,
    )
    from app.services.topics_sync import sync_topics

    try:
        await assert_readonly(settings)
    except (SourceDbWritableError, SourceTableMissingError) as exc:
        print(f"\nERRORE DI CONFIGURAZIONE\n\n{exc}\n", file=sys.stderr)
        return 2

    try:
        async with get_sessionmaker()() as session:
            stats = await sync_topics(session, full=args.full, settings=settings)
    finally:
        await dispose_source_engine()
        await dispose_engine()

    modalita = "completa" if stats.full_eseguito else "incrementale"
    if stats.full_eseguito and not args.full:
        modalita = "completa (primo avvio: non c'era nulla da confrontare)"

    print(
        f"\nSincronizzazione {modalita} terminata.\n"
        f"  letti dalla sorgente : {stats.fetched}\n"
        f"  inseriti             : {stats.inserted}\n"
        f"  aggiornati           : {stats.updated}\n"
        f"  disattivati          : {stats.deactivated}\n"
        f"  scartati             : {stats.skipped}"
    )
    if stats.motivi_scarto:
        for motivo, quanti in sorted(stats.motivi_scarto.items()):
            print(f"      - {motivo}: {quanti}")
    print()
    return 0


async def cmd_generate_queries(args: argparse.Namespace, settings: Settings) -> int:
    """Genera e salva un lotto, poi lo stampa per la revisione a occhio.

    L'output e' pensato per essere letto da un essere umano che si chiede "un
    lettore scriverebbe questa domanda?". Se la risposta e' no, il resto del
    sistema misurerebbe rumore, e si torna a lavorare sui template.
    """
    from app.db.session import dispose_engine, get_sessionmaker
    from app.services.querygen import genera_lotto

    try:
        async with get_sessionmaker()() as session:
            esito = await genera_lotto(session, args.count, settings=settings)
    finally:
        await dispose_engine()

    larghezza = 78
    print("\n" + "=" * larghezza)
    print(f"LOTTO DI {len(esito.query)} QUERY (richieste: {args.count})")
    print("=" * larghezza)

    if not esito.query:
        print(
            "\nNessuna query prodotta. Le cause possibili, in ordine di probabilita':\n"
            "  1. `topics` e' vuota            → esegui prima `sender.py sync-topics`\n"
            "  2. tutte le domande possibili sono state generate ed eseguite di recente\n"
            f"     (finestra di deduplica: {settings.query_dedup_window_days} giorni)\n"
        )
        return 1

    for i, q in enumerate(esito.query, 1):
        etichetta = f"[{q.strategy}"
        if q.generator == "llm_rewrite":
            etichetta += "+riscritta"
        etichetta += "]"
        contesto = q.category_slug or "—"
        print(f"\n{i:3}. {q.text}")
        print(f"     {etichetta:28} categoria: {contesto}")

    print("\n" + "-" * larghezza)
    print(f"  nuove          : {esito.nuove}")
    print(f"  riusate        : {esito.riusate}")
    print(f"  riscrittura    : {esito.riscrittura}")
    print(f"  composizione   : {esito.composizione}")
    if esito.scartate:
        print("  scartate       :")
        for motivo, quante in sorted(esito.scartate.items()):
            print(f"      - {motivo}: {quante}")
    print("-" * larghezza)
    print(
        "\nControlla a occhio: suonano come domande che un genitore, un docente o uno\n"
        "studente scriverebbe davvero? Nessuna deve nominare il giornale.\n"
    )
    return 0


async def cmd_run_once(args: argparse.Namespace, settings: Settings) -> int:
    """Un ciclo completo, subito. Fa chiamate a pagamento ai provider."""
    from app.db.session import dispose_engine, get_sessionmaker
    from app.services import budget
    from app.services.runner import esegui_ciclo

    quante = args.limit if args.limit is not None else 5

    # I provider si validano PRIMA di annunciare cosa si sta per fare:
    # annunciare "sto per eseguire su 0 provider" e poi fallire e' peggio che
    # fallire subito.
    if not settings.enabled_providers:
        print(
            "\nERRORE\n\nNessun provider configurato: metti almeno una chiave API nel .env "
            "(OPENAI_API_KEY, PERPLEXITY_API_KEY, ANTHROPIC_API_KEY).\n"
            "Le chiavi assenti non sono un errore: quel provider viene semplicemente "
            "saltato. Ma almeno una serve.\n",
            file=sys.stderr,
        )
        return 2

    if args.provider and args.provider not in settings.enabled_providers:
        print(
            f"\nERRORE\n\nProvider '{args.provider}' non disponibile: chiave assente, "
            "oppure disattivato.\nProvider configurati: "
            f"{', '.join(settings.enabled_providers)}\n",
            file=sys.stderr,
        )
        return 2

    try:
        async with get_sessionmaker()() as session:
            stato = await budget.stato(session, settings)
            print(
                f"\nSpesa: {stato.giorno_eur} EUR oggi (tetto {stato.tetto_giorno_eur}), "
                f"{stato.mese_eur} EUR questo mese (tetto {stato.tetto_mese_eur})."
            )
            provider_attivi = [args.provider] if args.provider else settings.enabled_providers
            print(
                f"Sto per eseguire {quante} query su {len(provider_attivi)} provider "
                f"({', '.join(provider_attivi) or 'nessuno'}): chiamate a pagamento.\n"
            )

            esito = await esegui_ciclo(
                session, quante=quante, provider=args.provider, kind="manual", settings=settings
            )
    except ValueError as exc:
        print(f"\nERRORE\n\n{exc}\n", file=sys.stderr)
        return 2
    finally:
        await dispose_engine()

    print(
        f"Ciclo #{esito.run_id} — {esito.status}\n"
        f"  pianificati : {esito.planned}\n"
        f"  completati  : {esito.completed}\n"
        f"  falliti     : {esito.failed}\n"
        f"  costo       : {esito.cost_eur} EUR"
    )
    if esito.per_stato:
        for stato_probe, quanti in sorted(esito.per_stato.items()):
            print(f"      - {stato_probe}: {quanti}")
    if esito.note:
        print(f"  nota        : {esito.note}")
    if esito.per_stato.get("no_search"):
        print(
            "\n  ATTENZIONE: alcuni probe non hanno eseguito nessuna ricerca. Sono\n"
            "  registrati come `no_search` ed esclusi da ogni denominatore: una\n"
            "  risposta data a memoria non e' un 'non citato', e' un 'non misurato'."
        )
    print(
        "\nControllo consigliato: confronta a mano le citazioni estratte con il\n"
        "raw_response grezzo, provider per provider.\n"
        "  SELECT p.provider, p.status, p.search_calls, p.edunews_cited,\n"
        "         count(c.id) AS citazioni\n"
        f"  FROM probes p LEFT JOIN citations c ON c.probe_id = p.id\n"
        f"  WHERE p.run_id = {esito.run_id} GROUP BY 1,2,3,4;\n"
    )
    return 0 if esito.status in ("ok", "partial") else 1


async def cmd_serve(args: argparse.Namespace, settings: Settings) -> int:
    """API + scheduler. E' il comando di default del container."""
    import uvicorn

    host = args.host or settings.host
    porta = args.port or settings.port

    config = uvicorn.Config(
        "app.main:app",
        host=host,
        port=porta,
        # UN solo worker, non negoziabile: lo scheduler e' in-process e due
        # worker eseguirebbero il ciclo orario due volte, raddoppiando la spesa.
        workers=1,
        log_config=None,  # il logging lo configura `setup_logging`
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    await uvicorn.Server(config).serve()
    return 0


async def cmd_cost_report(args: argparse.Namespace, settings: Settings) -> int:
    from sqlalchemy import text as sql

    from app.db.session import dispose_engine, get_sessionmaker
    from app.services import budget

    righe: Sequence[Any] = []
    try:
        async with get_sessionmaker()() as session:
            stato = await budget.stato(session, settings)
            righe = (
                await session.execute(
                    sql(
                        """
                        SELECT (created_at AT TIME ZONE :tz)::date AS giorno,
                               provider,
                               count(*)                                    AS probe,
                               count(*) FILTER (WHERE status = 'ok')       AS ok,
                               coalesce(sum(cost_eur), 0)                  AS costo,
                               count(*) FILTER (WHERE cost_estimated)      AS stimati
                        FROM probes
                        WHERE created_at >= now() - make_interval(days => :giorni)
                        GROUP BY 1, 2
                        ORDER BY 1 DESC, 2
                        """
                    ),
                    {"tz": settings.tz, "giorni": args.days},
                )
            ).all()
    finally:
        await dispose_engine()

    print(f"\nSpesa degli ultimi {args.days} giorni (fuso {settings.tz})\n")
    if not righe:
        print("  Nessun probe nel periodo.\n")
    else:
        print(
            f"  {'giorno':<12} {'provider':<12} {'probe':>6} "
            f"{'ok':>5} {'costo EUR':>11} {'stimati':>8}"
        )
        print("  " + "-" * 58)
        for giorno, provider, probe, ok, costo, stimati in righe:
            print(f"  {giorno!s:<12} {provider:<12} {probe:>6} {ok:>5} {costo:>11} {stimati:>8}")

    print(
        f"\n  oggi  : {stato.giorno_eur} EUR / {stato.tetto_giorno_eur} EUR"
        f"\n  mese  : {stato.mese_eur} EUR / {stato.tetto_mese_eur} EUR"
    )
    if stato.superato:
        print(f"\n  BUDGET SUPERATO — {stato.motivo()}")
        print("  I cicli orari vengono saltati con status `skipped_budget`.")
    print(
        "\n  La colonna `stimati` conta i probe il cui costo e' stato dedotto dal\n"
        "  listino perche' il provider non ha dichiarato l'uso di token. Se e' alta,\n"
        "  la spesa reale puo' scostarsi: controlla la fattura.\n"
    )
    return 0


async def cmd_non_implementato(args: argparse.Namespace, settings: Settings) -> int:
    fase = NON_ANCORA_IMPLEMENTATI[args.comando]
    print(
        f"\n`{args.comando}` non e' ancora disponibile: arriva con la {fase}.\n"
        "Comandi funzionanti oggi: sync-topics, generate-queries.\n",
        file=sys.stderr,
    )
    return 3


COMANDI: dict[str, Callable[[argparse.Namespace, Settings], Awaitable[int]]] = {
    "sync-topics": cmd_sync_topics,
    "generate-queries": cmd_generate_queries,
    "run-once": cmd_run_once,
    "serve": cmd_serve,
    "cost-report": cmd_cost_report,
}


def cmd_hash_password() -> int:
    """Genera l'hash della password di amministratore.

    NON tocca le Settings e non apre nessuna connessione, di proposito: e' il
    comando che produce un valore che le Settings poi PRETENDONO in produzione.
    Se caricasse la configurazione, il primo comando della procedura di
    installazione fallirebbe perche' manca il valore che sta per generare.
    """
    import getpass

    from argon2 import PasswordHasher

    if sys.stdin.isatty():
        password = getpass.getpass("Password di amministratore: ")
        conferma = getpass.getpass("Ripetila: ")
        if password != conferma:
            print("\nLe due password non coincidono.\n", file=sys.stderr)
            return 2
    else:
        # Con una pipe: `echo 'segreto' | ... sender.py hash-password`
        password = sys.stdin.readline().rstrip("\n")

    if len(password) < 8:
        print("\nUsa almeno 8 caratteri.\n", file=sys.stderr)
        return 2

    hash_generato = PasswordHasher().hash(password)
    print(
        "\nIncolla questa riga nel .env, APICI SINGOLI COMPRESI.\n"
        "Senza gli apici Docker Compose interpreta i `$` come variabili e "
        "distrugge l'hash:\n"
    )
    print(f"ADMIN_PASSWORD_HASH='{hash_generato}'\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Prima di qualunque lettura della configurazione: vedi il docstring sopra.
    if args.comando == "hash-password":
        return cmd_hash_password()

    try:
        settings = get_settings()
    except Exception as exc:  # pragma: no cover — errore di configurazione
        print(
            f"\nERRORE DI CONFIGURAZIONE\n\n{exc}\n\nControlla il file .env (vedi .env.example).\n",
            file=sys.stderr,
        )
        return 2

    setup_logging(settings)
    esito: int = asyncio.run(COMANDI[args.comando](args, settings))  # type: ignore[arg-type]
    return esito
