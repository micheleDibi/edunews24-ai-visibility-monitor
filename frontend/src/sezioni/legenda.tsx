/**
 * Guida alle metriche — la versione lunga, in fondo alla pagina.
 *
 * Le spiegazioni per sezione servono a chi ha un dubbio su un numero preciso
 * mentre lo sta guardando. Questa serve al caso opposto: la prima volta che si
 * apre la dashboard, o quando si deve spiegare a qualcun altro cosa misura.
 *
 * Sta in fondo e chiusa perché è l'unica sezione della pagina che non contiene
 * dati: aperta di default spingerebbe in basso tutto quello che invece si
 * guarda ogni giorno.
 */

import { BookOpen, ChevronDown } from "lucide-react";

import { Bottone, Card } from "../components/base";
import { PannelloGlossario } from "../components/Spiegazione";
import { GRUPPI_GLOSSARIO } from "../lib/glossario";

/** Il numero di voci, calcolato dal glossario: aggiungendone una si aggiorna da sé. */
export const VOCI_TOTALI = GRUPPI_GLOSSARIO.reduce((n, g) => n + g.voci.length, 0);

/**
 * Lo stato dell'apertura vive in `App` e non qui: il collegamento in
 * intestazione deve poter aprire la guida oltre che portarci sopra, altrimenti
 * chi lo segue atterra su una card chiusa e deve cliccare una seconda volta.
 */
export function Legenda({
  aperta,
  onCambia,
}: {
  aperta: boolean;
  onCambia: (v: boolean) => void;
}) {
  const setAperta = (f: (v: boolean) => boolean) => onCambia(f(aperta));

  return (
    <Card
      id="legenda"
      titolo="Guida alle metriche"
      descrizione="Cosa conta ogni numero, cosa entra nei denominatori e come si legge l'incertezza."
      azioni={
        <Bottone onClick={() => setAperta((v) => !v)}>
          {aperta ? (
            <ChevronDown size={16} aria-hidden />
          ) : (
            <BookOpen size={16} aria-hidden />
          )}
          {aperta ? "Chiudi la guida" : "Apri la guida"}
        </Bottone>
      }
    >
      <p className="max-w-prose text-sm text-lavagna-80">
        Ogni ora il servizio genera domande in italiano a partire dagli articoli pubblicati e le
        manda ai motori di risposta con la ricerca web attiva, poi conta quante volte
        edunews24.it compare fra le fonti. Le domande non contengono mai il nome del giornale:
        una domanda che lo nominasse otterrebbe la citazione per costruzione.
      </p>

      {!aperta ? (
        <p className="mt-2 max-w-prose text-sm text-grafite">
          La guida spiega le {VOCI_TOTALI} voci che compaiono nella dashboard. Le stesse
          definizioni sono raggiungibili dal pulsante «Come si legge» in ogni sezione.
        </p>
      ) : (
        <div className="rivela mt-4 space-y-5">
          {GRUPPI_GLOSSARIO.map((g) => (
            <div key={g.titolo}>
              {/* Un gradino sopra i termini del glossario, altrimenti il titolo
                  del gruppo e la prima voce hanno lo stesso peso e la
                  gerarchia sparisce. */}
              <h3 className="display text-md font-semibold">{g.titolo}</h3>
              <PannelloGlossario voci={g.voci} className="mt-2" />
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
