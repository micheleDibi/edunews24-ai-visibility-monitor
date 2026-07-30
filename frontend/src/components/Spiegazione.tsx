/**
 * SPIEGAZIONE — la disclosure che rende interpretabili i numeri.
 *
 * Tre scelte non negoziabili, in ordine di importanza:
 *
 * 1. È un PULSANTE, non un tooltip al passaggio del mouse. Su un telefono il
 *    passaggio del mouse non esiste, e un utente che tocca un tooltip lo vede
 *    lampeggiare e sparire. Chi legge questa dashboard dal telefono al mattino
 *    ha lo stesso diritto alla definizione di chi la apre dal desktop.
 *
 * 2. Il pannello si apre NEL FLUSSO, sopra il contenuto, e sposta il resto in
 *    basso. Un popover sovrapposto coprirebbe proprio i numeri che sta
 *    spiegando, e su schermo stretto finirebbe fuori dal viewport.
 *
 * 3. Il testo è lo stesso ovunque, perché arriva da `lib/glossario.ts`. La
 *    stessa metrica compare in cinque sezioni: se ogni sezione riscrivesse la
 *    propria definizione, prima o poi due si contraddirebbero.
 *
 * Chiusura con Esc e ritorno del fuoco al pulsante: chi naviga da tastiera non
 * deve ritrovarsi a fondo pannello senza via d'uscita.
 */

import { HelpCircle, TriangleAlert, X } from "lucide-react";
import { useId, useRef, useState } from "react";

import { GLOSSARIO, type ChiaveGlossario } from "../lib/glossario";

/* ------------------------------------------------------------- il pannello */

export function PannelloGlossario({
  voci,
  id,
  className = "",
}: {
  voci: readonly ChiaveGlossario[];
  id?: string;
  className?: string;
}) {
  return (
    <div
      id={id}
      // `max-w-3xl`: senza, su schermo largo il fondo grigio arriva a 1200px
      // mentre il testo si ferma a 600 (`max-w-prose` sui paragrafi), e metà
      // pannello resta una campitura vuota che sembra un errore di caricamento.
      className={`nota rivela max-w-3xl rounded-r-[var(--radius-controllo)] bg-gesso py-3 pl-4 pr-4 ${className}`}
    >
      {/* `space-y-5` e non meno: fra i paragrafi di una voce c'è 0,375rem, e
          se lo stacco fra una voce e la successiva non è nettamente maggiore il
          termine in grassetto sembra il titolo dell'ultimo paragrafo di quella
          precedente invece dell'inizio di una voce nuova. */}
      <dl className="space-y-5">
        {voci.map((chiave) => (
          <VoceStampata key={chiave} chiave={chiave} />
        ))}
      </dl>
    </div>
  );
}

function VoceStampata({ chiave }: { chiave: ChiaveGlossario }) {
  const v = GLOSSARIO[chiave];
  return (
    <div>
      <dt className="display text-base font-semibold text-lavagna">{v.termine}</dt>
      {/* `text-base` e non `text-sm`: la scala tipografica riserva i 13px alle
          etichette e ai dati fitti, ma questi sono paragrafi che si leggono uno
          dopo l'altro. `max-w-prose` tiene le righe sotto i ~70 caratteri,
          oltre i quali l'occhio perde il rigo tornando a capo. */}
      <dd className="mt-1 max-w-prose space-y-1.5 leading-relaxed text-lavagna-80">
        <p>{v.misura}</p>
        {/* `lavagna-60` e non `grafite`: su fondo `gesso` grafite dà 4,19:1,
            sotto il minimo AA di 4,5. È testo secondario, non testo opzionale. */}
        {"conto" in v && v.conto && <p className="text-lavagna-60">{v.conto}</p>}
        {"lettura" in v && v.lettura && <p>{v.lettura}</p>}
        {"attenzione" in v && v.attenzione && (
          <p className="flex gap-1.5 text-ottone">
            <TriangleAlert size={15} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden />
            <span>{v.attenzione}</span>
          </p>
        )}
      </dd>
    </div>
  );
}

/* -------------------------------------------------------------- il pulsante */

export function BottoneSpiegazione({
  aperto,
  onToggle,
  controlla,
  etichetta = "Come si legge",
  riferimento,
}: {
  aperto: boolean;
  onToggle: () => void;
  controlla: string;
  etichetta?: string;
  riferimento?: React.Ref<HTMLButtonElement>;
}) {
  const Icona = aperto ? X : HelpCircle;
  return (
    <button
      ref={riferimento}
      type="button"
      onClick={onToggle}
      aria-expanded={aperto}
      aria-controls={controlla}
      // 44px di altezza su mobile: è un bersaglio tocco come gli altri.
      className={`inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-[var(--radius-controllo)] px-2 text-sm font-medium transition-colors sm:min-h-8 ${
        aperto ? "bg-timbro-tenue text-timbro" : "text-grafite hover:bg-gesso hover:text-timbro"
      }`}
    >
      <Icona size={16} strokeWidth={1.75} aria-hidden />
      {etichetta}
      <span className="sr-only">{aperto ? " — chiudi la spiegazione" : ""}</span>
    </button>
  );
}

/* ------------------------------------------------ pulsante + pannello insieme */

/**
 * Versione autonoma, per i blocchi che non sono una `Card` (l'header KPI).
 * Dentro una `Card` si usa invece la prop `spiega`, che mette il pulsante
 * nell'intestazione e il pannello in cima al corpo.
 */
export function Spiegazione({
  voci,
  etichetta,
  className = "",
}: {
  voci: readonly ChiaveGlossario[];
  etichetta?: string;
  className?: string;
}) {
  const { aperto, alterna, idPannello, bottone, chiudiConEsc } = useSpiegazione();
  return (
    <div className={className} onKeyDown={chiudiConEsc}>
      <BottoneSpiegazione
        aperto={aperto}
        onToggle={alterna}
        controlla={idPannello}
        etichetta={etichetta}
        riferimento={bottone}
      />
      {aperto && <PannelloGlossario id={idPannello} voci={voci} className="mt-2" />}
    </div>
  );
}

/* ------------------------------------------------------------------ il gancio */

/** Stato condiviso fra `Spiegazione` e `Card`, per non duplicarlo due volte. */
export function useSpiegazione() {
  const [aperto, setAperto] = useState(false);
  const idPannello = useId();
  const bottone = useRef<HTMLButtonElement>(null);

  const chiudiConEsc = (e: React.KeyboardEvent) => {
    if (e.key !== "Escape" || !aperto) return;
    setAperto(false);
    // Il fuoco torna al pulsante: senza questo, chi chiude da tastiera resta
    // ancorato a un elemento che non esiste più e riparte da inizio pagina.
    bottone.current?.focus();
  };

  return {
    aperto,
    alterna: () => setAperto((v) => !v),
    idPannello,
    bottone,
    chiudiConEsc,
  };
}
