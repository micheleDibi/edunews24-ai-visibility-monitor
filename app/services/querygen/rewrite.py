"""Naturalizzazione LLM del lotto di query.

Le domande da template sono corrette ma riconoscibili: "concorso docenti 2026:
quali sono le scadenze?" non e' come scrive un genitore alle undici di sera.
Questo passaggio le distende, in UNA sola chiamata per lotto.

E' un passaggio opzionale e sacrificabile: se il modello non risponde,
risponde male, cambia lingua o rimescola l'ordine, si usano i template. Il
sistema non si ferma per un miglioramento cosmetico.

Il client e' iniettabile: qui c'e' un'implementazione minima su endpoint
compatibile OpenAI, e la Fase 3 la sostituira' con l'adapter verificato sulla
documentazione corrente senza toccare questa logica.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable

import httpx
import structlog

from app.core.config import Settings
from app.services.querygen.normalize import solo_alfanumerico
from app.services.querygen.validate import valida_testo

log = structlog.get_logger(__name__)

Riscrittore = Callable[[list[str]], Awaitable[list[str]]]

# Le graffe letterali sono RADDOPPIATE perche' questa stringa passa da
# `.format(n=...)`. Con graffe singole, `{"domande": [...]}` viene letto come un
# campo da sostituire e solleva `KeyError: '"domande"'`: la riscrittura falliva
# a ogni singolo lotto, in silenzio, ripiegando sempre sui template. Il ripiego
# funzionava troppo bene per far notare che la funzione era morta.
ISTRUZIONE = (
    "Riscrivi ciascuna di queste domande come le scriverebbe un genitore, un docente "
    "o uno studente italiano che cerca informazioni.\n"
    "Mantieni identico il contenuto informativo e le entità specifiche (date, importi, "
    "nomi propri, sigle).\n"
    "Varia la forma: a volte una domanda completa, a volte una frase secca.\n"
    "Non aggiungere nomi di testate, siti o giornali.\n"
    'Rispondi con un oggetto JSON {{"domande": [...]}} contenente esattamente '
    "{n} stringhe, nello stesso ordine delle domande ricevute."
)

# Parole abbastanza lunghe da portare significato, PIU' ogni gruppo di cifre di
# qualunque lunghezza. I numeri contano quanto le parole: in questo dominio sono
# l'anno del concorso, l'importo del bonus, la scadenza della domanda — cioe'
# esattamente le entita' che la riscrittura deve conservare, e spesso l'unica
# cosa che distingue un articolo da un altro ("bonus 500 euro" vs "bonus 1.000
# euro").
_PAROLE_LUNGHE = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
_CIFRE = re.compile(r"\d+")


def _token_significativi(testo: str) -> set[str]:
    parole = {solo_alfanumerico(t) for t in _PAROLE_LUNGHE.findall(testo)}
    return (parole | set(_CIFRE.findall(testo))) - {""}


def _token_distintivi(token_per_indice: list[set[str]]) -> list[set[str]]:
    """Per ogni originale, i token che nessun altro del lotto possiede.

    Il controllo sul numero di elementi non intercetta un modello che
    restituisce le stesse N domande in ordine diverso: l'accoppiamento per
    indice assocerebbe la riscrittura della query 3 alla query 1, e da quel
    momento `target_hit` misurerebbe la cosa sbagliata senza alcun errore
    visibile.

    Chiedere "almeno un token in comune con l'originale" non basta, perche' le
    query di un lotto condividono il vocabolario del dominio: "concorso",
    "docenti", "scuola" compaiono in mezzo catalogo e un riordino le
    soddisferebbe tutte. Serve un token che identifichi *quell'* originale
    dentro *questo* lotto.
    """
    distintivi: list[set[str]] = []
    for i, token in enumerate(token_per_indice):
        altrove: set[str] = set()
        for j, altri in enumerate(token_per_indice):
            if j != i:
                altrove |= altri
        distintivi.append(token - altrove)
    return distintivi


def _parla_dello_stesso_argomento(
    riscritta: str, token_originale: set[str], token_distintivi: set[str]
) -> bool:
    """Limite noto: se due originali del lotto hanno token identici, uno scambio
    fra loro non e' rilevabile — ma in quel caso le due query chiedono la stessa
    cosa e lo scambio non cambia la misura."""
    token_riscritta = _token_significativi(riscritta)
    if token_distintivi:
        return bool(token_distintivi & token_riscritta)
    if token_originale:
        return bool(token_originale & token_riscritta)
    return True


async def riscrivi_lotto(
    testi: list[str],
    riscrittore: Riscrittore,
    *,
    own_domain: str = "edunews24.it",
) -> list[str]:
    """Restituisce il lotto riscritto, con ripiego per elemento sul template.

    Mai solleva. Nel peggiore dei casi restituisce `testi` invariato.
    """
    if not testi:
        return testi

    try:
        riscritte = await riscrittore(testi)
    except Exception as exc:
        log.warning("riscrittura fallita, si usano i template", errore=str(exc))
        return testi

    if not isinstance(riscritte, list) or len(riscritte) != len(testi):
        log.warning(
            "riscrittura scartata: numero di elementi diverso",
            attesi=len(testi),
            ricevuti=len(riscritte) if isinstance(riscritte, list) else None,
        )
        return testi

    token_originali = [_token_significativi(t) for t in testi]
    distintivi = _token_distintivi(token_originali)

    risultato: list[str] = []
    scartate = 0
    for i, (originale, riscritta) in enumerate(zip(testi, riscritte, strict=True)):
        if not isinstance(riscritta, str):
            risultato.append(originale)
            scartate += 1
            continue
        candidata = " ".join(riscritta.split())
        # La riscrittura viene rivalidata: il modello puo' reintrodurre il
        # brand che i template non contenevano.
        if not valida_testo(candidata, own_domain).valida or not _parla_dello_stesso_argomento(
            candidata, token_originali[i], distintivi[i]
        ):
            risultato.append(originale)
            scartate += 1
            continue
        risultato.append(candidata)

    if scartate:
        log.info("riscritture scartate, template mantenuti", quante=scartate, su=len(testi))
    return risultato


def client_openai(settings: Settings) -> Riscrittore | None:
    """Riscrittore su endpoint compatibile OpenAI. `None` se manca la chiave.

    Corpo della richiesta volutamente minimo (modello, messaggi, formato):
    piu' parametri si mandano, piu' e' probabile che un modello nuovo ne
    rifiuti uno e faccia fallire un passaggio che doveva solo abbellire.
    """
    if not settings.openai_api_key:
        return None

    async def _riscrivi(testi: list[str]) -> list[str]:
        corpo = {
            "model": settings.query_rewrite_model,
            "messages": [
                {"role": "system", "content": ISTRUZIONE.format(n=len(testi))},
                {"role": "user", "content": json.dumps(testi, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            risposta = await client.post(
                f"{settings.openai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=corpo,
            )
            risposta.raise_for_status()
            dati = risposta.json()

        contenuto = dati["choices"][0]["message"]["content"]
        decodificato = json.loads(contenuto)
        if isinstance(decodificato, list):
            return decodificato
        if isinstance(decodificato, dict):
            for chiave in ("domande", "questions", "queries", "risultato"):
                if isinstance(decodificato.get(chiave), list):
                    return decodificato[chiave]
        raise ValueError(f"forma di risposta inattesa: {type(decodificato).__name__}")

    return _riscrivi
