"""Normalizzazione dei campi semi-strutturati che arrivano dal DB editoriale.

`tags` e `faqs` possono arrivare in tre forme diverse e non c'e' modo di
saperlo prima di guardare i dati:

* `list` — la colonna e' `text[]` o `jsonb` e asyncpg l'ha gia' deserializzata;
* `str`  — la colonna e' `text` e contiene un array JSON serializzato, oppure
           un literal di array Postgres (`{a,b,c}`);
* `None` — molti articoli hanno `faqs` a NULL.

Nessuna di queste tre deve poter interrompere una sincronizzazione. Un valore
malformato vale lista vuota piu' un log, mai un'eccezione: il costo di perdere
i tag di un articolo e' una strategia di generazione in meno, il costo di un
crash e' l'intero monitoraggio fermo.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

log = structlog.get_logger(__name__)


def parse_json_array(value: Any, *, campo: str = "?", source_id: Any = None) -> list[Any]:
    """Riporta a lista Python un campo che dovrebbe contenere un array."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        # Un oggetto singolo dove ci si aspettava un array: lo si tratta come
        # array di un elemento invece di buttarlo.
        return [value]
    if not isinstance(value, str):
        log.warning("tipo inatteso", campo=campo, source_id=source_id, tipo=type(value).__name__)
        return []

    testo = value.strip()
    if not testo or testo in {"null", "[]", "{}"}:
        return []

    try:
        decodificato = json.loads(testo)
    except json.JSONDecodeError:
        # Non e' JSON: puo' essere il literal testuale di un array Postgres.
        if testo.startswith("{") and testo.endswith("}"):
            return _parse_pg_array_literal(testo)
        log.warning("valore non decodificabile", campo=campo, source_id=source_id)
        return []

    if isinstance(decodificato, list):
        return decodificato
    if isinstance(decodificato, dict):
        return [decodificato]
    log.warning(
        "atteso array, trovato scalare",
        campo=campo,
        source_id=source_id,
        tipo=type(decodificato).__name__,
    )
    return []


def _parse_pg_array_literal(testo: str) -> list[str]:
    """Interpreta `{alpha,"beta, con virgola",gamma}`.

    Implementazione volutamente minima: copre il caso delle stringhe con
    virgolette e delle virgole interne, che e' l'unico che si incontra su
    colonne di tag.
    """
    interno = testo[1:-1]
    elementi: list[str] = []
    corrente: list[str] = []
    tra_virgolette = False
    escape = False

    for ch in interno:
        if escape:
            corrente.append(ch)
            escape = False
        elif ch == "\\":
            escape = True
        elif ch == '"':
            tra_virgolette = not tra_virgolette
        elif ch == "," and not tra_virgolette:
            elementi.append("".join(corrente).strip())
            corrente = []
        else:
            corrente.append(ch)

    coda = "".join(corrente).strip()
    if coda or elementi:
        elementi.append(coda)

    return [e for e in elementi if e and e != "NULL"]


def parse_tags(value: Any, *, source_id: Any = None, max_tags: int = 30) -> list[str]:
    """Lista di tag testuali, ripulita e deduplicata mantenendo l'ordine."""
    grezzi = parse_json_array(value, campo="tags", source_id=source_id)
    visti: set[str] = set()
    puliti: list[str] = []
    for elemento in grezzi:
        if not isinstance(elemento, str):
            continue
        tag = " ".join(elemento.split())
        if not tag or len(tag) > 80:
            continue
        chiave = tag.casefold()
        if chiave in visti:
            continue
        visti.add(chiave)
        puliti.append(tag)
        if len(puliti) >= max_tags:
            break
    return puliti


def parse_faq_questions(value: Any, *, source_id: Any = None, max_faq: int = 20) -> list[str]:
    """Solo le domande delle FAQ: le risposte non servono a generare query.

    La forma attesa e' `[{"question": ..., "answer": ...}, ...]`, ma si accetta
    anche una lista di stringhe, che qualche articolo piu' vecchio potrebbe
    avere.
    """
    grezzi = parse_json_array(value, campo="faqs", source_id=source_id)
    domande: list[str] = []
    for elemento in grezzi:
        testo: str | None = None
        if isinstance(elemento, dict):
            candidato = elemento.get("question") or elemento.get("domanda")
            if isinstance(candidato, str):
                testo = candidato
        elif isinstance(elemento, str):
            testo = elemento

        if not testo:
            continue
        domanda = " ".join(testo.split())
        # Le FAQ troppo corte non sono domande, quelle troppo lunghe non sono
        # cose che un lettore digiterebbe.
        if not 10 <= len(domanda) <= 300:
            continue
        domande.append(domanda)
        if len(domande) >= max_faq:
            break
    return domande
