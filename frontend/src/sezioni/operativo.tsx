/**
 * Sezione 5 — Dove sei invisibile. Sezione 6 — Cosa funziona.
 *
 * La 5 è la sezione operativa: quella che si apre per decidere cosa scrivere.
 * Progettata per essere la più usabile, non la più decorata — lista invece di
 * griglia, drill-down su chi è stato citato al posto tuo.
 */

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import { useState } from "react";

import { BandaIncertezza } from "../components/BandaIncertezza";
import { Card, Distintivo, Scheletro, StatoErrore, StatoVuoto } from "../components/base";
import { api, type Citazione } from "../lib/api";
import { ETICHETTA_STRATEGIA, dataOra, intero } from "../lib/format";

/* ---------------------------------------------------- Dove sei invisibile */

export function DoveInvisibile({ giorni }: { giorni: number }) {
  const [minProbe, setMinProbe] = useState(10);
  const [aperto, setAperto] = useState<number | null>(null);

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["lacune", giorni, minProbe],
    queryFn: () => api.lacune(giorni, minProbe),
  });

  return (
    <Card
      id="lacune"
      titolo="Dove sei invisibile"
      descrizione="Articoli sondati più volte e mai citati, dal più sondato. Apri una riga per vedere le risposte ricevute e chi è stato citato al posto tuo."
      azioni={
        <label className="flex items-center gap-2 text-sm">
          <span className="text-grafite">Almeno</span>
          <select
            value={minProbe}
            onChange={(e) => setMinProbe(Number(e.target.value))}
            className="min-h-11 cursor-pointer rounded-[var(--radius-controllo)] border border-grafite-tenue bg-foglio px-2 text-sm sm:min-h-9"
          >
            <option value={3}>3 probe</option>
            <option value={10}>10 probe</option>
            <option value={20}>20 probe</option>
          </select>
        </label>
      }
    >
      {error ? (
        <StatoErrore errore={error} riprova={() => void refetch()} />
      ) : isPending ? (
        <Scheletro righe={6} />
      ) : !data?.length ? (
        <StatoVuoto
          titolo={`Nessun articolo è stato sondato almeno ${minProbe} volte senza mai essere citato.`}
          cosaFare="Con poche settimane di dati è il caso normale. La soglia esiste perché un articolo sondato due volte e mai citato è rumore, non un dato: abbassala per guardare comunque."
        />
      ) : (
        <ul className="divide-y divide-grafite-tenue">
          {data.map((l) => {
            const espanso = aperto === l.topic_id;
            return (
              <li key={l.topic_id}>
                <button
                  type="button"
                  onClick={() => setAperto(espanso ? null : l.topic_id)}
                  aria-expanded={espanso}
                  // 44px di altezza minima: e' una riga cliccabile su mobile.
                  className="flex min-h-11 w-full cursor-pointer items-start gap-3 py-3 text-left transition-colors hover:bg-gesso"
                >
                  {espanso ? (
                    <ChevronDown size={18} className="mt-0.5 shrink-0 text-grafite" aria-hidden />
                  ) : (
                    <ChevronRight size={18} className="mt-0.5 shrink-0 text-grafite" aria-hidden />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{l.title}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-grafite">
                      {l.category_slug && <Distintivo>{l.category_slug}</Distintivo>}
                      <span className="cifre">{intero(l.probe)} probe, zero citazioni</span>
                      {l.recuperato_mai && (
                        <Distintivo
                          tinta="ottone"
                          titolo="Il giornale è comparso fra le fonti mostrate al modello, che però non l'ha citato: è un problema di qualità percepita del pezzo, non di indicizzazione."
                        >
                          recuperato ma non citato
                        </Distintivo>
                      )}
                    </span>
                  </span>
                </button>
                {espanso && <DettaglioLacuna topicId={l.topic_id} giorni={giorni} />}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

/** Drill-down: le risposte ricevute e i domini citati al posto nostro. */
function DettaglioLacuna({ topicId, giorni }: { topicId: number; giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["lacuna-probe", topicId, giorni],
    queryFn: () => api.probe({ days: giorni, topic_id: topicId, limit: 6, mode: "retrieval" }),
  });

  if (error) return <div className="pb-3"><StatoErrore errore={error} riprova={() => void refetch()} /></div>;
  if (isPending) return <div className="pb-3 pl-8"><Scheletro righe={2} /></div>;

  const elementi = data?.elementi ?? [];
  if (!elementi.length) {
    return (
      <p className="pb-3 pl-8 text-sm text-grafite">
        Nessun probe conservato per questo articolo: la retention azzera le risposte dopo il
        periodo configurato.
      </p>
    );
  }

  const occupanti = contaOccupanti(elementi.flatMap((e) => e.citazioni));

  return (
    <div className="space-y-3 pb-4 pl-8">
      {occupanti.length > 0 && (
        <div>
          <h4 className="text-sm font-medium">Citati al posto tuo</h4>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {occupanti.map(([dominio, quante]) => (
              <li key={dominio}>
                <Distintivo tinta="grafite">
                  <span className="font-mono">{dominio}</span>
                  <span className="cifre">×{quante}</span>
                </Distintivo>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h4 className="text-sm font-medium">Domande fatte e risposte ricevute</h4>
        <ul className="mt-1 space-y-2">
          {elementi.map((p) => (
            <li
              key={p.id}
              className="rounded-[var(--radius-controllo)] bg-gesso p-3 text-sm"
            >
              <p className="font-medium">{p.query_text}</p>
              <p className="mt-0.5 text-xs text-grafite">
                {p.provider} · {ETICHETTA_STRATEGIA[p.query_strategy] ?? p.query_strategy} ·{" "}
                {dataOra(p.created_at)}
              </p>
              {p.answer_text ? (
                <p className="mt-2 line-clamp-4 whitespace-pre-wrap text-grafite">
                  {p.answer_text}
                </p>
              ) : (
                <p className="mt-2 text-xs text-grafite">
                  Testo della risposta rimosso dalla retention.
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function contaOccupanti(citazioni: Citazione[]): Array<[string, number]> {
  const conteggio = new Map<string, number>();
  for (const c of citazioni) {
    if (c.is_own || c.kind !== "citation") continue;
    conteggio.set(c.domain, (conteggio.get(c.domain) ?? 0) + 1);
  }
  return [...conteggio.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
}

/* --------------------------------------------------------- Cosa funziona */

export function CosaFunziona({ giorni }: { giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["successi", giorni],
    queryFn: () => api.successi(giorni),
  });

  return (
    <Card
      id="successi"
      titolo="Cosa funziona"
      descrizione="Articoli citati, dal più citato. «Articolo giusto» significa che è stato citato proprio il pezzo che ha generato la domanda."
    >
      {error ? (
        <StatoErrore errore={error} riprova={() => void refetch()} />
      ) : isPending ? (
        <Scheletro righe={4} />
      ) : !data?.length ? (
        <StatoVuoto
          titolo="Ancora nessuna citazione registrata."
          cosaFare="Per un giornale locale che compete con le testate grandi è il punto di partenza normale. La sezione «dove sei invisibile» dice su cosa lavorare per cambiarlo."
        />
      ) : (
        <ul className="divide-y divide-grafite-tenue">
          {data.map((s) => (
            <li key={s.topic_id} className="flex flex-wrap items-start gap-x-4 gap-y-2 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{s.title}</p>
                <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-grafite">
                  {s.category_slug && <Distintivo>{s.category_slug}</Distintivo>}
                  <span className="cifre">
                    {intero(s.citazioni)} citazioni su {intero(s.probe)} probe
                  </span>
                  {s.target_hit > 0 && (
                    <Distintivo tinta="alloro">
                      {intero(s.target_hit)}× articolo giusto
                    </Distintivo>
                  )}
                  {s.provider.map((p) => (
                    <Distintivo key={p} tinta="timbro">
                      {p}
                    </Distintivo>
                  ))}
                </p>
              </div>
              <div className="w-40 shrink-0">
                <BandaIncertezza
                  tasso={s.citation_rate}
                  tinta="alloro"
                  etichetta={`citation rate ${s.slug}`}
                />
              </div>
              <a
                href={`https://edunews24.it/${s.category_slug ?? ""}/${s.slug}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-11 items-center gap-1 text-sm text-timbro underline decoration-timbro/40 underline-offset-2 hover:decoration-timbro sm:min-h-0"
              >
                apri
                <ExternalLink size={14} aria-hidden />
                <span className="sr-only">l'articolo {s.title} su edunews24.it</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
