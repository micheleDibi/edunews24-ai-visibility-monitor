/** Componenti di base: card, stati vuoti, errori, scheletri, distintivi.
 *
 *  Vocabolario Nocturne: superfici piene senza bordo, un solo accento usato
 *  come contorno e mai come campitura, stati resi con le rampe tonali (niente
 *  rosso/verde semantici: e' una tavolozza mono-accento per scelta).
 */

import { CircleNotch, Info, Warning } from "@phosphor-icons/react";
import type { ReactNode } from "react";

export function Card({
  titolo,
  descrizione,
  azioni,
  children,
  id,
}: {
  titolo: string;
  descrizione?: string;
  azioni?: ReactNode;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section
      id={id}
      className="rounded-md bg-superficie p-6"
      aria-labelledby={id ? `${id}-titolo` : undefined}
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={id ? `${id}-titolo` : undefined} className="display text-md">
            {titolo}
          </h2>
          {descrizione && (
            <p className="mt-1 max-w-prose text-sm text-testo-55">{descrizione}</p>
          )}
        </div>
        {azioni && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{azioni}</div>
        )}
      </header>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/**
 * Stato vuoto. Spiega COSA FARE, non si limita a dire che non c'e' nulla:
 * un utente solo, davanti a una dashboard vuota, deve sapere il passo
 * successivo senza aprire il runbook.
 */
export function StatoVuoto({ titolo, cosaFare }: { titolo: string; cosaFare: string }) {
  return (
    <div className="flex items-start gap-3 rounded-md bg-neutro-900 px-4 py-5">
      <Info className="mt-0.5 shrink-0 text-testo-45" size={20} aria-hidden />
      <div>
        <p className="font-medium">{titolo}</p>
        <p className="mt-1 text-sm text-testo-55">{cosaFare}</p>
      </div>
    </div>
  );
}

/** Errore con il percorso di ripristino, non solo il messaggio.
 *  Mono-accento anche qui: l'errore e' un avviso in tinta accento, il
 *  contesto (icona, testo, ruolo alert) dice che e' un problema. */
export function StatoErrore({
  errore,
  riprova,
}: {
  errore: unknown;
  riprova?: () => void;
}) {
  const messaggio = errore instanceof Error ? errore.message : "errore sconosciuto";
  return (
    <div
      role="alert"
      className="flex flex-wrap items-start gap-3 rounded-md bg-accento-900 px-4 py-4"
    >
      <Warning className="mt-0.5 shrink-0 text-accento-300" size={20} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-accento-200">Non è stato possibile caricare i dati.</p>
        <p className="mt-1 break-words text-sm text-testo-55">{messaggio}</p>
        <p className="mt-1 text-sm text-testo-55">
          Se persiste, controlla che il servizio sia in esecuzione e guarda i log del container.
        </p>
      </div>
      {riprova && (
        <button
          type="button"
          onClick={riprova}
          className="cursor-pointer rounded-md border border-accento px-3 py-1.5 text-sm font-medium text-accento transition-colors hover:bg-accento/12 active:bg-accento/20"
        >
          Riprova
        </button>
      )}
    </div>
  );
}

/** Scheletro: spazio riservato, così il caricamento non fa saltare il layout. */
export function Scheletro({ righe = 3 }: { righe?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-live="polite">
      <span className="sr-only">Caricamento in corso</span>
      {Array.from({ length: righe }).map((_, i) => (
        <div
          key={i}
          className="h-6 animate-pulse rounded-sm bg-neutro-800"
          style={{ width: `${100 - i * 12}%` }}
        />
      ))}
    </div>
  );
}

/**
 * Distintivo (il «tag» Nocturne). Tavolozza mono-accento: gli stati non hanno
 * un rosso o un verde, hanno un posto sulle rampe. `accento` e' il segnale
 * positivo pieno, `neutro` l'esito normale, `pervinca` gli stati "a meta'"
 * (parziale, recuperato, senza ricerca), `muto` il contorno smorzato dei
 * salti, `allarme` il contorno accento dei guasti, `contorno` il contorno
 * accento pieno dei marcatori positivi («articolo giusto»).
 */
export function Distintivo({
  children,
  tinta = "muto",
  titolo,
}: {
  children: ReactNode;
  tinta?: "accento" | "neutro" | "pervinca" | "muto" | "allarme" | "contorno";
  titolo?: string;
}) {
  const tinte = {
    accento: "bg-accento-800 text-accento-100",
    neutro: "bg-neutro-800 text-neutro-100",
    pervinca: "bg-pervinca-900 text-pervinca-200",
    muto: "border border-divisore text-testo-45",
    // Il bordo usa l'accento base a mezza opacita', non il passo 700: le
    // rampe si specchiano fra i temi e il 700 chiaro (#d2cefd) rendeva il
    // contorno invisibile (1.5:1) sul fondo chiaro.
    allarme: "border border-accento/45 text-accento-300",
    contorno: "border border-accento text-accento",
  } as const;
  return (
    <span
      title={titolo}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-[6px] px-2.5 py-[3px] text-xs tracking-[0.02em] ${tinte[tinta]}`}
    >
      {children}
    </span>
  );
}

/** Bottone Nocturne: il primario e' un CONTORNO accento, mai un riempimento. */
export function Bottone({
  children,
  onClick,
  variante = "secondario",
  disabilitato,
  inCorso,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  variante?: "primario" | "secondario";
  disabilitato?: boolean;
  inCorso?: boolean;
  type?: "button" | "submit";
}) {
  const stili =
    variante === "primario"
      ? "border-accento text-accento hover:bg-accento/12 active:bg-accento/20"
      : "border-divisore text-testo hover:bg-testo/7 active:bg-testo/14";
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabilitato || inCorso}
      // 44px di altezza minima: e' un bersaglio tocco, non solo un bottone.
      className={`inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-md border bg-transparent px-3.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 sm:min-h-9 ${stili}`}
    >
      {inCorso && <CircleNotch size={16} className="animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

/** Selettore del periodo: il controllo segmentato Nocturne. */
export function SelettorePeriodo({
  giorni,
  onChange,
}: {
  giorni: number;
  onChange: (g: number) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Periodo di osservazione"
      className="inline-flex overflow-hidden rounded-md border border-divisore"
    >
      {[7, 30, 90].map((g) => (
        <button
          key={g}
          type="button"
          onClick={() => onChange(g)}
          aria-pressed={giorni === g}
          className={`cifre min-h-11 cursor-pointer border-0 bg-transparent px-3 text-sm transition-colors first:rounded-l-md last:rounded-r-md sm:min-h-8 ${
            giorni === g
              ? "text-accento shadow-[inset_0_0_0_1px_var(--color-accento)]"
              : "text-testo-60 hover:bg-testo/7"
          }`}
        >
          {g}g
        </button>
      ))}
    </div>
  );
}
