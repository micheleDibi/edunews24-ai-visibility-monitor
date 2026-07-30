/** Sezione 3 — Provider. Sezione 4 — Categorie. Più la classifica dei domini. */

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { BandaIncertezza, descriviTasso } from "../components/BandaIncertezza";
import { Card, Distintivo, Scheletro, StatoErrore, StatoVuoto } from "../components/base";
import { api, type CellaCategoria } from "../lib/api";
import { euro, intero, millisecondi, percentuale, serieDi } from "../lib/format";

/* ------------------------------------------------------------- Provider */

export function Provider({ giorni }: { giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["provider", giorni],
    queryFn: () => api.provider(giorni),
  });

  return (
    <Card
      id="provider"
      titolo="Provider"
      descrizione="Dove il giornale viene citato e dove no. La colonna «memoria» è separata perché misura una cosa diversa."
      spiega={[
        "citation_rate",
        "mention",
        "target_hit",
        "memoria",
        "falliti",
        "latenza",
        "ricerche",
        "banda",
      ]}
    >
      {error ? (
        <StatoErrore errore={error} riprova={() => void refetch()} />
      ) : isPending ? (
        <Scheletro righe={4} />
      ) : !data?.length ? (
        <StatoVuoto
          titolo="Nessun provider ha ancora prodotto probe riusciti."
          cosaFare="Aggiungi almeno una chiave API nel .env (OPENAI_API_KEY, PERPLEXITY_API_KEY, ANTHROPIC_API_KEY) e riavvia il container."
        />
      ) : (
        <div className="scorrevole -mx-4 px-4">
          <table className="w-full min-w-[52rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-grafite-tenue text-left align-bottom">
                <th scope="col" className="py-2 pr-3 font-medium">
                  Provider
                </th>
                <th scope="col" className="py-2 pr-3 font-medium">
                  Citato
                </th>
                <th scope="col" className="py-2 pr-3 font-medium">
                  Mention
                </th>
                <th scope="col" className="py-2 pr-3 font-medium">
                  Articolo giusto
                </th>
                {/* Filetto verticale + intestazione che dichiara la differenza:
                    e' l'unica colonna della tabella che non si confronta con le
                    altre. */}
                <th
                  scope="col"
                  className="border-l border-grafite-tenue py-2 pl-3 pr-3 font-medium"
                >
                  Memoria
                  <span className="block text-xs font-normal text-grafite">
                    metrica diversa: cosa ricorda,
                    <br />
                    non cosa trova
                  </span>
                </th>
                <th scope="col" className="py-2 pr-3 font-medium">
                  Latenza
                </th>
                <th scope="col" className="py-2 pr-3 font-medium">
                  Ricerche
                </th>
                <th scope="col" className="py-2 font-medium">
                  Costo
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.provider} className="border-b border-grafite-tenue align-top">
                  <th scope="row" className="py-3 pr-3 text-left font-medium">
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden
                        className="inline-block h-0.5 w-4 shrink-0"
                        style={{ background: serieDi(r.provider).colore }}
                      />
                      {r.provider}
                    </span>
                    {r.model && (
                      <span className="mt-0.5 block font-mono text-xs font-normal text-grafite">
                        {r.model}
                      </span>
                    )}
                    {r.probe_falliti > 0 && (
                      <span className="mt-1 block">
                        <Distintivo tinta="sigillo" titolo="Esclusi da ogni denominatore">
                          {intero(r.probe_falliti)} falliti
                        </Distintivo>
                      </span>
                    )}
                  </th>
                  <td className="py-3 pr-3">
                    <BandaIncertezza
                      tasso={r.citation_rate}
                      tinta="timbro"
                      etichetta={`citation rate ${r.provider}`}
                    />
                  </td>
                  <td className="py-3 pr-3">
                    <BandaIncertezza
                      tasso={r.mention_rate}
                      tinta="grafite"
                      etichetta={`mention rate ${r.provider}`}
                    />
                  </td>
                  <td className="py-3 pr-3">
                    <BandaIncertezza
                      tasso={r.target_hit_rate}
                      tinta="alloro"
                      etichetta={`target hit ${r.provider}`}
                    />
                  </td>
                  <td className="border-l border-grafite-tenue py-3 pl-3 pr-3">
                    <BandaIncertezza
                      tasso={r.memoria}
                      tinta="grafite"
                      etichetta={`memoria ${r.provider}`}
                    />
                  </td>
                  <td className="cifre py-3 pr-3">{millisecondi(r.latenza_mediana_ms)}</td>
                  <td className="cifre py-3 pr-3">
                    {r.ricerche_medie === null ? "—" : r.ricerche_medie.toFixed(1)}
                  </td>
                  <td className="cifre py-3">{euro(r.costo_eur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------ Categorie */

export function Categorie({ giorni }: { giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["categorie", giorni],
    queryFn: () => api.categorie(giorni),
  });

  const { categorie, provider, mappa } = useMemo(() => costruisciGriglia(data ?? []), [data]);

  return (
    <Card
      id="categorie"
      titolo="Categorie"
      descrizione="Dove si legge il pattern. Ogni cella porta il numero e la sua incertezza: un gradiente di colore comunicherebbe una certezza che con questi denominatori non c'è."
      spiega={["citation_rate", "soglia", "banda", "strategia"]}
    >
      {error ? (
        <StatoErrore errore={error} riprova={() => void refetch()} />
      ) : isPending ? (
        <Scheletro righe={5} />
      ) : !categorie.length ? (
        <StatoVuoto
          titolo="Nessuna categoria ha ancora dati."
          cosaFare="Le categorie compaiono dopo il primo `sender.py sync-topics` e almeno un ciclo di probe."
        />
      ) : (
        <div className="scorrevole -mx-4 px-4">
          <table className="w-full min-w-[36rem] border-collapse text-sm">
            <caption className="sr-only">
              Citation rate per categoria editoriale e provider
            </caption>
            <thead>
              <tr className="border-b border-grafite-tenue text-left">
                <th scope="col" className="py-2 pr-3 font-medium">
                  Categoria
                </th>
                {provider.map((p) => (
                  <th key={p} scope="col" className="py-2 pr-3 font-medium">
                    {p}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {categorie.map((c) => (
                <tr key={c} className="border-b border-grafite-tenue align-top">
                  <th scope="row" className="py-3 pr-3 text-left font-medium">
                    {c || "senza categoria"}
                  </th>
                  {provider.map((p) => {
                    const cella = mappa.get(`${c}|${p}`);
                    return (
                      <td key={p} className="py-3 pr-3">
                        {cella ? (
                          <BandaIncertezza
                            tasso={cella.citation_rate}
                            tinta="timbro"
                            etichetta={`${c} su ${p}`}
                          />
                        ) : (
                          <span className="text-grafite" title="Mai sondata in questo periodo">
                            —
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
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

/* --------------------------------------------------------------- Domini */

export function Domini({ giorni }: { giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["domini", giorni],
    queryFn: () => api.domini(giorni),
  });

  return (
    <Card
      id="domini"
      titolo="Chi occupa il posto"
      descrizione="I domini citati dai motori sulle stesse domande. È il dato che dice contro chi si compete."
      spiega={["quota_dominio", "non_risolto"]}
    >
      {error ? (
        <StatoErrore errore={error} riprova={() => void refetch()} />
      ) : isPending ? (
        <Scheletro righe={5} />
      ) : !data?.length ? (
        <StatoVuoto
          titolo="Nessuna citazione registrata nel periodo."
          cosaFare="Compaiono qui tutti i domini citati, non solo il proprio: senza gli altri non si sa chi prende il posto quando il giornale manca."
        />
      ) : (
        <ol className="space-y-2">
          {data.map((d, i) => (
            <li
              key={d.domain}
              className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[var(--radius-controllo)] px-2 py-2 ${
                d.proprio ? "bg-timbro-tenue" : "odd:bg-gesso"
              }`}
            >
              <span className="cifre w-6 shrink-0 text-right text-sm text-grafite">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1 truncate font-mono text-sm">
                {d.non_risolto ? (
                  <span className="text-grafite">dominio non risolto</span>
                ) : (
                  d.domain
                )}
              </span>
              {d.proprio && <Distintivo tinta="timbro">il tuo</Distintivo>}
              {d.non_risolto && (
                <Distintivo
                  tinta="ottone"
                  titolo="URL avvolti in un redirect: il dominio reale non è estraibile senza seguirlo. Si dichiara invece di indovinarlo."
                >
                  quota di misura mancante
                </Distintivo>
              )}
              <span className="cifre w-40 shrink-0 text-sm" title={descriviTasso(d.quota, "quota")}>
                {d.quota.tasso === null ? "—" : percentuale(d.quota.tasso)}
                <span className="ml-1.5 text-xs text-grafite">
                  {d.quota.numeratore}/{d.quota.denominatore}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
