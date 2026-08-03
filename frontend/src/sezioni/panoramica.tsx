/** Sezione 1 — Header KPI. Sezione 2 — Tendenza. */

import { useQuery } from "@tanstack/react-query";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";
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

import { BandaIncertezza, descriviTasso } from "../components/BandaIncertezza";
import { Card, Scheletro, StatoErrore, StatoVuoto } from "../components/base";
import {
  BottoneSpiegazione,
  PannelloGlossario,
  useSpiegazione,
} from "../components/Spiegazione";
import { api, type Delta, type PuntoTendenza, type Tasso } from "../lib/api";
import type { ChiaveGlossario } from "../lib/glossario";
import { dataBreve, euro, intero, percentuale, serieDi } from "../lib/format";

/**
 * Le voci spiegate dall'header KPI: i quattro tassi che mostra, più le tre
 * convenzioni di lettura che li governano tutti (la banda, la soglia sotto cui
 * si vede un trattino, quando una variazione conta) e i probe senza ricerca,
 * che compaiono nel conteggio in basso a destra.
 */
const VOCI_KPI: readonly ChiaveGlossario[] = [
  "citation_rate",
  "mention",
  "target_hit",
  "recuperato",
  "banda",
  "soglia",
  "significativita",
  "nessuna_ricerca",
];

/* ------------------------------------------------------------------ KPI */

function NumeroSecondario({
  etichetta,
  tasso,
  nota,
}: {
  etichetta: string;
  tasso: Tasso;
  nota: string;
}) {
  return (
    <div>
      <h3 className="text-sm font-medium text-grafite">{etichetta}</h3>
      <div className="mt-1">
        <BandaIncertezza tasso={tasso} tinta="grafite" etichetta={etichetta} />
      </div>
      <p className="mt-1 text-xs text-grafite">{nota}</p>
    </div>
  );
}

/**
 * Il delta compare SOLO se significativo. Se gli intervalli di confidenza dei
 * due periodi si sovrappongono, la differenza e' rumore: mostrarla con una
 * freccia verde sarebbe la bugia piu' facile di tutta l'interfaccia.
 */
function Variazione({ delta }: { delta: Delta }) {
  if (delta.differenza === null) {
    return (
      <p className="text-sm text-grafite">
        Nessun confronto: il periodo precedente non ha abbastanza probe.
      </p>
    );
  }
  if (!delta.significativo) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-grafite">
        <Minus size={16} strokeWidth={1.5} aria-hidden />
        Variazione non significativa ({percentuale(delta.precedente.tasso ?? 0)} nel periodo
        precedente): gli intervalli si sovrappongono.
      </p>
    );
  }
  const su = delta.differenza > 0;
  const Icona = su ? TrendingUp : TrendingDown;
  return (
    <p
      className={`flex items-center gap-1.5 text-sm font-medium ${su ? "text-alloro" : "text-sigillo"}`}
    >
      <Icona size={16} strokeWidth={1.5} aria-hidden />
      {su ? "+" : ""}
      {percentuale(delta.differenza)} rispetto al periodo precedente
      <span className="font-normal text-grafite">
        (era {percentuale(delta.precedente.tasso ?? 0)})
      </span>
    </p>
  );
}

export function HeaderKpi({ giorni }: { giorni: number }) {
  const spiega = useSpiegazione();
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["kpi", giorni],
    queryFn: () => api.kpi(giorni),
  });

  if (error) return <StatoErrore errore={error} riprova={() => void refetch()} />;
  if (isPending)
    return (
      <div className="rounded-[var(--radius-card)] border border-grafite-tenue bg-foglio p-4 shadow-card">
        <Scheletro righe={4} />
      </div>
    );

  const k = data!;
  if (k.probe_totali === 0) {
    return (
      <div className="rounded-[var(--radius-card)] border border-grafite-tenue bg-foglio p-4 shadow-card">
        <StatoVuoto
          titolo={`Nessun probe riuscito negli ultimi ${giorni} giorni.`}
          cosaFare="Il ciclo orario gira al minuto 7 di ogni ora. Per un ciclo immediato usa «Esegui un ciclo» nello stato del sistema, oppure `python sender.py run-once` dal container."
        />
      </div>
    );
  }

  return (
    <div
      className="rounded-[var(--radius-card)] border border-grafite-tenue bg-foglio p-4 shadow-card"
      onKeyDown={spiega.chiudiConEsc}
    >
      {/* Titolo e spiegazione in cima: il pannello si apre SOPRA i numeri, mai
          davanti, così non copre proprio quello che sta spiegando. */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="display text-lg font-semibold">Citation rate</h2>
          <p className="mt-0.5 max-w-prose text-sm text-grafite">
            Quota di risposte con web search attiva in cui edunews24.it compare fra le fonti
            citate, negli ultimi {giorni} giorni.
          </p>
        </div>
        <BottoneSpiegazione
          aperto={spiega.aperto}
          onToggle={spiega.alterna}
          controlla={spiega.idPannello}
          etichetta="Cosa vogliono dire questi numeri"
          riferimento={spiega.bottone}
        />
      </div>

      {spiega.aperto && (
        <PannelloGlossario id={spiega.idPannello} voci={VOCI_KPI} className="mt-3" />
      )}

      <div className="mt-3 grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* Il numero che conta, con il peso visivo maggiore. */}
        <div>
          <div className="max-w-md">
            <BandaIncertezza
              tasso={k.citation_rate}
              taglia="grande"
              tinta="timbro"
              etichetta="citation rate"
            />
          </div>
          <div className="mt-3">
            <Variazione delta={k.citation_rate_delta} />
          </div>
        </div>

        <div className="grid gap-4 border-t border-grafite-tenue pt-4 sm:grid-cols-2 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
          <NumeroSecondario
            etichetta="Mention senza link"
            tasso={k.mention_rate}
            nota="Il modello nomina il giornale ma non lo cita come fonte. Segnale diverso: riconoscimento, non retrieval."
          />
          <NumeroSecondario
            etichetta="Articolo giusto"
            tasso={k.target_hit_rate}
            nota="Citato proprio il pezzo che ha generato la domanda, non un altro del sito."
          />
          <NumeroSecondario
            etichetta="Recuperato"
            tasso={k.retrieval_rate}
            nota="Comparso fra le fonti mostrate al modello, citato o no. Recuperato-ma-non-citato è un problema di qualità percepita, non di indicizzazione."
          />
          <div>
            <h3 className="text-sm font-medium text-grafite">Costo del periodo</h3>
            <p className="display cifre mt-1 text-xl font-semibold">{euro(k.costo_eur)}</p>
            <p className="mt-1 text-xs text-grafite">
              {intero(k.probe_totali)} probe riusciti
              {k.probe_falliti > 0 && `, ${intero(k.probe_falliti)} falliti`}
              {k.probe_senza_ricerca > 0 &&
                `, ${intero(k.probe_senza_ricerca)} senza ricerca (esclusi dai conti)`}
              .
            </p>
          </div>
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

  const { righe, provider } = useMemo(() => aggrega(data ?? []), [data]);

  return (
    <Card
      id="tendenza"
      titolo="Tendenza"
      descrizione="Citation rate giorno per giorno. Le serie si distinguono per tratteggio oltre che per colore, così restano leggibili in scala di grigi."
      spiega={["citation_rate", "banda", "soglia", "ciclo"]}
      azioni={
        <label className="flex items-center gap-2 text-sm">
          <span className="text-grafite">Provider</span>
          <select
            value={soloProvider}
            onChange={(e) => setSoloProvider(e.target.value)}
            className="min-h-11 cursor-pointer rounded-[var(--radius-controllo)] border border-grafite-tenue bg-foglio px-2 text-sm sm:min-h-9"
          >
            <option value="">tutti</option>
            {provider.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      }
    >
      {error ? (
        <StatoErrore errore={error} riprova={() => void refetch()} />
      ) : isPending ? (
        <Scheletro righe={6} />
      ) : righe.length < 2 ? (
        <StatoVuoto
          titolo="Servono almeno due giorni di dati per disegnare una tendenza."
          cosaFare="Il grafico si popola da sé man mano che i cicli orari girano. Il giorno corrente è calcolato in tempo reale, i precedenti dagli aggregati notturni."
        />
      ) : (
        <>
          <div className="h-72 w-full">
            <ResponsiveContainer>
              <ComposedChart data={righe} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
                <CartesianGrid stroke="var(--color-divisore)" vertical={false} />
                <XAxis
                  dataKey="giorno"
                  tickFormatter={dataBreve}
                  tick={{ fontSize: 12, fill: "var(--color-testo-45)" }}
                  stroke="var(--color-divisore)"
                  minTickGap={24}
                />
                <YAxis
                  domain={[0, 1]}
                  tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                  tick={{ fontSize: 12, fill: "var(--color-testo-45)" }}
                  stroke="var(--color-divisore)"
                  width={48}
                />
                <Tooltip content={<Suggerimento />} />
                <Legend
                  verticalAlign="bottom"
                  height={28}
                  wrapperStyle={{ fontSize: 13 }}
                  formatter={(v) => <span className="text-lavagna">{String(v)}</span>}
                />
                {/* La banda d'incertezza attorno alla linea, quando si guarda
                    un solo provider: con piu' serie diventerebbe illeggibile. */}
                {provider.length === 1 &&
                  provider[0] && (
                    <Area
                      dataKey={`${provider[0]}__ic`}
                      stroke="none"
                      fill={serieDi(provider[0]).colore}
                      fillOpacity={0.14}
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
          {provider.length > 1 && (
            <p className="mt-2 text-xs text-grafite">
              L'intervallo di confidenza si disegna selezionando un solo provider: con più
              serie sovrapposte diventerebbe illeggibile.
            </p>
          )}
        </>
      )}
    </Card>
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
    <div className="rounded-[var(--radius-controllo)] border border-grafite-tenue bg-foglio p-2.5 text-sm shadow-alzata">
      <p className="font-medium">{label ? dataBreve(label) : ""}</p>
      <ul className="mt-1 space-y-0.5">
        {payload
          .filter((v) => typeof v.dataKey === "string" && !v.dataKey.includes("__"))
          .map((v) => {
            const p = String(v.dataKey);
            const n = Number(riga?.[`${p}__n`] ?? 0);
            const k = Number(riga?.[`${p}__k`] ?? 0);
            return (
              <li key={p} className="cifre flex items-center gap-2">
                <span
                  aria-hidden
                  className="inline-block h-0.5 w-4"
                  style={{ background: serieDi(p).colore }}
                />
                <span className="text-grafite">{p}</span>
                <span className="font-medium">
                  {typeof v.value === "number" ? percentuale(v.value) : "—"}
                </span>
                <span className="text-xs text-grafite">
                  {k}/{n}
                </span>
              </li>
            );
          })}
      </ul>
    </div>
  );
}

export { descriviTasso };
