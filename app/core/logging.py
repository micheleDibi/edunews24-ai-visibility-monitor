"""Logging strutturato con structlog.

In produzione esce JSON su stdout (il container lo raccoglie da li'); in
sviluppo esce colorato e leggibile. Il resto del codice usa sempre
`structlog.get_logger()` e passa i dati come chiavi, non interpolati nel
messaggio: `log.info("probe ok", provider=..., latency_ms=...)`.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import Settings


def setup_logging(settings: Settings) -> None:
    livello = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=livello)
    # uvicorn installa i propri handler: li silenziamo per non avere ogni riga
    # di accesso stampata due volte, una volta per formato.
    for nome in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(nome).handlers.clear()
        logging.getLogger(nome).propagate = True

    processori: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.log_format == "json":
        processori.append(structlog.processors.JSONRenderer())
    else:
        processori.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processori,
        wrapper_class=structlog.make_filtering_bound_logger(livello),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
