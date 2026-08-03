/**
 * Guida alle metriche — la vista di riferimento.
 *
 * L'unica vista senza dati: spiega cosa conta ogni numero, cosa entra nei
 * denominatori e come si legge l'incertezza. Serve la prima volta che si apre
 * la dashboard, o quando si deve spiegare a qualcun altro cosa misura.
 */

import { Warning } from "@phosphor-icons/react";

import { GLOSSARIO, GRUPPI_GLOSSARIO } from "../lib/glossario";
import type { VoceGlossario } from "../lib/glossario";

export function Legenda() {
  return (
    <section aria-labelledby="guida-titolo">
      <p className="text-[11px] uppercase tracking-[0.1em] text-accento">Riferimento</p>
      <h1 id="guida-titolo" className="display mt-1.5 text-xl">
        Guida alle metriche
      </h1>
      <p className="mt-3 max-w-[65ch] text-sm leading-relaxed text-testo-70">
        Ogni ora il servizio genera domande in italiano a partire dagli articoli pubblicati e
        le manda ai motori di risposta con la ricerca web attiva, poi conta quante volte
        edunews24.it compare fra le fonti. Le domande non contengono mai il nome del giornale:
        una domanda che lo nominasse otterrebbe la citazione per costruzione.
      </p>

      <div className="mt-9 flex flex-col gap-9">
        {GRUPPI_GLOSSARIO.map((g) => (
          <div key={g.titolo}>
            <h2 className="display text-[18px] text-accento-300">{g.titolo}</h2>
            <div className="righello mt-1.5" />
            <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-x-10 gap-y-6">
              {g.voci.map((chiave) => {
                const voce: VoceGlossario = GLOSSARIO[chiave];
                return (
                  <div key={chiave} className="max-w-[60ch]">
                    <h3 className="text-base font-medium">{voce.termine}</h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-testo-70">{voce.misura}</p>
                    {voce.conto && (
                      <p className="cifre mt-1.5 text-xs text-testo-45">{voce.conto}</p>
                    )}
                    {voce.lettura && (
                      <p className="mt-1.5 text-sm leading-relaxed text-testo-55">
                        {voce.lettura}
                      </p>
                    )}
                    {voce.attenzione && (
                      <p className="mt-2 text-xs leading-relaxed text-accento-300">
                        <Warning size={13} className="mr-1.5 inline align-[-2px]" aria-hidden />
                        {voce.attenzione}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
