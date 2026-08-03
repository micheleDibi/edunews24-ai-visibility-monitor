/** Vista «Provider e categorie», piu' la classifica dei domini (in Panoramica). */

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { Scheletro, StatoErrore, StatoVuoto } from "../components/base";
import { api, type CellaCategoria, type Tasso } from "../lib/api";
import { euro, intero, millisecondi, percentuale, serieDi } from "../lib/format";

/* ------------------------------------------------------------------ Vista */

export function Confronti({ giorni }: { giorni: number }) {
  return (
    <section aria-labelledby="confronti-titolo">
      <p className="text-[11px] uppercase tracking-[0.1em] text-accento">
        Confronti · ultimi {giorni} giorni
      </p>
      <h1 id="confronti-titolo" className="display mt-1.5 text-xl">
        Provider e categorie
      </h1>
      <p className="mt-1.5 max-w-[60ch] text-sm text-testo-55">
        Chi cita di più, e su quali argomenti.
      </p>

      <div className="mt-8 space-y-6">
        <Provider giorni={giorni} />
        <Categorie giorni={giorni} />
      </div>
    </section>
  );
}

/**
 * La cella-tasso del design: il valore sopra, il conto e l'intervallo sotto.
 * Le tre soglie restano quelle di sempre: sotto i 10 probe un trattino (un
 * numero su tre casi non è una misura), sotto i 30 il valore è sbiadito.
 */
function CellaTasso({ tasso, smorzata = false }: { tasso: Tasso; smorzata?: boolean }) {
  const n = tasso.denominatore;
  const misurabile = tasso.tasso !== null;
  const colore = !misurabile
    ? "text-testo-45"
    : smorzata
      ? "text-testo-60"
      : tasso.affidabile
        ? "text-testo"
        : "text-testo-55";
  const sotto =
    n === 0
      ? "nessun dato"
      : !misurabile
        ? `n = ${intero(n)}`
        : tasso.ic_basso !== null && tasso.ic_alto !== null
          ? `${intero(tasso.numeratore)}/${intero(n)} · ${percentuale(tasso.ic_basso, 0)}–${percentuale(tasso.ic_alto, 0)}`
          : `${intero(tasso.numeratore)}/${intero(n)}`;
  return (
    <>
      <span className={`display cifre text-[16px] ${colore}`}>
        {misurabile ? percentuale(tasso.tasso!) : "—"}
      </span>
      <span className="cifre mt-0.5 block whitespace-nowrap text-xs text-testo-45">{sotto}</span>
    </>
  );
}

/* --------------------------------------------------------------- Provider */

export function Provider({ giorni }: { giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["provider", giorni],
    queryFn: () => api.provider(giorni),
  });

  return (
    <div className="rounded-md bg-superficie p-7">
      <h2 className="display text-md">Provider</h2>
      <p className="mt-1 max-w-prose text-sm text-testo-55">
        «Memoria» misura cosa il modello ricorda, non cosa trova: non si confronta con le
        altre colonne.
      </p>
      {error ? (
        <div className="mt-4">
          <StatoErrore errore={error} riprova={() => void refetch()} />
        </div>
      ) : isPending ? (
        <div className="mt-4">
          <Scheletro righe={4} />
        </div>
      ) : !data?.length ? (
        <div className="mt-4">
          <StatoVuoto
            titolo="Nessun provider ha ancora prodotto probe riusciti."
            cosaFare="Aggiungi almeno una chiave API nel .env (OPENAI_API_KEY, PERPLEXITY_API_KEY, ANTHROPIC_API_KEY) e riavvia il container."
          />
        </div>
      ) : (
        <div className="scorrevole -mx-4 mt-4 px-4">
          <table className="tabella min-w-[54rem]">
            <thead>
              <tr className="align-bottom">
                <th scope="col">Provider</th>
                <th scope="col">Citato</th>
                <th scope="col">Mention</th>
                <th scope="col">Articolo giusto</th>
                <th scope="col" className="border-l border-divisore !pl-3.5">
                  Memoria
                </th>
                <th scope="col">Latenza</th>
                <th scope="col">Ricerche</th>
                <th scope="col">Costo</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.provider}>
                  <th scope="row" className="pr-3 text-left align-top font-normal">
                    <span className="flex items-center gap-2.5 pt-0.5 text-sm">
                      <svg width="18" height="4" viewBox="0 0 18 4" className="shrink-0" aria-hidden>
                        <line
                          x1="0"
                          y1="2"
                          x2="18"
                          y2="2"
                          stroke={serieDi(r.provider).colore}
                          strokeWidth="2"
                          strokeDasharray={serieDi(r.provider).tratto}
                        />
                      </svg>
                      {r.provider}
                    </span>
                    <span className="mt-1 block pl-7 text-xs text-testo-45">
                      {r.model}
                      {r.probe_falliti > 0 && (
                        <span title="Esclusi da ogni denominatore">
                          {" "}
                          · {intero(r.probe_falliti)} falliti
                        </span>
                      )}
                    </span>
                  </th>
                  <td>
                    <CellaTasso tasso={r.citation_rate} />
                  </td>
                  <td>
                    <CellaTasso tasso={r.mention_rate} smorzata />
                  </td>
                  <td>
                    <CellaTasso tasso={r.target_hit_rate} smorzata />
                  </td>
                  <td className="border-l border-divisore !pl-3.5">
                    <CellaTasso tasso={r.memoria} smorzata />
                  </td>
                  <td className="cifre text-sm text-testo-70">
                    {millisecondi(r.latenza_mediana_ms)}
                  </td>
                  <td className="cifre text-sm text-testo-70">
                    {r.ricerche_medie === null ? "—" : r.ricerche_medie.toFixed(1)}
                  </td>
                  <td className="cifre text-sm text-testo-70">{euro(r.costo_eur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------- Categorie */

export function Categorie({ giorni }: { giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["categorie", giorni],
    queryFn: () => api.categorie(giorni),
  });

  const { categorie, provider, mappa } = useMemo(() => costruisciGriglia(data ?? []), [data]);

  return (
    <div className="rounded-md bg-superficie p-7">
      <h2 className="display text-md">Categorie</h2>
      <p className="mt-1 max-w-prose text-sm text-testo-55">
        Citation rate per categoria editoriale e provider.
      </p>
      {error ? (
        <div className="mt-4">
          <StatoErrore errore={error} riprova={() => void refetch()} />
        </div>
      ) : isPending ? (
        <div className="mt-4">
          <Scheletro righe={5} />
        </div>
      ) : !categorie.length ? (
        <div className="mt-4">
          <StatoVuoto
            titolo="Nessuna categoria ha ancora dati."
            cosaFare="Le categorie compaiono dopo il primo `sender.py sync-topics` e almeno un ciclo di probe."
          />
        </div>
      ) : (
        <>
          <div className="scorrevole -mx-4 mt-4 px-4">
            <table className="tabella min-w-[40rem]">
              <caption className="sr-only">
                Citation rate per categoria editoriale e provider
              </caption>
              <thead>
                <tr>
                  <th scope="col">Categoria</th>
                  {provider.map((p) => (
                    <th key={p} scope="col">
                      {p}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {categorie.map((c) => (
                  <tr key={c}>
                    <th scope="row" className="pr-3 text-left align-top text-sm font-normal">
                      {c || "senza categoria"}
                    </th>
                    {provider.map((p) => {
                      const cella = mappa.get(`${c}|${p}`);
                      return (
                        <td key={p}>
                          {cella ? (
                            <CellaTasso tasso={cella.citation_rate} />
                          ) : (
                            <>
                              <span className="text-testo-45">—</span>
                              <span className="mt-0.5 block text-xs text-testo-45">
                                mai sondata
                              </span>
                            </>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-xs text-testo-40">
            Valori sbiaditi = campione sotto i 30 probe. Trattino = sotto i 10, nessuna
            percentuale.
          </p>
        </>
      )}
    </div>
  );
}

function costruisciGriglia(celle: CellaCategoria[]) {
  const categorie = new Set<string>();
  const provider = new Set<string>();
  const mappa = new Map<string, CellaCategoria>();
  for (const c of celle) {
    categorie.add(c.category_slug);
    provider.add(c.provider);
    mappa.set(`${c.category_slug}|${c.provider}`, c);
  }
  return {
    categorie: [...categorie].sort(),
    provider: [...provider].sort(),
    mappa,
  };
}

/* ----------------------------------------------------------------- Domini */

export function Domini({ giorni }: { giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["domini", giorni],
    queryFn: () => api.domini(giorni),
  });

  const massimo = useMemo(
    () => Math.max(1, ...(data ?? []).map((d) => d.citazioni)),
    [data],
  );

  return (
    <div className="rounded-md bg-superficie p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="display text-md">Chi occupa il posto</h2>
        <span className="text-xs text-testo-45">quota citazioni</span>
      </div>
      {error ? (
        <div className="mt-4">
          <StatoErrore errore={error} riprova={() => void refetch()} />
        </div>
      ) : isPending ? (
        <div className="mt-4">
          <Scheletro righe={5} />
        </div>
      ) : !data?.length ? (
        <div className="mt-4">
          <StatoVuoto
            titolo="Nessuna citazione registrata nel periodo."
            cosaFare="Compaiono qui tutti i domini citati, non solo il proprio: senza gli altri non si sa chi prende il posto quando il giornale manca."
          />
        </div>
      ) : (
        <>
          <ol className="mt-4 flex flex-col gap-3">
            {data.map((d, i) => (
              <li
                key={d.domain}
                className={`grid grid-cols-[18px_minmax(0,1fr)_minmax(64px,120px)_52px] items-center gap-3 rounded-sm px-1.5 py-0.5 ${
                  d.proprio ? "bg-accento/8" : ""
                }`}
              >
                <span className="cifre text-right text-xs text-testo-40">{i + 1}</span>
                <span
                  className={`truncate text-sm ${d.non_risolto ? "text-testo-45" : "text-testo"}`}
                >
                  {d.non_risolto ? "dominio non risolto" : d.domain}
                  {d.proprio && (
                    <span className="ml-2 text-[10px] uppercase tracking-[0.08em] text-accento">
                      il tuo
                    </span>
                  )}
                </span>
                <span
                  aria-hidden
                  className="relative h-1 overflow-hidden rounded-full bg-neutro-900"
                >
                  <span
                    className={`absolute bottom-0 left-0 top-0 rounded-full ${
                      d.proprio ? "bg-accento" : "bg-neutro-600"
                    }`}
                    style={{ width: `${Math.round((d.citazioni / massimo) * 100)}%` }}
                  />
                </span>
                <span
                  className="cifre text-right text-xs text-testo-70"
                  title={`${d.quota.numeratore}/${d.quota.denominatore} probe`}
                >
                  {d.quota.tasso === null ? "—" : percentuale(d.quota.tasso)}
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-4 text-xs text-testo-40">
            Domini citati sulle stesse domande. Le quote non sommano a 100%: classifica
            troncata.
          </p>
        </>
      )}
    </div>
  );
}
