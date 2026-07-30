/**
 * ELEMENTO FIRMA — la banda d'incertezza.
 *
 * Ogni tasso di questa interfaccia si disegna come cifra + banda in scala +
 * conteggi. La banda copre l'intervallo di Wilson sull'asse 0–100%: un
 * intervallo largo SEMBRA largo, invece di essere una postilla in un tooltip.
 *
 * Quando il campione non basta la cifra diventa un tratto e la banda si
 * tratteggia a tutta larghezza: l'assenza di misura si vede, non si deduce.
 *
 * Vedi docs/design.md §5.
 */

import type { Tasso } from "../lib/api";
import { percentuale } from "../lib/format";

type Taglia = "grande" | "compatta";

interface Props {
  tasso: Tasso;
  taglia?: Taglia;
  /** Colore della banda; per default `timbro` (presenza). */
  tinta?: "timbro" | "alloro" | "grafite";
  /** Etichetta letta dagli screen reader al posto del disegno. */
  etichetta?: string;
}

const TINTE = {
  timbro: { barra: "bg-timbro", punto: "bg-timbro", testo: "text-timbro" },
  alloro: { barra: "bg-alloro", punto: "bg-alloro", testo: "text-alloro" },
  grafite: { barra: "bg-grafite", punto: "bg-grafite", testo: "text-grafite" },
} as const;

/** Testo alternativo: e' l'unica versione che un lettore di schermo riceve. */
export function descriviTasso(t: Tasso, etichetta = "tasso"): string {
  if (t.denominatore === 0) return `${etichetta}: nessun dato`;
  if (t.tasso === null) {
    return `${etichetta}: non calcolabile, solo ${t.numeratore} su ${t.denominatore} casi`;
  }
  const base = `${etichetta}: ${percentuale(t.tasso)}, ${t.numeratore} su ${t.denominatore}`;
  if (t.ic_basso === null || t.ic_alto === null) return base;
  const affidabilita = t.affidabile ? "" : ", campione piccolo";
  return `${base}, intervallo di confidenza dal ${percentuale(t.ic_basso)} al ${percentuale(
    t.ic_alto,
  )}${affidabilita}`;
}

export function BandaIncertezza({
  tasso,
  taglia = "compatta",
  tinta = "timbro",
  etichetta = "tasso",
}: Props) {
  const t = TINTE[tinta];
  const grande = taglia === "grande";
  const nonMisurabile = tasso.tasso === null;
  const vuoto = tasso.denominatore === 0;

  const sinistra = ((tasso.ic_basso ?? 0) * 100).toFixed(2);
  const larghezza = (((tasso.ic_alto ?? 1) - (tasso.ic_basso ?? 0)) * 100).toFixed(2);
  const stima = ((tasso.tasso ?? 0) * 100).toFixed(2);

  return (
    <div
      className={grande ? "w-full" : "w-full min-w-[3rem]"}
      role="img"
      aria-label={descriviTasso(tasso, etichetta)}
    >
      {/* Cifra */}
      <div className="flex items-baseline gap-1.5">
        <span
          className={[
            grande ? "cifra-madre" : "display cifre font-semibold",
            nonMisurabile ? "text-grafite" : t.testo,
          ].join(" ")}
          style={grande ? undefined : { fontSize: "var(--text-md)" }}
        >
          {vuoto || nonMisurabile ? "—" : percentuale(tasso.tasso!)}
        </span>
        {grande && !vuoto && (
          <span className="cifre text-sm text-grafite">
            {tasso.numeratore}/{tasso.denominatore}
          </span>
        )}
      </div>

      {/* Banda */}
      <div
        className={[
          "relative mt-1 w-full rounded-full bg-grafite-tenue",
          grande ? "h-2" : "h-1",
        ].join(" ")}
      >
        {vuoto ? null : nonMisurabile ? (
          <div className="banda-non-misurabile absolute inset-0 rounded-full" />
        ) : (
          <>
            <div
              className={`absolute inset-y-0 rounded-full ${t.barra} ${
                tasso.affidabile ? "opacity-100" : "opacity-45"
              }`}
              style={{ left: `${sinistra}%`, width: `${larghezza}%` }}
            />
            <div
              className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-foglio ${t.punto} ${
                grande ? "h-3.5 w-3.5" : "h-2 w-2"
              }`}
              style={{ left: `${stima}%` }}
            />
          </>
        )}
      </div>

      {/* Conteggi e avvertenza */}
      {!grande && (
        <div className="mt-0.5 cifre text-xs leading-tight text-grafite">
          {vuoto ? "nessun dato" : `${tasso.numeratore}/${tasso.denominatore}`}
        </div>
      )}
      {grande && (
        <p className="mt-2 text-xs text-grafite">
          {vuoto
            ? "Nessun probe riuscito nel periodo."
            : nonMisurabile
              ? `Solo ${tasso.denominatore} probe: troppo pochi per una percentuale.`
              : tasso.affidabile
                ? `Intervallo di confidenza 95%: ${percentuale(tasso.ic_basso!)} – ${percentuale(
                    tasso.ic_alto!,
                  )}.`
                : `Campione piccolo (${tasso.denominatore}): l'intervallo va dal ${percentuale(
                    tasso.ic_basso!,
                  )} al ${percentuale(tasso.ic_alto!)}.`}
        </p>
      )}
    </div>
  );
}
