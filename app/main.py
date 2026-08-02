"""Applicazione FastAPI: API, scheduler nel lifespan, SPA.

Un solo processo, `--workers 1` obbligatorio: lo scheduler e' in-process e due
worker eseguirebbero il ciclo orario due volte, raddoppiando la spesa e i probe.

L'ordine dell'avvio non e' arbitrario: prima si verifica che le credenziali del
DB editoriale non possano scrivere, poi si carica il listino, poi si chiudono i
cicli interrotti da un processo ucciso, e solo alla fine parte lo scheduler. Un
servizio che puo' scrivere sul database del giornale non deve nemmeno arrivare
ad accettare richieste.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, status

from app.api.routes import api_router
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.db.session import dispose_engine, get_sessionmaker
from app.db.source import SourceDbWritableError, SourceTableMissingError, assert_readonly
from app.services import pricing
from app.services.scheduler import (
    attendi_compiti_listener,
    crea_scheduler,
    prossime_esecuzioni,
    riconcilia_run_interrotti,
    segna_cicli_persi,
)

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    setup_logging(settings)

    # 1. Il vincolo di sola lettura sul DB editoriale si verifica all'AVVIO, non
    #    al primo sync: un servizio che puo' scrivere sul database del giornale
    #    non deve nemmeno arrivare ad accettare richieste.
    try:
        await assert_readonly(settings)
    except (SourceDbWritableError, SourceTableMissingError):
        log.exception("avvio interrotto: il DB sorgente non e' in sola lettura")
        raise

    # 2. Il listino si carica subito, cosi' un file mancante o scaduto si vede
    #    all'avvio e non alla prima fattura.
    pricing.carica_listino(settings)

    fabbrica = get_sessionmaker()

    # 3. Un container ucciso a metà ciclo lascia un `run` eternamente "in corso",
    #    e le ore in cui il processo era spento non hanno lasciato nessuna riga:
    #    prima si chiudono i run interrotti, poi si scrive il marcatore delle ore
    #    perse — APScheduler, con il jobstore in memoria, di quei fire non sa
    #    nulla e riparte come se niente fosse.
    async with fabbrica() as session:
        await riconcilia_run_interrotti(session)
        if settings.scheduler_enabled:
            await segna_cicli_persi(session, settings)

    scheduler: AsyncIOScheduler | None = None
    if settings.scheduler_enabled:
        scheduler = crea_scheduler(fabbrica, settings)
        scheduler.start()
        log.info("scheduler avviato", job=prossime_esecuzioni(scheduler))
    else:
        log.warning("scheduler disattivato da configurazione: nessun ciclo automatico")

    app.state.scheduler = scheduler
    app.state.settings = settings

    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        # I listener dello scheduler scrivono le righe di salto in task
        # separati: prima di spegnere l'engine gli si da' il tempo di finire,
        # o una riga `skipped_*` in volo andrebbe persa proprio allo shutdown.
        await attendi_compiti_listener()
        await dispose_engine()
        log.info("applicazione fermata")


def crea_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Edunews24 AI Visibility Monitor",
        description=(
            "Misura dove i motori di risposta AI citano edunews24.it e dove no, "
            "per indirizzare il lavoro editoriale. Le citazioni si guadagnano con "
            "quello che si pubblica: il volume di interrogazioni non le sposta."
        ),
        version="0.1.0",
        lifespan=lifespan,
        # La documentazione interattiva non serve a un servizio a utente unico
        # e in produzione e' superficie in piu'.
        docs_url="/api/docs" if settings.env != "production" else None,
        redoc_url=None,
    )

    # Le rotte `/api` PRIMA del frontend: il catch-all della SPA le
    # oscurerebbe se montato per primo.
    app.include_router(api_router)
    _monta_frontend(app, settings)
    return app


def _monta_frontend(app: FastAPI, settings: Settings) -> None:
    """Serve la SPA da `app/static`, se il build c'e'.

    Si monta DOPO le rotte `/api`, altrimenti il catch-all le oscurerebbe. In
    sviluppo la cartella non esiste e non si monta nulla: il frontend gira su
    Vite con il proxy verso questo processo.
    """
    statico = Path(__file__).parent / "static"
    indice = statico / "index.html"
    if not indice.exists():
        log.info("nessun build del frontend in app/static: si servono solo le API")
        return

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    # Gli asset con hash nel nome possono essere messi in cache per sempre.
    app.mount("/assets", StaticFiles(directory=str(statico / "assets")), name="assets")

    @app.get("/{percorso:path}", include_in_schema=False)
    async def spa(percorso: str) -> FileResponse:
        """Qualunque percorso NON-API restituisce la SPA.

        `StaticFiles(html=True)` da' 404 su un percorso sconosciuto: basterebbe
        un bookmark o un refresh su una rotta lato client per vedere un 404
        invece dell'applicazione. Il file richiesto si serve se esiste davvero
        (favicon, robots), altrimenti si torna all'indice.
        """
        # Un percorso `/api/*` che non ha trovato una rotta e' un errore, non una
        # pagina: restituire la SPA darebbe al chiamante dell'HTML con stato 200,
        # e un errore di battitura nel frontend si manifesterebbe come un
        # inspiegabile errore di parsing JSON invece di un 404 leggibile.
        if percorso == "api" or percorso.startswith("api/"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"endpoint inesistente: /{percorso}",
            )

        # I percorsi nascosti (`/.env`, `/.git/config`) non esistono e non devono
        # rispondere 200. Non c'e' nessuna perdita — quei file non sono nemmeno
        # nell'immagine e la SPA non contiene segreti — ma un 200 dice agli
        # scanner automatici che il percorso e' interessante, e riempie i log di
        # rumore che nasconde le richieste vere.
        if any(pezzo.startswith(".") for pezzo in percorso.split("/")):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="non trovato")

        candidato = (statico / percorso).resolve()
        if (
            percorso
            and candidato.is_file()
            # Difesa contro il path traversal: il file deve stare dentro
            # `static`, non altrove nel filesystem.
            and candidato.is_relative_to(statico.resolve())
        ):
            return FileResponse(candidato)
        return FileResponse(indice)

    log.info("frontend montato", cartella=str(statico))


app = crea_app()
