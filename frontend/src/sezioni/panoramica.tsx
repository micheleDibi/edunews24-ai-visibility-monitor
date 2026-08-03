/** Vista «Panoramica»: il KPI hero, le tessere secondarie e la tendenza. */

import { useQuery } from "@tanstack/react-query";
import { Minus, TrendDown, TrendUp } from "@phosphor-icons/react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useMemo, useState } from "react";

import { Scheletro, StatoErrore, StatoVuoto } from "../components/base";
import { api, type Delta, type PuntoTendenza, type Tasso } from "../lib/api";
import { dataBreve, euro, intero, percentuale, serieDi } from "../lib/format";

/* ------------------------------------------------------------------ KPI */

/** «+2,1 pt»: la differenza fra due tassi si dice in punti, non in percento. */
function punti(differenza: number): string {
  const valore = Math.abs(differenza * 100).toLocaleString("it-IT", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  return `${differenza >= 0 ? "+" : "−"}${valore} pt`;
}

/**
 * Il delta compare SOLO se significativo. Se gli intervalli di confidenza dei
 * due periodi si sovrappongono, la differenza e' rumore: mostrarla con una
 * freccia sarebbe la bugia piu' facile di tutta l'interfaccia.
 */
function Variazione({ delta }: { delta: Delta }) {
  if (delta.differenza === null) {
    return (
      <p className="mt-4 text-sm text-testo-45">
        Nessun confronto: il periodo precedente non ha abbastanza probe.
      </p>
    );
  }
  if (!delta.significativo) {
    return (
      <p className="mt-4 flex items-center gap-2 text-sm text-testo-45">
        <Minus size={16} aria-hidden />
        variazione non significativa
        <span className="cifre whitespace-nowrap">
          (era {percentuale(delta.precedente.tasso ?? 0)})
        </span>
      </p>
    );
  }
  const su = delta.differenza > 0;
  const Icona = su ? TrendUp : TrendDown;
  return (
    <p className="mt-4 flex items-center gap-2 text-sm text-accento-300">
      <Icona size={16} aria-hidden />
      <span className="cifre whitespace-nowrap font-medium">{punti(delta.differenza)}</span>
      <span className="whitespace-nowrap text-testo-45">
        vs periodo precedente ({percentuale(delta.precedente.tasso ?? 0)})
      </span>
    </p>
  );
}

function Tessera({
  etichetta,
  valore,
  conto,
  nota,
}: {
  etichetta: string;
  valore: string;
  conto?: string;
  nota: string;
}) {
  return (
    <div className="rounded-md bg-superficie p-5">
      <p className="text-[11px] uppercase tracking-[0.1em] text-testo-55">{etichetta}</p>
      <p className="mt-2.5 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="display cifre text-[26px] leading-none">{valore}</span>
        {conto && <span className="cifre text-xs text-testo-45">{conto}</span>}
      </p>
      <p className="mt-2.5 text-xs leading-normal text-testo-55">{nota}</p>
    </div>
  );
}

function contoTasso(t: Tasso): string {
  return t.denominatore === 0
    ? "nessun dato"
    : `${intero(t.numeratore)}/${intero(t.denominatore)}`;
}

export function HeaderKpi({ giorni }: { giorni: number }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["kpi", giorni],
    queryFn: () => api.kpi(giorni),
  });

  const intestazione = (
    <div>
      <p className="text-[11px] uppercase tracking-[0.1em] text-accento">
        Ultimi {giorni} giorni
      </p>
      <h1 className="display mt-1.5 text-xl">Panoramica</h1>
      <p className="mt-1.5 max-w-[60ch] text-sm text-testo-55">
        Dove i motori di risposta citano edunews24.it, e dove no.
      </p>
    </div>
  );

  if (error) {
    return (
      <div>
        {intestazione}
        <div className="mt-7">
          <StatoErrore errore={error} riprova={() => void refetch()} />
        </div>
      </div>
    );
  }
  if (isPending) {
    return (
      <div>
        {intestazione}
        <div className="mt-7 rounded-md bg-superficie p-7">
          <Scheletro righe={4} />
        </div>
      </div>
    );
  }

  const k = data;
  if (k.probe_totali === 0) {
    return (
      <div>
        {intestazione}
        <div className="mt-7">
          <StatoVuoto
            titolo={`Nessun probe riuscito negli ultimi ${giorni} giorni.`}
            cosaFare="Il ciclo orario gira al minuto 7 di ogni ora. Per un ciclo immediato usa «Esegui un ciclo» nello stato del sistema, oppure `python sender.py run-once` dal container."
          />
        </div>
      </div>
    );
  }

  const cr = k.citation_rate;
  return (
    <div>
      {intestazione}
      <div className="mt-9 grid grid-cols-[repeat(auto-fit,minmax(340px,1fr))] items-stretch gap-6">
        {/* Il numero che conta, con il peso visivo maggiore. */}
        <div className="rounded-md bg-superficie p-7">
          <p className="text-[11px] uppercase tracking-[0.1em] text-testo-55">Citation rate</p>
          <p className="mt-3.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="display cifre text-[clamp(3rem,8vw,4.5rem)] leading-none tracking-[-0.03em]">
              {cr.tasso === null ? "—" : percentuale(cr.tasso)}
            </span>
            <span className="cifre text-sm text-testo-55">{contoTasso(cr)}</span>
          </p>
          {/* La sottolineatura: l'accento come marchio corto, col suo bagliore. */}
          <div
            aria-hidden
            className="mt-4 h-[3px] w-14 rounded-[2px] bg-accento shadow-bagliore-riga"
          />
          <Variazione delta={k.citation_rate_delta} />
          <p className="cifre mt-2.5 text-xs text-testo-45">
            {cr.ic_basso !== null && cr.ic_alto !== null
              ? `IC 95%: ${percentuale(cr.ic_basso)} – ${percentuale(cr.ic_alto)} · `
              : ""}
            risposte con ricerca web in cui il sito è fra le fonti citate
          </p>
        </div>

        <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-6">
          <Tessera
            etichetta="Mention senza link"
            valore={k.mention_rate.tasso === null ? "—" : percentuale(k.mention_rate.tasso)}
            conto={contoTasso(k.mention_rate)}
            nota="Nominato ma non citato come fonte: notorietà, non retrieval."
          />
          <Tessera
            etichetta="Articolo giusto"
            valore={
              k.target_hit_rate.tasso === null ? "—" : percentuale(k.target_hit_rate.tasso)
            }
            conto={contoTasso(k.target_hit_rate)}
            nota="Citato proprio il pezzo che ha generato la domanda."
          />
          <Tessera
            etichetta="Recuperato"
            valore={
              k.retrieval_rate.tasso === null ? "—" : percentuale(k.retrieval_rate.tasso)
            }
            conto={contoTasso(k.retrieval_rate)}
            nota="Aperto dal motore, citato o no. Se non citato, è forma del pezzo."
          />
          <Tessera
            etichetta="Costo del periodo"
            valore={euro(k.costo_eur)}
            nota={`${intero(k.probe_totali)} probe riusciti · ${intero(k.probe_falliti)} falliti · ${intero(k.probe_senza_ricerca)} senza ricerca (esclusi).`}
          />
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- Tendenza */

interface RigaGrafico {
  giorno: string;
  [chiave: string]: number | string | null;
}

export function Tendenza({ giorni }: { giorni: number }) {
  const [soloProvider, setSoloProvider] = useState<string>("");
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["tendenza", giorni, soloProvider],
    queryFn: () => api.tendenza(giorni, soloProvider || undefined),
  });

  // L'elenco dei provider per il filtro NON dipende dal filtro stesso,
  // altrimenti selezionandone uno sparirebbero gli altri bottoni.
  const tutti = useQuery({
    queryKey: ["tendenza", giorni, ""],
    queryFn: () => api.tendenza(giorni, undefined),
  });
  const nomiProvider = useMemo(
    () => [...new Set((tutti.data ?? []).map((p) => p.provider))].sort(),
    [tutti.data],
  );

  const { righe, provider } = useMemo(() => aggrega(data ?? []), [data]);

  return (
    <div className="rounded-md bg-superficie p-7" id="tendenza">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="display text-md">Tendenza</h2>
          <p className="mt-1 text-sm text-testo-55">
            Citation rate per giorno e per provider. Le serie si distinguono per tratteggio
            oltre che per colore.
          </p>
        </div>
        {nomiProvider.length > 0 && (
          <div
            role="group"
            aria-label="Filtra per provider"
            className="inline-flex overflow-hidden rounded-md border border-divisore"
          >
            {[["", "tutti"], ...nomiProvider.map((p) => [p, p])].map(([valore, testo]) => (
              <button
                key={valore}
                type="button"
                onClick={() => setSoloProvider(valore!)}
                aria-pressed={soloProvider === valore}
                className={`min-h-11 cursor-pointer whitespace-nowrap border-0 bg-transparent px-3 text-sm transition-colors sm:min-h-8 ${
                  soloProvider === valore
                    ? "text-accento shadow-[inset_0_0_0_1px_var(--color-accento)]"
                    : "text-testo-60 hover:bg-testo/7"
                }`}
              >
                {testo}
              </button>
            ))}
          </div>
        )}
      </div>

      {error ? (
        <div className="mt-5">
          <StatoErrore errore={error} riprova={() => void refetch()} />
        </div>
      ) : isPending ? (
        <div className="mt-5">
          <Scheletro righe={6} />
        </div>
      ) : righe.length < 2 ? (
        <div className="mt-5">
          <StatoVuoto
            titolo="Servono almeno due giorni di dati per disegnare una tendenza."
            cosaFare="Il grafico si popola da sé man mano che i cicli orari girano. Il giorno corrente è calcolato in tempo reale, i precedenti dagli aggregati notturni."
          />
        </div>
      ) : (
        <>
          <div className="mt-6 h-72 w-full">
            <ResponsiveContainer>
              <ComposedChart data={righe} margin={{ top: 8, right: 8, bottom: 0, left: -14 }}>
                <CartesianGrid stroke="var(--color-divisore)" vertical={false} />
                <XAxis
                  dataKey="giorno"
                  tickFormatter={dataBreve}
                  tick={{ fontSize: 11, fill: "var(--color-testo-45)" }}
                  stroke="transparent"
                  minTickGap={24}
                />
                <YAxis
                  domain={[0, 1]}
                  tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                  tick={{ fontSize: 11, fill: "var(--color-testo-45)" }}
                  stroke="transparent"
                  width={44}
                />
                <Tooltip content={<Suggerimento />} />
                <Legend
                  verticalAlign="bottom"
                  height={30}
                  wrapperStyle={{ fontSize: 13 }}
                  formatter={(v) => <span className="text-testo-70">{String(v)}</span>}
                />
                {/* La banda d'incertezza attorno alla linea, quando si guarda
                    un solo provider: con piu' serie diventerebbe illeggibile. */}
                {provider.length === 1 && provider[0] && (
                  <Area
                    dataKey={`${provider[0]}__ic`}
                    stroke="none"
                    fill={serieDi(provider[0]).colore}
                    fillOpacity={0.12}
                    isAnimationActive={false}
                    legendType="none"
                    name="intervallo di confidenza"
                  />
                )}
                {provider.map((p) => (
                  <Line
                    key={p}
                    type="monotone"
                    dataKey={p}
                    name={p}
                    stroke={serieDi(p).colore}
                    strokeWidth={2}
                    strokeDasharray={serieDi(p).tratto}
                    // I giorni sotto la soglia sono `null` e la linea si
                    // INTERROMPE: con `connectNulls` il grafico disegnerebbe un
                    // segmento dritto sopra un giorno mai misurato, che è
                    // esattamente il numero inventato che tutto il resto
                    // dell'interfaccia si rifiuta di mostrare. Il pallino serve
                    // perché un giorno isolato fra due buchi resterebbe
                    // altrimenti invisibile.
                    dot={{ r: 2, strokeWidth: 0, fill: serieDi(p).colore }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-3 text-xs text-testo-40">
            {provider.length === 1
              ? "banda = intervallo di confidenza 95%"
              : "L'intervallo di confidenza si disegna selezionando un solo provider: con più serie sovrapposte diventerebbe illeggibile."}
          </p>
        </>
      )}
    </div>
  );
}

function aggrega(punti: PuntoTendenza[]) {
  const perGiorno = new Map<string, RigaGrafico>();
  const provider = new Set<string>();

  for (const p of punti) {
    provider.add(p.provider);
    const riga = perGiorno.get(p.giorno) ?? { giorno: p.giorno };
    // I giorni sotto la soglia restano `null`: la linea si interrompe invece di
    // disegnare uno zero che non e' uno zero misurato.
    riga[p.provider] = p.citation_rate.tasso;
    riga[`${p.provider}__ic`] =
      p.citation_rate.ic_basso === null
        ? null
        : ([p.citation_rate.ic_basso, p.citation_rate.ic_alto] as unknown as number);
    riga[`${p.provider}__n`] = p.citation_rate.denominatore;
    riga[`${p.provider}__k`] = p.citation_rate.numeratore;
    perGiorno.set(p.giorno, riga);
  }

  return {
    righe: [...perGiorno.values()].sort((a, b) => a.giorno.localeCompare(b.giorno)),
    provider: [...provider].sort(),
  };
}

function Suggerimento({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ dataKey?: string | number; value?: unknown; payload?: RigaGrafico }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const riga = payload[0]?.payload;
  return (
    <div className="rounded-md bg-superficie p-3 text-sm shadow-md">
      <p className="font-medium">{label ? dataBreve(label) : ""}</p>
      <ul className="mt-1.5 space-y-1">
        {payload
          .filter((v) => typeof v.dataKey === "string" && !v.dataKey.includes("__"))
          .map((v) => {
            const p = String(v.dataKey);
            const n = Number(riga?.[`${p}__n`] ?? 0);
            const k = Number(riga?.[`${p}__k`] ?? 0);
            return (
              <li key={p} className="cifre flex items-center gap-2">
                <svg width="18" height="4" viewBox="0 0 18 4" aria-hidden>
                  <line
                    x1="0"
                    y1="2"
                    x2="18"
                    y2="2"
                    stroke={serieDi(p).colore}
                    strokeWidth="2"
                    strokeDasharray={serieDi(p).tratto}
                  />
                </svg>
                <span className="text-testo-55">{p}</span>
                <span className="font-medium">
                  {typeof v.value === "number" ? percentuale(v.value) : "—"}
                </span>
                <span className="text-xs text-testo-45">
                  {k}/{n}
                </span>
              </li>
            );
          })}
      </ul>
    </div>
  );
}
