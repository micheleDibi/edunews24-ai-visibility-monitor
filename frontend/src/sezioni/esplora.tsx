/** Vista «Esplora probe»: ogni interrogazione registrata, con risposta e fonti. */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CaretDown, CaretRight, MagnifyingGlass, Warning, X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { Bottone, Distintivo, Scheletro, StatoErrore, StatoVuoto } from "../components/base";
import { api, type ProbeVisto } from "../lib/api";
import {
  ETICHETTA_STATO,
  ETICHETTA_STRATEGIA,
  dataOra,
  euro,
  intero,
  millisecondi,
} from "../lib/format";

const PAGINA = 25;

interface Filtri {
  provider: string;
  status: string;
  cited: string;
  q: string;
}

const FILTRI_VUOTI: Filtri = { provider: "", status: "", cited: "", q: "" };

export function EsploraProbe({ giorni }: { giorni: number }) {
  const [filtri, setFiltri] = useState<Filtri>(FILTRI_VUOTI);
  const [ricerca, setRicerca] = useState("");
  const [offset, setOffset] = useState(0);
  const [aperto, setAperto] = useState<number | null>(null);

  // Il periodo cambia da fuori (la sidebar), senza smontare la vista: la
  // pagina su cui si era non ha piu' senso nel periodo nuovo. Regolazione in
  // render, senza effect: niente fetch intermedia con l'offset vecchio.
  const [giorniVisti, setGiorniVisti] = useState(giorni);
  if (giorni !== giorniVisti) {
    setGiorniVisti(giorni);
    setOffset(0);
  }

  // La ricerca si digita subito ma interroga con calma: una fetch per
  // battitura sarebbe una richiesta (e un flash) a ogni lettera.
  useEffect(() => {
    const timer = setTimeout(() => {
      setFiltri((f) => (f.q === ricerca ? f : { ...f, q: ricerca }));
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [ricerca]);

  const attivi = Object.values(filtri).some(Boolean) || ricerca !== "";

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["probe", giorni, filtri, offset],
    queryFn: () =>
      api.probe({
        days: giorni,
        offset,
        limit: PAGINA,
        provider: filtri.provider || undefined,
        status: filtri.status || undefined,
        cited: filtri.cited === "" ? undefined : filtri.cited === "si",
        q: filtri.q || undefined,
      }),
    // La pagina precedente resta visibile mentre arriva la nuova: niente
    // scheletro a ogni cambio di filtro o pagina.
    placeholderData: keepPreviousData,
  });

  const aggiorna = (chiave: keyof Filtri, valore: string) => {
    setFiltri((f) => ({ ...f, [chiave]: valore }));
    setOffset(0);
  };

  return (
    <section aria-labelledby="esplora-titolo">
      <p className="text-[11px] uppercase tracking-[0.1em] text-accento">
        Registro · ultimi {giorni} giorni
      </p>
      <h1 id="esplora-titolo" className="display mt-1.5 text-xl">
        Esplora probe
      </h1>
      <p className="mt-1.5 max-w-[60ch] text-sm text-testo-55">
        Ogni interrogazione registrata, con risposta integrale e fonti.
      </p>

      <div className="mt-8 rounded-md bg-superficie p-7">
        {/* ── Filtri ──────────────────────────────────────────────────── */}
        <div className="flex flex-wrap items-center gap-2.5">
          <label className="relative">
            <span className="sr-only">Cerca nel testo della domanda</span>
            <MagnifyingGlass
              size={15}
              aria-hidden
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-testo-45"
            />
            <input
              type="search"
              value={ricerca}
              onChange={(e) => setRicerca(e.target.value)}
              placeholder="Cerca nella domanda…"
              className="min-h-11 w-60 rounded-md border border-divisore bg-superficie pl-8 pr-2.5 text-sm caret-accento hover:border-testo-45 focus-visible:border-accento sm:min-h-9"
            />
          </label>
          <Selettore
            etichetta="Provider"
            valore={filtri.provider}
            onChange={(v) => aggiorna("provider", v)}
            opzioni={[
              ["", "provider: tutti"],
              ["openai", "openai"],
              ["perplexity", "perplexity"],
              ["anthropic", "anthropic"],
              ["gemini", "gemini"],
            ]}
          />
          <Selettore
            etichetta="Esito"
            valore={filtri.status}
            onChange={(v) => aggiorna("status", v)}
            opzioni={[
              ["", "esito: tutti"],
              ["ok", "riuscito"],
              ["error", "errore"],
              ["timeout", "scaduto"],
              ["rate_limited", "limite di frequenza"],
              ["no_search", "nessuna ricerca"],
            ]}
          />
          <Selettore
            etichetta="Citato"
            valore={filtri.cited}
            onChange={(v) => aggiorna("cited", v)}
            opzioni={[
              ["", "citato: indifferente"],
              ["si", "citato: sì"],
              ["no", "citato: no"],
            ]}
          />
          {attivi && (
            <button
              type="button"
              onClick={() => {
                setFiltri(FILTRI_VUOTI);
                setRicerca("");
                setOffset(0);
              }}
              className="inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-md px-1.5 text-sm font-medium text-accento transition-colors hover:bg-accento/10 active:bg-accento/18 sm:min-h-9"
            >
              <X size={14} aria-hidden />
              Azzera
            </button>
          )}
        </div>

        {/* ── Tabella ─────────────────────────────────────────────────── */}
        {error ? (
          <div className="mt-5">
            <StatoErrore errore={error} riprova={() => void refetch()} />
          </div>
        ) : isPending ? (
          <div className="mt-5">
            <Scheletro righe={8} />
          </div>
        ) : !data?.elementi.length ? (
          <div className="mt-5">
            <StatoVuoto
              titolo="Nessun probe con questi filtri."
              cosaFare={
                attivi
                  ? "Prova ad azzerare i filtri, o ad allargare il periodo."
                  : "Non ci sono ancora probe nel periodo scelto. Allarga il periodo o esegui un ciclo dallo stato del sistema."
              }
            />
          </div>
        ) : (
          <>
            <div className="scorrevole -mx-4 mt-5 px-4">
              <table className="tabella min-w-[56rem]">
                <thead>
                  <tr>
                    <th scope="col" className="w-10">
                      <span className="sr-only">Dettaglio</span>
                    </th>
                    <th scope="col">Data</th>
                    <th scope="col">Domanda</th>
                    <th scope="col">Provider</th>
                    <th scope="col">Esito</th>
                    <th scope="col">Segnali</th>
                    <th scope="col">Fonti</th>
                  </tr>
                </thead>
                <tbody>
                  {data.elementi.map((p) => (
                    <Riga
                      key={p.id}
                      probe={p}
                      espanso={aperto === p.id}
                      onToggle={() => setAperto(aperto === p.id ? null : p.id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="cifre text-sm text-testo-55">
                {offset + 1}–{Math.min(offset + PAGINA, data.totale)} di {intero(data.totale)}
              </p>
              <div className="flex gap-2">
                <Bottone
                  onClick={() => setOffset(Math.max(0, offset - PAGINA))}
                  disabilitato={offset === 0}
                >
                  Precedenti
                </Bottone>
                <Bottone
                  onClick={() => setOffset(offset + PAGINA)}
                  disabilitato={offset + PAGINA >= data.totale}
                >
                  Successivi
                </Bottone>
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function Selettore({
  etichetta,
  valore,
  onChange,
  opzioni,
}: {
  etichetta: string;
  valore: string;
  onChange: (v: string) => void;
  opzioni: Array<[string, string]>;
}) {
  return (
    <select
      aria-label={etichetta}
      value={valore}
      onChange={(e) => onChange(e.target.value)}
      className="min-h-11 cursor-pointer rounded-md border border-divisore bg-superficie px-2.5 text-sm text-testo hover:border-testo-45 sm:min-h-9"
    >
      {opzioni.map(([v, testo]) => (
        <option key={v} value={v}>
          {testo}
        </option>
      ))}
    </select>
  );
}

function Riga({
  probe,
  espanso,
  onToggle,
}: {
  probe: ProbeVisto;
  espanso: boolean;
  onToggle: () => void;
}) {
  const citate = probe.citazioni.filter((c) => c.kind === "citation");
  const recuperate = probe.citazioni.filter((c) => c.kind === "source");
  const Caret = espanso ? CaretDown : CaretRight;

  return (
    <>
      <tr className="align-top">
        <td className="!py-1.5 !pr-0">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={espanso}
            // Il nome dice QUALE riga: venticinque bottoni «apri il dettaglio»
            // identici sono un labirinto per chi naviga con uno screen reader.
            aria-label={`${espanso ? "Chiudi" : "Apri"} il dettaglio: ${probe.query_text}`}
            className="grid min-h-11 min-w-11 cursor-pointer place-items-center rounded-sm text-testo-45 transition-colors hover:bg-testo/6 sm:min-h-8 sm:min-w-8"
          >
            <Caret size={14} aria-hidden />
          </button>
        </td>
        <td className="cifre whitespace-nowrap text-xs text-testo-55">
          {dataOra(probe.created_at)}
        </td>
        <td className="max-w-md">
          <span className="block truncate text-sm text-testo">{probe.query_text}</span>
          <span className="mt-0.5 block text-xs text-testo-45">
            {ETICHETTA_STRATEGIA[probe.query_strategy] ?? probe.query_strategy}
            {probe.mode === "memory" && " · memoria (senza ricerca)"}
          </span>
        </td>
        <td className="text-sm">
          {probe.provider}
          <span className="block text-xs text-testo-45">{probe.model}</span>
        </td>
        <td>
          <Distintivo
            tinta={
              probe.status === "ok"
                ? "neutro"
                : probe.status === "no_search"
                  ? "pervinca"
                  : "allarme"
            }
            titolo={
              probe.status === "no_search"
                ? "Il provider ha risposto senza cercare: non è «non citato», è «non misurato». Escluso da ogni denominatore."
                : undefined
            }
          >
            {ETICHETTA_STATO[probe.status] ?? probe.status}
          </Distintivo>
        </td>
        <td>
          <span className="flex flex-wrap gap-1">
            {probe.edunews_cited && <Distintivo tinta="accento">citato</Distintivo>}
            {probe.target_hit && <Distintivo tinta="contorno">articolo giusto</Distintivo>}
            {probe.edunews_retrieved && !probe.edunews_cited && (
              <Distintivo tinta="pervinca">recuperato</Distintivo>
            )}
            {probe.edunews_mention && <Distintivo tinta="neutro">mention</Distintivo>}
          </span>
        </td>
        <td className="cifre text-sm">
          {citate.length}
          <span className="text-testo-45"> / {recuperate.length}</span>
        </td>
      </tr>
      {espanso && (
        <tr>
          <td colSpan={7} className="!p-0 pb-4">
            <div className="mb-4 flex flex-col gap-4 rounded-md bg-neutro-900 px-6 py-5">
              <Dettaglio probe={probe} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function Dettaglio({ probe }: { probe: ProbeVisto }) {
  return (
    <>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Voce etichetta="Latenza" valore={millisecondi(probe.latency_ms)} />
        <Voce
          etichetta="Ricerche"
          valore={probe.search_calls === null ? "—" : String(probe.search_calls)}
        />
        <Voce
          etichetta="Costo"
          valore={probe.costo_eur === null ? "—" : euro(probe.costo_eur)}
          nota={probe.costo_stimato ? "stimato" : undefined}
        />
        <Voce etichetta="Ciclo" valore={`#${probe.run_id}`} />
      </dl>

      {probe.error && (
        <p className="text-xs text-accento-300">
          <Warning size={14} className="mr-1.5 inline align-[-2px]" aria-hidden />
          <span className="font-mono break-words">{probe.error}</span>
        </p>
      )}

      {probe.answer_text ? (
        <div>
          <p className="text-[10px] uppercase tracking-[0.1em] text-testo-45">
            Risposta integrale
          </p>
          <p className="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-testo-70">
            {probe.answer_text}
          </p>
        </div>
      ) : (
        <p className="text-sm text-testo-55">
          Testo della risposta rimosso dalla retention: non significa che non c'era.
        </p>
      )}

      {probe.citazioni.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-[0.1em] text-testo-45">Fonti</p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {probe.citazioni.map((c, i) => (
              <li key={`${c.kind}-${i}`} className="flex flex-wrap items-center gap-2.5 text-xs">
                <Distintivo tinta={c.kind === "citation" ? "accento" : "neutro"}>
                  {c.kind === "citation" ? "citata" : "recuperata"}
                </Distintivo>
                <span className={`cifre ${c.is_own ? "text-accento" : "text-testo-70"}`}>
                  {c.domain === "unresolved" ? "dominio non risolto" : c.domain}
                </span>
                {c.url && (
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noreferrer"
                    className="min-w-0 flex-1 truncate text-accento underline decoration-accento/40 underline-offset-2 hover:decoration-accento"
                  >
                    {c.title || c.url}
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function Voce({
  etichetta,
  valore,
  nota,
}: {
  etichetta: string;
  valore: string;
  nota?: string;
}) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-[0.1em] text-testo-45">{etichetta}</dt>
      <dd className="cifre mt-1 text-sm font-medium">
        {valore}
        {nota && <span className="ml-1.5 text-xs font-normal text-testo-45">{nota}</span>}
      </dd>
    </div>
  );
}
