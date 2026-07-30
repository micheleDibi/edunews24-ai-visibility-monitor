/**
 * Client dell'API e tipi.
 *
 * I tipi rispecchiano i modelli Pydantic del backend. `Tasso` in particolare:
 * il backend NON restituisce mai una percentuale nuda, quindi il frontend non
 * ha modo di mostrarne una.
 */

export type Modo = "retrieval" | "memory";

/** Un rapporto che non si puo' leggere senza il suo denominatore. */
export interface Tasso {
  numeratore: number;
  denominatore: number;
  /** `null` quando il denominatore e' sotto la soglia minima: non si stampa. */
  tasso: number | null;
  ic_basso: number | null;
  ic_alto: number | null
  affidabile: boolean;
}

export interface Delta {
  attuale: Tasso;
  precedente: Tasso;
  differenza: number | null;
  /** Vero solo se gli intervalli non si sovrappongono. */
  significativo: boolean;
}

export interface Kpi {
  giorni: number;
  mode: Modo;
  citation_rate: Tasso;
  citation_rate_delta: Delta;
  mention_rate: Tasso;
  target_hit_rate: Tasso;
  retrieval_rate: Tasso;
  probe_totali: number;
  probe_falliti: number;
  probe_senza_ricerca: number;
  costo_eur: string;
}

export interface PuntoTendenza {
  giorno: string;
  provider: string;
  citation_rate: Tasso;
  costo_eur: string;
}

export interface RigaProvider {
  provider: string;
  model: string | null;
  citation_rate: Tasso;
  mention_rate: Tasso;
  target_hit_rate: Tasso;
  memoria: Tasso;
  latenza_mediana_ms: number | null;
  ricerche_medie: number | null;
  costo_eur: string;
  probe_falliti: number;
}

export interface CellaCategoria {
  category_slug: string;
  provider: string;
  citation_rate: Tasso;
}

export interface Lacuna {
  topic_id: number;
  source_id: number;
  slug: string;
  title: string;
  category_slug: string | null;
  published_at: string | null;
  probe: number;
  /** Quante volte il motore ha aperto la pagina senza citarla. Qui sono tutti
   *  articoli mai citati: sopra zero manca la forma del pezzo, a zero il pezzo. */
  recuperi: number;
}

export interface Successo {
  topic_id: number;
  slug: string;
  title: string;
  category_slug: string | null;
  citazioni: number;
  target_hit: number;
  probe: number;
  citation_rate: Tasso;
  provider: string[];
}

export interface RigaDominio {
  domain: string;
  probe: number;
  citazioni: number;
  quota: Tasso;
  proprio: boolean;
  non_risolto: boolean;
}

export interface Citazione {
  domain: string;
  url: string | null;
  title: string | null;
  kind: "citation" | "source";
  position: number | null;
  is_own: boolean;
  own_slug: string | null;
}

export interface ProbeVisto {
  id: number;
  run_id: number;
  created_at: string;
  provider: string;
  model: string;
  mode: Modo;
  status: string;
  error: string | null;
  latency_ms: number | null;
  search_calls: number | null;
  costo_eur: string | null;
  costo_stimato: boolean;
  edunews_cited: boolean;
  edunews_mention: boolean;
  edunews_retrieved: boolean;
  target_hit: boolean;
  query_id: number;
  query_text: string;
  query_strategy: string;
  category_slug: string | null;
  topic_slug: string | null;
  answer_text: string | null;
  citazioni: Citazione[];
}

export interface PaginaProbe {
  totale: number;
  offset: number;
  limit: number;
  elementi: ProbeVisto[];
}

export interface RunVisto {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  kind: string;
  planned: number;
  completed: number;
  failed: number;
  costo_eur: string;
  notes: string | null;
}

export interface StatoCosti {
  giorno_eur: string;
  mese_eur: string;
  tetto_giorno_eur: string;
  tetto_mese_eur: string;
  residuo_giorno_eur: string;
  budget_superato: boolean;
  motivo: string | null;
}

export interface Salute {
  stato: string;
  database: string;
  scheduler: string;
  prossime_esecuzioni: Record<string, string | null>;
}

/** Sollevata quando la sessione non c'e' o e' scaduta: fa tornare al login. */
export class NonAutenticato extends Error {}

async function chiama<T>(percorso: string, opzioni: RequestInit = {}): Promise<T> {
  const risposta = await fetch(`/api${percorso}`, {
    ...opzioni,
    headers: { "content-type": "application/json", ...opzioni.headers },
    // Il cookie di sessione e' httpOnly: same-origin lo manda da se'.
    credentials: "same-origin",
  });

  if (risposta.status === 401) throw new NonAutenticato("sessione assente o scaduta");
  if (!risposta.ok) {
    let dettaglio = `HTTP ${risposta.status}`;
    try {
      const corpo = await risposta.json();
      if (corpo?.detail) dettaglio = String(corpo.detail);
    } catch {
      /* il corpo non era JSON: resta il codice */
    }
    throw new Error(dettaglio);
  }
  if (risposta.status === 204) return undefined as T;
  return risposta.json() as Promise<T>;
}

const q = (parametri: Record<string, string | number | boolean | undefined>) => {
  const cerca = new URLSearchParams();
  for (const [chiave, valore] of Object.entries(parametri)) {
    if (valore !== undefined && valore !== "") cerca.set(chiave, String(valore));
  }
  const s = cerca.toString();
  return s ? `?${s}` : "";
};

export const api = {
  login: (password: string) =>
    chiama<{ ok: boolean }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  logout: () => chiama<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  me: () => chiama<{ soggetto: string }>("/me"),

  salute: () => chiama<Salute>("/health"),
  costi: () => chiama<StatoCosti>("/costs"),

  kpi: (giorni: number, modo: Modo = "retrieval") =>
    chiama<Kpi>(`/kpi${q({ days: giorni, mode: modo })}`),
  tendenza: (giorni: number, provider?: string) =>
    chiama<PuntoTendenza[]>(`/trend${q({ days: giorni, provider })}`),
  provider: (giorni: number) => chiama<RigaProvider[]>(`/providers${q({ days: giorni })}`),
  categorie: (giorni: number) => chiama<CellaCategoria[]>(`/categories${q({ days: giorni })}`),
  lacune: (giorni: number, minProbe: number) =>
    chiama<Lacuna[]>(`/gaps${q({ days: giorni, min_probe: minProbe })}`),
  successi: (giorni: number) => chiama<Successo[]>(`/wins${q({ days: giorni })}`),
  domini: (giorni: number) => chiama<RigaDominio[]>(`/domains${q({ days: giorni })}`),
  run: (limite = 20) => chiama<RunVisto[]>(`/runs${q({ limit: limite })}`),

  probe: (parametri: {
    days?: number;
    provider?: string;
    mode?: Modo;
    status?: string;
    cited?: boolean;
    topic_id?: number;
    q?: string;
    offset?: number;
    limit?: number;
  }) => chiama<PaginaProbe>(`/probes${q(parametri)}`),

  eseguiOra: (quante: number) =>
    chiama<{ avviato: boolean; messaggio: string }>(
      `/actions/run-now${q({ quante })}`,
      { method: "POST" },
    ),
};
