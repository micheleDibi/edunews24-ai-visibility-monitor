/** Componenti di base: card, stati vuoti, errori, scheletri, distintivi. */

import { AlertTriangle, Info, Loader2 } from "lucide-react";
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
      className="rounded-[var(--radius-card)] border border-grafite-tenue bg-foglio shadow-card"
      aria-labelledby={id ? `${id}-titolo` : undefined}
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-grafite-tenue px-4 py-3">
        <div className="min-w-0">
          <h2 id={id ? `${id}-titolo` : undefined} className="display text-lg font-semibold">
            {titolo}
          </h2>
          {descrizione && (
            <p className="mt-0.5 max-w-prose text-sm text-grafite">{descrizione}</p>
          )}
        </div>
        {azioni && <div className="flex shrink-0 items-center gap-2">{azioni}</div>}
      </header>
      <div className="p-4">{children}</div>
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
    <div className="flex items-start gap-3 rounded-[var(--radius-controllo)] bg-gesso px-4 py-5">
      <Info className="mt-0.5 shrink-0 text-grafite" size={20} strokeWidth={1.5} aria-hidden />
      <div>
        <p className="font-medium">{titolo}</p>
        <p className="mt-1 text-sm text-grafite">{cosaFare}</p>
      </div>
    </div>
  );
}

/** Errore con il percorso di ripristino, non solo il messaggio. */
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
      className="flex flex-wrap items-start gap-3 rounded-[var(--radius-controllo)] bg-sigillo-tenue px-4 py-4"
    >
      <AlertTriangle
        className="mt-0.5 shrink-0 text-sigillo"
        size={20}
        strokeWidth={1.5}
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-sigillo">Non è stato possibile caricare i dati.</p>
        <p className="mt-1 break-words text-sm text-grafite">{messaggio}</p>
        <p className="mt-1 text-sm text-grafite">
          Se persiste, controlla che il servizio sia in esecuzione e guarda i log del container.
        </p>
      </div>
      {riprova && (
        <button
          type="button"
          onClick={riprova}
          className="rounded-[var(--radius-controllo)] border border-sigillo px-3 py-1.5 text-sm font-medium text-sigillo transition-colors hover:bg-sigillo hover:text-foglio"
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
          className="h-6 animate-pulse rounded-[var(--radius-controllo)] bg-grafite-tenue"
          style={{ width: `${100 - i * 12}%` }}
        />
      ))}
    </div>
  );
}

export function Distintivo({
  children,
  tinta = "grafite",
  titolo,
}: {
  children: ReactNode;
  tinta?: "timbro" | "alloro" | "ottone" | "grafite" | "sigillo";
  titolo?: string;
}) {
  const tinte = {
    timbro: "bg-timbro-tenue text-timbro",
    alloro: "bg-alloro-tenue text-alloro",
    ottone: "bg-ottone-tenue text-ottone",
    grafite: "bg-grafite-tenue text-lavagna-80",
    sigillo: "bg-sigillo-tenue text-sigillo",
  } as const;
  return (
    <span
      title={titolo}
      className={`inline-flex items-center gap-1 rounded-[var(--radius-controllo)] px-1.5 py-0.5 text-xs font-medium ${tinte[tinta]}`}
    >
      {children}
    </span>
  );
}

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
      ? "bg-timbro text-foglio hover:opacity-90"
      : "border border-grafite-tenue bg-foglio text-lavagna hover:bg-gesso";
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabilitato || inCorso}
      // 44px di altezza minima: e' un bersaglio tocco, non solo un bottone.
      className={`inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-[var(--radius-controllo)] px-3.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 sm:min-h-9 ${stili}`}
    >
      {inCorso && <Loader2 size={16} className="animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function SelettorePeriodo({
  giorni,
  onChange,
}: {
  giorni: number;
  onChange: (g: number) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-grafite">Periodo</span>
      <select
        value={giorni}
        onChange={(e) => onChange(Number(e.target.value))}
        className="min-h-11 cursor-pointer rounded-[var(--radius-controllo)] border border-grafite-tenue bg-foglio px-2 text-sm sm:min-h-9"
      >
        <option value={7}>7 giorni</option>
        <option value={30}>30 giorni</option>
        <option value={90}>90 giorni</option>
      </select>
    </label>
  );
}
