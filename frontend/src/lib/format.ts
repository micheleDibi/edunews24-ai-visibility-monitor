/** Formattazioni, tutte localizzate in italiano. */

export const percentuale = (v: number, decimali = 1) =>
  `${(v * 100).toLocaleString("it-IT", {
    minimumFractionDigits: decimali,
    maximumFractionDigits: decimali,
  })}%`;

export const euro = (v: string | number) =>
  Number(v).toLocaleString("it-IT", { style: "currency", currency: "EUR" });

export const intero = (v: number) => v.toLocaleString("it-IT");

export const dataOra = (iso: string) =>
  new Date(iso).toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

export const dataBreve = (iso: string) =>
  new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short" });

export const millisecondi = (v: number | null) =>
  v === null ? "—" : v < 1000 ? `${v} ms` : `${(v / 1000).toFixed(1)} s`;

/** Colore e tratteggio per provider: il tratteggio rende le serie leggibili
 *  in scala di grigi e per un daltonico, dove il colore da solo non basta.
 *  I token --color-serie-N cambiano col tema (sul fondo scuro le serie si
 *  schiariscono): qui si nominano i ruoli, i valori vivono in index.css. */
export const SERIE_PROVIDER: Record<string, { colore: string; tratto: string }> = {
  openai: { colore: "var(--color-serie-1)", tratto: "0" },
  perplexity: { colore: "var(--color-serie-2)", tratto: "6 4" },
  anthropic: { colore: "var(--color-serie-3)", tratto: "2 4" },
  gemini: { colore: "var(--color-serie-4)", tratto: "9 4 2 4" },
};

export const serieDi = (provider: string) =>
  SERIE_PROVIDER[provider] ?? { colore: "var(--color-testo-55)", tratto: "1 4" };

/** Etichette leggibili per gli stati dei probe e dei run. */
export const ETICHETTA_STATO: Record<string, string> = {
  ok: "riuscito",
  error: "errore",
  timeout: "scaduto",
  rate_limited: "limite di frequenza",
  no_search: "nessuna ricerca",
  running: "in corso",
  partial: "parziale",
  failed: "fallito",
  skipped_budget: "saltato per budget",
  skipped_overlap: "saltato: ciclo precedente in corso",
  skipped_misfire: "saltato: fuori tempo massimo",
  skipped_offline: "servizio fermo",
};

export const ETICHETTA_STRATEGIA: Record<string, string> = {
  faq_verbatim: "FAQ della redazione",
  keyword_intent: "keyword + intento",
  tag_combo: "combinazione di tag",
  angolo: "angolo dell'articolo",
  evergreen_howto: "procedurale evergreen",
  category: "domanda di categoria",
};
