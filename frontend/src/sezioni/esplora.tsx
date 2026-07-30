/** Sezione 7 — Esplora probe. */

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { useState } from "react";

import { Bottone, Card, Distintivo, Scheletro, StatoErrore, StatoVuoto } from "../components/base";
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
  const [offset, setOffset] = useState(0);
  const [aperto, setAperto] = useState<number | null>(null);

  const attivi = Object.values(filtri).some(Boolean);

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
  });

  const aggiorna = (chiave: keyof Filtri, valore: string) => {
    setFiltri((f) => ({ ...f, [chiave]: valore }));
    setOffset(0);
  };

  return (
    <Card
      id="esplora"
      titolo="Esplora probe"
      descrizione="Ogni interrogazione registrata. Apri una riga per la risposta integrale e le fonti estratte."
      azioni={
        attivi ? (
          <Bottone
            onClick={() => {
              setFiltri(FILTRI_VUOTI);
              setOffset(0);
            }}
          >
            <X size={16} aria-hidden />
            Azzera filtri
          </Bottone>
        ) : undefined
      }
    >
      <div className="mb-3 flex flex-wrap gap-2">
        <label className="flex items-center gap-2 text-sm">
          <span className="sr-only">Cerca nel testo della domanda</span>
          <input
            type="search"
            value={filtri.q}
            onChange={(e) => aggiorna("q", e.target.value)}
            placeholder="Cerca nella domanda…"
            className="min-h-11 w-56 rounded-[var(--radius-controllo)] border border-grafite-tenue bg-foglio px-2.5 text-sm sm:min-h-9"
          />
        </label>
        <Selettore
          etichetta="Provider"
          valore={filtri.provider}
          onChange={(v) => aggiorna("provider", v)}
          opzioni={[
            ["", "tutti"],
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
            ["", "tutti"],
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
            ["", "indifferente"],
            ["si", "sì"],
            ["no", "no"],
          ]}
        />
      </div>

      {error ? (
        <StatoErrore errore={error} riprova={() => void refetch()} />
      ) : isPending ? (
        <Scheletro righe={8} />
      ) : !data?.elementi.length ? (
        <StatoVuoto
          titolo="Nessun probe con questi filtri."
          cosaFare={
            attivi
              ? "Prova ad azzerare i filtri con il pulsante in alto a destra, o ad allargare il periodo."
              : "Non ci sono ancora probe nel periodo scelto. Allarga il periodo o esegui un ciclo dallo stato del sistema."
          }
        />
      ) : (
        <>
          <div className="scorrevole -mx-4 px-4">
            <table className="w-full min-w-[46rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-grafite-tenue text-left">
                  <th scope="col" className="w-6 py-2" />
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Data
                  </th>
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Domanda
                  </th>
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Provider
                  </th>
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Esito
                  </th>
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Segnali
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Fonti
                  </th>
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

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <p className="cifre text-sm text-grafite">
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
    </Card>
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
    <label className="flex items-center gap-2 text-sm">
      <span className="text-grafite">{etichetta}</span>
      <select
        value={valore}
        onChange={(e) => onChange(e.target.value)}
        className="min-h-11 cursor-pointer rounded-[var(--radius-controllo)] border border-grafite-tenue bg-foglio px-2 text-sm sm:min-h-9"
      >
        {opzioni.map(([v, testo]) => (
          <option key={v} value={v}>
            {testo}
          </option>
        ))}
      </select>
    </label>
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

  return (
    <>
      <tr className="border-b border-grafite-tenue align-top transition-colors hover:bg-gesso">
        <td className="py-3">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={espanso}
            aria-label={espanso ? "Chiudi il dettaglio" : "Apri il dettaglio"}
            className="cursor-pointer p-1 text-grafite"
          >
            {espanso ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>
        </td>
        <td className="cifre whitespace-nowrap py-3 pr-3 text-xs text-grafite">
          {dataOra(probe.created_at)}
        </td>
        <td className="max-w-md py-3 pr-3">
          <span className="block truncate">{probe.query_text}</span>
          <span className="mt-0.5 block text-xs text-grafite">
            {ETICHETTA_STRATEGIA[probe.query_strategy] ?? probe.query_strategy}
            {probe.mode === "memory" && " · memoria (senza ricerca)"}
          </span>
        </td>
        <td className="py-3 pr-3">
          <span className="block">{probe.provider}</span>
          <span className="block font-mono text-xs text-grafite">{probe.model}</span>
        </td>
        <td className="py-3 pr-3">
          <Distintivo
            tinta={
              probe.status === "ok"
                ? "alloro"
                : probe.status === "no_search"
                  ? "ottone"
                  : "sigillo"
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
        <td className="py-3 pr-3">
          <span className="flex flex-wrap gap-1">
            {probe.edunews_cited && <Distintivo tinta="timbro">citato</Distintivo>}
            {probe.target_hit && <Distintivo tinta="alloro">articolo giusto</Distintivo>}
            {probe.edunews_retrieved && !probe.edunews_cited && (
              <Distintivo tinta="ottone">recuperato</Distintivo>
            )}
            {probe.edunews_mention && <Distintivo tinta="grafite">mention</Distintivo>}
          </span>
        </td>
        <td className="cifre py-3 text-sm">
          {citate.length}
          <span className="text-xs text-grafite"> citate / {recuperate.length} recup.</span>
        </td>
      </tr>
      {espanso && (
        <tr className="border-b border-grafite-tenue bg-gesso">
          <td colSpan={7} className="px-3 py-4">
            <Dettaglio probe={probe} />
          </td>
        </tr>
      )}
    </>
  );
}

function Dettaglio({ probe }: { probe: ProbeVisto }) {
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Voce etichetta="Latenza" valore={millisecondi(probe.latency_ms)} />
        <Voce
          etichetta="Ricerche"
          valore={probe.search_calls === null ? "—" : String(probe.search_calls)}
        />
        <Voce
          etichetta="Costo"
          valore={probe.costo_eur === null ? "—" : euro(probe.costo_eur)}
          nota={probe.costo_stimato ? "stimato dal listino" : undefined}
        />
        <Voce etichetta="Ciclo" valore={`#${probe.run_id}`} />
      </dl>

      {probe.error && (
        <div className="rounded-[var(--radius-controllo)] bg-sigillo-tenue p-3 text-sm">
          <p className="font-medium text-sigillo">Errore riportato</p>
          <p className="mt-1 break-words font-mono text-xs">{probe.error}</p>
        </div>
      )}

      {probe.answer_text ? (
        <div>
          <h4 className="text-sm font-medium">Risposta integrale</h4>
          <p className="mt-1 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-[var(--radius-controllo)] bg-foglio p-3 text-sm">
            {probe.answer_text}
          </p>
        </div>
      ) : (
        <p className="text-sm text-grafite">
          Testo della risposta rimosso dalla retention: non significa che non c'era.
        </p>
      )}

      {probe.citazioni.length > 0 && (
        <div>
          <h4 className="text-sm font-medium">Fonti</h4>
          <ul className="mt-1 space-y-1">
            {probe.citazioni.map((c, i) => (
              <li
                key={`${c.kind}-${i}`}
                className={`flex flex-wrap items-center gap-2 rounded-[var(--radius-controllo)] px-2 py-1.5 text-sm ${
                  c.is_own ? "bg-timbro-tenue" : "bg-foglio"
                }`}
              >
                <Distintivo tinta={c.kind === "citation" ? "timbro" : "grafite"}>
                  {c.kind === "citation" ? "citata" : "recuperata"}
                </Distintivo>
                <span className="font-mono text-xs">
                  {c.domain === "unresolved" ? "dominio non risolto" : c.domain}
                </span>
                {c.url && (
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noreferrer"
                    className="min-w-0 flex-1 truncate text-xs text-timbro underline decoration-timbro/40 underline-offset-2"
                  >
                    {c.title || c.url}
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
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
      <dt className="text-xs text-grafite">{etichetta}</dt>
      <dd className="cifre font-medium">
        {valore}
        {nota && <span className="ml-1 text-xs font-normal text-ottone">({nota})</span>}
      </dd>
    </div>
  );
}
