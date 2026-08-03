/**
 * Vista «Dove sei invisibile» — la coda di lavoro — piu' «Cosa funziona»
 * (che vive nella Panoramica).
 *
 * La coda e' divisa per costo di rimedio: sopra i pezzi che il motore apre
 * gia' e scarta (si riscrive), sotto quelli mai raggiunti (si scrive). Il
 * drill-down mostra chi e' citato al posto nostro, aggregato dal server su
 * tutti i probe del periodo.
 */

import { useQuery } from "@tanstack/react-query";
import { CaretDown, CaretRight } from "@phosphor-icons/react";
import { useMemo, useState } from "react";

import { Distintivo, Scheletro, StatoErrore, StatoVuoto } from "../components/base";
import { api, type Lacuna } from "../lib/api";
import { ETICHETTA_STRATEGIA, dataOra, intero, percentuale } from "../lib/format";

/* ---------------------------------------------------- Dove sei invisibile */

export function DoveInvisibile({ giorni }: { giorni: number }) {
  const [minProbe, setMinProbe] = useState(10);
  const [aperto, setAperto] = useState<number | null>(null);

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["lacune", giorni, minProbe],
    queryFn: () => api.lacune(giorni, minProbe),
  });

  const gruppi = useMemo(() => {
    const riscrivibili = (data ?? []).filter((l) => l.recuperi > 0);
    const mancanti = (data ?? []).filter((l) => l.recuperi === 0);
    return { riscrivibili, mancanti };
  }, [data]);

  return (
    <section aria-labelledby="invisibile-titolo">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.1em] text-accento">
            Coda di lavoro · ultimi {giorni} giorni
          </p>
          <h1 id="invisibile-titolo" className="display mt-1.5 text-xl">
            Dove sei invisibile
          </h1>
          <p className="mt-1.5 max-w-[60ch] text-sm text-testo-55">
            Articoli sondati e mai citati, ordinati per costo di rimedio. Apri una riga per
            vedere chi è citato al posto tuo.
          </p>
        </div>
        <div
          role="group"
          aria-label="Soglia minima di probe"
          className="inline-flex overflow-hidden rounded-md border border-divisore"
        >
          {[3, 10, 20].map((soglia) => (
            <button
              key={soglia}
              type="button"
              onClick={() => setMinProbe(soglia)}
              aria-pressed={minProbe === soglia}
              className={`cifre min-h-11 cursor-pointer whitespace-nowrap border-0 bg-transparent px-3 text-sm transition-colors sm:min-h-8 ${
                minProbe === soglia
                  ? "text-accento shadow-[inset_0_0_0_1px_var(--color-accento)]"
                  : "text-testo-60 hover:bg-testo/7"
              }`}
            >
              ≥ {soglia} probe
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <div className="mt-7">
          <StatoErrore errore={error} riprova={() => void refetch()} />
        </div>
      ) : isPending ? (
        <div className="mt-7">
          <Scheletro righe={6} />
        </div>
      ) : !data?.length ? (
        <div className="mt-7">
          <StatoVuoto
            titolo={`Nessun articolo è stato sondato almeno ${minProbe} volte senza mai essere citato.`}
            cosaFare="Con poche settimane di dati è il caso normale. La soglia esiste perché un articolo sondato due volte e mai citato è rumore, non un dato: abbassala per guardare comunque."
          />
        </div>
      ) : (
        <>
          {gruppi.riscrivibili.length > 0 && (
            <GruppoLacune
              titolo="Basta riscrivere il pezzo"
              tinta="accento"
              descrizione="Il motore apre già queste pagine e cita qualcun altro: manca la risposta esplicita dove viene cercata, non l'indicizzazione. Il lavoro più corto, il primo da fare."
              righe={gruppi.riscrivibili}
              giorni={giorni}
              aperto={aperto}
              onToggle={(id) => setAperto(aperto === id ? null : id)}
            />
          )}
          {gruppi.mancanti.length > 0 && (
            <GruppoLacune
              titolo="Manca il pezzo"
              tinta="neutro"
              descrizione="Il motore non ha mai aperto il sito su queste domande: serve un pezzo nuovo, o autorevolezza sull'argomento."
              righe={gruppi.mancanti}
              giorni={giorni}
              aperto={aperto}
              onToggle={(id) => setAperto(aperto === id ? null : id)}
            />
          )}
        </>
      )}
    </section>
  );
}

function GruppoLacune({
  titolo,
  tinta,
  descrizione,
  righe,
  giorni,
  aperto,
  onToggle,
}: {
  titolo: string;
  tinta: "accento" | "neutro";
  descrizione: string;
  righe: Lacuna[];
  giorni: number;
  aperto: number | null;
  onToggle: (id: number) => void;
}) {
  return (
    <div className="mt-7 rounded-md bg-superficie p-7">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="display whitespace-nowrap text-md">{titolo}</h2>
        <Distintivo tinta={tinta}>
          <span className="cifre">{intero(righe.length)}</span>
        </Distintivo>
      </div>
      <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-testo-55">{descrizione}</p>
      <ul className="mt-3">
        {righe.map((l) => {
          const espanso = aperto === l.topic_id;
          const recuperabile = l.recuperi > 0;
          const Caret = espanso ? CaretDown : CaretRight;
          return (
            <li key={l.topic_id}>
              <button
                type="button"
                onClick={() => onToggle(l.topic_id)}
                aria-expanded={espanso}
                className="flex min-h-11 w-full cursor-pointer items-center gap-3.5 rounded-sm px-2 py-4 text-left transition-colors hover:bg-testo/4"
              >
                <Caret size={14} className="shrink-0 text-testo-45" aria-hidden />
                <span className="min-w-0 flex-1 text-base leading-snug">{l.title}</span>
                {l.category_slug && (
                  <span className="hidden shrink-0 sm:inline-flex">
                    <Distintivo tinta="neutro">{l.category_slug}</Distintivo>
                  </span>
                )}
                <span
                  className={`cifre w-44 shrink-0 text-right text-xs ${
                    recuperabile ? "text-accento-300" : "text-testo-45"
                  }`}
                >
                  {recuperabile
                    ? `aperto ${intero(l.recuperi)} volte su ${intero(l.probe)} · mai citato`
                    : `mai raggiunto · ${intero(l.probe)} probe`}
                </span>
              </button>
              {espanso && <DettaglioLacuna topicId={l.topic_id} giorni={giorni} />}
              <div className="righello" />
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Drill-down: gli occupanti aggregati dal server e un campione di risposte. */
function DettaglioLacuna({ topicId, giorni }: { topicId: number; giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["lacuna", topicId, giorni],
    queryFn: () => api.lacuna(topicId, giorni),
  });

  if (error) {
    return (
      <div className="pb-5 pl-9">
        <StatoErrore errore={error} riprova={() => void refetch()} />
      </div>
    );
  }
  if (isPending) {
    return (
      <div className="pb-5 pl-9">
        <Scheletro righe={2} />
      </div>
    );
  }

  const { occupanti, probe } = data;

  return (
    <div className="flex flex-col gap-4 px-2 pb-5 pl-9 pt-1">
      {occupanti.length > 0 && (
        <div>
          <p className="text-[11px] uppercase tracking-[0.1em] text-testo-55">
            Citati al posto tuo
          </p>
          <ul className="mt-2.5 flex flex-wrap gap-1.5">
            {occupanti.map((o) => (
              <li key={o.domain}>
                <Distintivo tinta="neutro">
                  <span className="cifre">
                    {o.domain} ×{intero(o.citazioni)}
                  </span>
                </Distintivo>
              </li>
            ))}
          </ul>
        </div>
      )}

      {probe.length > 0 ? (
        <div>
          <p className="text-[11px] uppercase tracking-[0.1em] text-testo-55">
            Domande e risposte
          </p>
          <ul className="mt-2.5 grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-3">
            {probe.map((p) => (
              <li key={p.id} className="rounded-md bg-neutro-900 px-4 py-3.5">
                <p className="text-sm font-medium leading-snug">{p.query_text}</p>
                <p className="mt-1 text-[11px] text-testo-45">
                  {p.provider} · {ETICHETTA_STRATEGIA[p.query_strategy] ?? p.query_strategy} ·{" "}
                  {dataOra(p.created_at)}
                </p>
                {p.answer_text ? (
                  <p className="mt-2.5 line-clamp-3 text-xs leading-relaxed text-testo-60">
                    {p.answer_text}
                  </p>
                ) : (
                  <p className="mt-2.5 text-xs text-testo-45">
                    Testo della risposta rimosso dalla retention.
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-testo-55">
          Nessun probe conservato per questo articolo: la retention azzera le risposte dopo
          il periodo configurato.
        </p>
      )}
    </div>
  );
}

/* --------------------------------------------------------- Cosa funziona */

export function CosaFunziona({ giorni }: { giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["successi", giorni],
    queryFn: () => api.successi(giorni),
  });

  return (
    <div className="rounded-md bg-superficie p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="display text-md">Cosa funziona</h2>
        <span className="text-xs text-testo-45">articoli citati</span>
      </div>
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
            titolo="Ancora nessuna citazione registrata."
            cosaFare="Per un giornale locale che compete con le testate grandi è il punto di partenza normale. La sezione «Dove sei invisibile» dice su cosa lavorare per cambiarlo."
          />
        </div>
      ) : (
        <ul className="mt-2">
          {data.map((s) => (
            <li key={s.topic_id} className="py-3.5">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <a
                    href={`https://edunews24.it/${s.category_slug ?? ""}/${s.slug}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm leading-snug text-testo underline decoration-transparent underline-offset-2 transition-colors hover:text-accento hover:decoration-accento/40"
                  >
                    {s.title}
                  </a>
                  <p className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
                    {s.category_slug && <Distintivo tinta="neutro">{s.category_slug}</Distintivo>}
                    {s.target_hit > 0 && (
                      <Distintivo tinta="accento">
                        <span className="cifre">{intero(s.target_hit)}× articolo giusto</span>
                      </Distintivo>
                    )}
                    <span className="cifre text-testo-45">{s.provider.join(", ")}</span>
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="display cifre text-[19px]">
                    {s.citation_rate.tasso === null ? "—" : percentuale(s.citation_rate.tasso)}
                  </p>
                  <p className="cifre text-[11px] text-testo-45">
                    {intero(s.citazioni)}/{intero(s.probe)}
                  </p>
                </div>
              </div>
              <div className="righello mt-3.5" />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
