"""Parser delle citazioni a tre livelli e normalizzazione dei domini.

I tre livelli, in cascata su ogni risposta:

1. **citazioni strutturate** — le fonti che il provider restituisce in un campo
   proprio. E' la fonte piu' affidabile e l'unica su cui si costruisce la
   metrica. Ogni adapter la estrae dal suo `raw_response`.
2. **ripiego su markdown/URL nudi** — regex sui link e sugli URL nel testo,
   per i provider che citano inline. Vale solo se il livello 1 non ha prodotto
   nulla: altrimenti si conterebbero due volte le stesse fonti.
3. **brand mention senza link** — il nome del giornale nel testo, senza URL
   corrispondente. Non e' una citazione ed e' registrata a parte.

## Le due colonne che sembrano una

`edunews_cited` e `edunews_mention` non vanno mai sommate. La citazione indica
che il retrieval ha pescato il giornale; la mention indica che il modello lo
conosce e lo nomina a memoria. Il primo si puo' influenzare scrivendo articoli
migliori, il secondo no — e confonderli renderebbe la dashboard incapace di
dire quale dei due sta succedendo.

## Mai inventare un dominio

Se un URL e' un wrapper di redirect da cui il dominio reale non e' estraibile,
si salva l'URL cosi' com'e' e si marca `domain = 'unresolved'`. Il dominio piu'
plausibile e' comunque una supposizione, e una supposizione dentro la classifica
di "chi occupa il posto" e' peggio di un buco dichiarato.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import structlog

from app.clients.base import CitazioneGrezza, TipoCitazione
from app.models.citation import DOMINIO_NON_RISOLTO
from app.services.querygen.normalize import solo_alfanumerico

log = structlog.get_logger(__name__)

# Host che sono involucri di redirect: il dominio reale non e' ricavabile dal
# solo URL. Verificato il 2026-07-30: e' il caso di `groundingChunks[].web.uri`
# nella vecchia API generateContent di Gemini.
HOST_WRAPPER = frozenset(
    {
        "vertexaisearch.cloud.google.com",
        "www.google.com",  # /url?q=... — solo quando il path e' /url
    }
)

# Parametri di tracciamento che cambiano l'URL ma non la pagina. OpenAI ha
# storicamente aggiunto `?utm_source=openai`: tenerli farebbe contare due volte
# lo stesso articolo.
_PREFISSI_TRACCIAMENTO = ("utm_", "ref_", "mc_eid", "mc_cid", "_hs")
_NOMI_TRACCIAMENTO = frozenset({"fbclid", "gclid", "yclid", "igshid", "si", "msclkid"})


def _e_parametro_di_tracciamento(nome: str) -> bool:
    minuscolo = nome.lower()
    return minuscolo in _NOMI_TRACCIAMENTO or minuscolo.startswith(_PREFISSI_TRACCIAMENTO)


_LINK_MARKDOWN = re.compile(r"\[[^\]]*\]\((https?://[^\s)]+)\)")
_URL_NUDO = re.compile(r"https?://[^\s<>\"'\])]+")

# Il brand in qualunque grafia. Si confronta sulla forma ridotta a lettere e
# cifre, cosi' "edu news 24" e "EduNews24" ricadono nello stesso caso.
_BRAND_COLLASSATO = "edunews"


@dataclass(frozen=True)
class CitazioneNormalizzata:
    domain: str
    url: str | None
    title: str | None
    kind: TipoCitazione
    position: int | None
    is_own: bool
    own_slug: str | None


@dataclass
class EsitoParsing:
    citazioni: list[CitazioneNormalizzata]
    edunews_cited: bool
    edunews_mention: bool
    edunews_retrieved: bool
    slug_propri: set[str]
    # Livello che ha effettivamente prodotto le citazioni, per i log.
    livello: str


def normalizza_host(url: str | None) -> str:
    """Host in minuscolo senza `www.`, oppure la sentinella se non ricavabile."""
    if not url:
        return DOMINIO_NON_RISOLTO
    try:
        parti = urlsplit(url.strip())
    except ValueError:
        return DOMINIO_NON_RISOLTO

    host = (parti.hostname or "").lower()
    if not host:
        return DOMINIO_NON_RISOLTO

    if host in HOST_WRAPPER and (host != "www.google.com" or parti.path.startswith("/url")):
        # Involucro di redirect: il dominio vero sta dietro una HTTP call che
        # non facciamo. Meglio dichiararlo che indovinarlo.
        return DOMINIO_NON_RISOLTO

    return host.removeprefix("www.")


def pulisci_url(url: str | None) -> str | None:
    """Toglie i parametri di tracciamento e il frammento, tiene il resto."""
    if not url:
        return None
    try:
        parti = urlsplit(url.strip())
    except ValueError:
        return url

    query_utili = [
        pezzo
        for pezzo in parti.query.split("&")
        if pezzo and not _e_parametro_di_tracciamento(pezzo.split("=", 1)[0])
    ]
    ricostruito = f"{parti.scheme}://{parti.netloc}{parti.path}"
    if query_utili:
        ricostruito += "?" + "&".join(query_utili)
    return ricostruito


def e_dominio_proprio(host: str, own_domain: str) -> bool:
    """Confronto sull'host, non per sottostringa.

    Cercare "edunews24.it" dentro l'URL darebbe falsi positivi su un
    aggregatore che lo mette nel path o in un parametro. I sottodomini contano.
    """
    proprio = own_domain.lower().removeprefix("www.")
    return host == proprio or host.endswith("." + proprio)


def estrai_slug(url: str | None) -> str | None:
    """Ultimo segmento del path: su edunews24.it l'URL e' /{categoria}/{slug}."""
    if not url:
        return None
    try:
        percorso = urlsplit(url).path
    except ValueError:
        return None
    segmenti = [s for s in percorso.split("/") if s]
    if not segmenti:
        return None
    ultimo = segmenti[-1]
    # Toglie un'eventuale estensione (.html, .amp) senza toccare gli slug che
    # contengono punti per altre ragioni.
    for suffisso in (".html", ".htm", ".amp", ".php"):
        ultimo = ultimo.removesuffix(suffisso)
    return ultimo or None


def contiene_mention_brand(testo: str | None) -> bool:
    return bool(testo) and _BRAND_COLLASSATO in solo_alfanumerico(testo or "")


def _da_testo(testo: str) -> list[CitazioneGrezza]:
    """Livello 2: link markdown e URL nudi, deduplicati mantenendo l'ordine."""
    trovati: list[str] = _LINK_MARKDOWN.findall(testo)
    trovati.extend(u for u in _URL_NUDO.findall(testo) if u not in trovati)

    visti: set[str] = set()
    citazioni: list[CitazioneGrezza] = []
    for url in trovati:
        # La punteggiatura di fine frase finisce spesso dentro l'URL nudo.
        pulito = url.rstrip(".,;:!?)")
        chiave = pulito.rstrip("/").lower()
        if chiave in visti:
            continue
        visti.add(chiave)
        citazioni.append(CitazioneGrezza(url=pulito, kind="citation", position=len(citazioni) + 1))
    return citazioni


def analizza(
    *,
    answer_text: str | None,
    citazioni_strutturate: list[CitazioneGrezza],
    own_domain: str,
) -> EsitoParsing:
    """Applica i tre livelli e produce le citazioni normalizzate.

    Il confronto con gli slug dell'articolo di origine — cioe' `target_hit` —
    sta in `e_target_hit`, perche' richiede un dato che viene dal database e
    non dalla risposta del provider.
    """
    grezze = list(citazioni_strutturate)
    livello = "strutturato"

    if not grezze:
        # Livello 2 solo se il livello 1 non ha prodotto nulla: applicarlo
        # sempre conterebbe due volte le fonti dei provider che citano sia in
        # modo strutturato sia inline.
        grezze = _da_testo(answer_text) if answer_text else []
        livello = "testo" if grezze else "nessuno"

    normalizzate: list[CitazioneNormalizzata] = []
    visti: set[tuple[str, str | None, TipoCitazione]] = set()
    slug_propri: set[str] = set()
    cited = retrieved = False

    for grezza in grezze:
        url = pulisci_url(grezza.url)
        host = normalizza_host(grezza.url)
        propria = host != DOMINIO_NON_RISOLTO and e_dominio_proprio(host, own_domain)
        slug = estrai_slug(url) if propria else None

        chiave = (host, (url or "").rstrip("/").lower() or None, grezza.kind)
        if chiave in visti:
            continue
        visti.add(chiave)

        if propria:
            if grezza.kind == "citation":
                cited = True
            retrieved = True
            if slug:
                slug_propri.add(slug)

        normalizzate.append(
            CitazioneNormalizzata(
                domain=host,
                url=url,
                title=grezza.title,
                kind=grezza.kind,
                position=grezza.position,
                is_own=propria,
                own_slug=slug,
            )
        )

    # Livello 3: il brand nominato senza URL corrispondente. Se il dominio e'
    # fra le citazioni non e' una mention "nuda" ed e' gia' contato come
    # citazione.
    mention = contiene_mention_brand(answer_text) and not cited

    return EsitoParsing(
        citazioni=normalizzate,
        edunews_cited=cited,
        edunews_mention=mention,
        edunews_retrieved=retrieved,
        slug_propri=slug_propri,
        livello=livello,
    )


def e_target_hit(esito: EsitoParsing, slug_attesi: set[str] | None) -> bool:
    """Citato proprio l'articolo che ha generato la query, non un altro."""
    if not slug_attesi or not esito.slug_propri:
        return False
    return bool(esito.slug_propri & slug_attesi)
