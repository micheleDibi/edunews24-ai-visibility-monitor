/** Il guscio Nocturne: sidebar di navigazione, mini-router, login.
 *
 *  Sei viste su percorsi reali (il catch-all della SPA lato server li serve
 *  gia'): niente libreria di routing, history API e un listener su popstate.
 *  Sotto i 900px la sidebar diventa una barra superiore compatta.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  EyeSlash,
  Gauge,
  ListMagnifyingGlass,
  Pulse,
  Scales,
  SignOut,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Bottone, SelettorePeriodo } from "./components/base";
import { NonAutenticato, api } from "./lib/api";
import { Confronti, Domini } from "./sezioni/confronti";
import { CosaFunziona, DoveInvisibile } from "./sezioni/operativo";
import { EsploraProbe } from "./sezioni/esplora";
import { Legenda } from "./sezioni/legenda";
import { HeaderKpi, Tendenza } from "./sezioni/panoramica";
import { StatoSistema } from "./sezioni/sistema";

const VISTE: Array<{ percorso: string; etichetta: string; icona: Icon }> = [
  { percorso: "/", etichetta: "Panoramica", icona: Gauge },
  { percorso: "/invisibile", etichetta: "Dove sei invisibile", icona: EyeSlash },
  { percorso: "/confronti", etichetta: "Provider e categorie", icona: Scales },
  { percorso: "/esplora", etichetta: "Esplora probe", icona: ListMagnifyingGlass },
  { percorso: "/sistema", etichetta: "Stato del sistema", icona: Pulse },
  { percorso: "/guida", etichetta: "Guida alle metriche", icona: BookOpen },
];

/** Router minimo: il percorso e' stato, la history e' la verita'. */
function usePercorso(): [string, (p: string) => void] {
  const [percorso, setPercorso] = useState(window.location.pathname);

  useEffect(() => {
    const suPop = () => setPercorso(window.location.pathname);
    window.addEventListener("popstate", suPop);
    return () => window.removeEventListener("popstate", suPop);
  }, []);

  const naviga = useCallback((p: string) => {
    if (p === window.location.pathname) return;
    window.history.pushState(null, "", p);
    setPercorso(p);
    window.scrollTo({ top: 0 });
  }, []);

  return [percorso, naviga];
}

export default function App() {
  const cache = useQueryClient();
  const [giorni, setGiorni] = useState(30);
  const [percorso, naviga] = usePercorso();

  // Al cambio di vista il focus va al contenuto: chi naviga da tastiera o con
  // uno screen reader riparte dalla vista nuova, non da dove era rimasto.
  // Non al primo render: ruberebbe il focus all'apertura della pagina.
  const primoRender = useRef(true);
  useEffect(() => {
    if (primoRender.current) {
      primoRender.current = false;
      return;
    }
    document.getElementById("contenuto")?.focus({ preventScroll: true });
  }, [percorso]);

  const sessione = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
    staleTime: 5 * 60_000,
  });

  const esci = useMutation({
    mutationFn: api.logout,
    onSuccess: () => cache.clear(),
  });

  const vista = VISTE.some((v) => v.percorso === percorso) ? percorso : "/";

  // Un percorso sconosciuto renderizza la Panoramica: anche l'URL deve dirlo,
  // o un refresh ripartirebbe da un indirizzo che non esiste. L'hook sta QUI,
  // prima dei return condizionali: le regole degli hook non perdonano.
  useEffect(() => {
    if (vista !== percorso) window.history.replaceState(null, "", vista);
  }, [vista, percorso]);

  if (sessione.isPending) {
    return (
      <main className="grid min-h-dvh place-items-center p-6">
        <p className="text-testo-55">Verifica della sessione…</p>
      </main>
    );
  }

  if (sessione.error instanceof NonAutenticato || sessione.error) {
    return <Login onEntrato={() => void cache.invalidateQueries()} />;
  }

  return (
    <div className="min-h-dvh lato:grid lato:grid-cols-[236px_minmax(0,1fr)]">
      {/* Salto al contenuto: primo elemento focalizzabile della pagina. */}
      <a
        href="#contenuto"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-sm focus:bg-superficie focus:px-3 focus:py-2 focus:text-accento"
      >
        Salta al contenuto
      </a>

      <Guscio
        vista={vista}
        naviga={naviga}
        giorni={giorni}
        setGiorni={setGiorni}
        esci={() => esci.mutate()}
        uscendo={esci.isPending}
      />

      <main
        id="contenuto"
        tabIndex={-1}
        className="min-w-0 px-4 pb-16 pt-6 outline-none lato:px-12 lato:pt-10"
      >
        <div className="max-w-[1080px]">
          <div key={vista} className="vista">
            {vista === "/" && (
              <div className="space-y-6">
                <HeaderKpi giorni={giorni} />
                <Tendenza giorni={giorni} />
                <div className="grid gap-6 xl:grid-cols-2">
                  <CosaFunziona giorni={giorni} />
                  <Domini giorni={giorni} />
                </div>
              </div>
            )}
            {vista === "/invisibile" && <DoveInvisibile giorni={giorni} />}
            {vista === "/confronti" && <Confronti giorni={giorni} />}
            {vista === "/esplora" && <EsploraProbe giorni={giorni} />}
            {vista === "/sistema" && <StatoSistema />}
            {vista === "/guida" && <Legenda />}
          </div>

          <footer className="mt-14">
            <div className="righello" />
            <p className="mt-4 max-w-[70ch] text-xs text-testo-45">
              Ogni percentuale porta il proprio denominatore e un intervallo di confidenza al
              95%. Dove il campione è troppo piccolo si mostra un tratto, non una cifra.{" "}
              <button
                type="button"
                onClick={() => naviga("/guida")}
                className="cursor-pointer text-accento underline decoration-accento/40 underline-offset-2 hover:decoration-accento"
              >
                Guida alle metriche
              </button>
              .
            </p>
          </footer>
        </div>
      </main>
    </div>
  );
}

function Guscio({
  vista,
  naviga,
  giorni,
  setGiorni,
  esci,
  uscendo,
}: {
  vista: string;
  naviga: (p: string) => void;
  giorni: number;
  setGiorni: (g: number) => void;
  esci: () => void;
  uscendo: boolean;
}) {
  // Il pallino dello scheduler: /health non e' autenticato e costa nulla.
  const salute = useQuery({
    queryKey: ["salute"],
    queryFn: api.salute,
    refetchInterval: 60_000,
    retry: false,
  });

  // Il badge sulla coda di lavoro: stessa query key della Panoramica, quindi
  // in cache condivisa — nessuna richiesta in piu' quando si naviga.
  const kpi = useQuery({ queryKey: ["kpi", giorni], queryFn: () => api.kpi(giorni) });
  const lacune = kpi.data?.lacune_totali ?? 0;
  const scheduler = salute.data?.scheduler === "attivo";
  const prossimo = salute.data?.prossime_esecuzioni?.ciclo_orario;
  const oraCiclo = prossimo
    ? new Date(prossimo).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })
    : null;

  const voci = VISTE.map((v) => {
    const corrente = vista === v.percorso;
    const Icona = v.icona;
    // Link veri, non bottoni: i percorsi esistono davvero (tasto centrale,
    // copia indirizzo, cronologia), il click sinistro resta gestito dalla SPA.
    return (
      <a
        key={v.percorso}
        href={v.percorso}
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
          e.preventDefault();
          naviga(v.percorso);
        }}
        aria-current={corrente ? "page" : undefined}
        className={`relative flex min-h-11 shrink-0 cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm no-underline transition-colors lato:min-h-0 ${
          corrente ? "bg-accento/10 text-accento" : "text-testo-70 hover:bg-testo/6"
        }`}
      >
        <span
          aria-hidden
          className={`absolute -left-0.5 bottom-[9px] top-[9px] w-[2px] rounded-full ${
            corrente ? "bg-accento" : "bg-transparent"
          }`}
        />
        <Icona size={17} className="shrink-0" aria-hidden />
        <span className="whitespace-nowrap">{v.etichetta}</span>
        {v.percorso === "/invisibile" && lacune > 0 && (
          <span className="cifre ml-auto rounded-[6px] bg-neutro-900 px-1.5 py-px text-[11px] text-neutro-300">
            {lacune}
            <span className="sr-only"> articoli mai citati</span>
          </span>
        )}
      </a>
    );
  });

  const indicatoreScheduler = (
    <p className="flex items-center gap-2 text-xs text-testo-55">
      <span
        aria-hidden
        className={`h-1.5 w-1.5 rounded-full ${
          scheduler ? "bg-accento bagliore-punto" : "bg-testo-40"
        }`}
      />
      {salute.isPending
        ? "Verifica dello scheduler…"
        : !salute.data
          ? "Stato non disponibile"
          : scheduler
            ? `Scheduler attivo${oraCiclo ? ` · ciclo ${oraCiclo}` : ""}`
            : "Scheduler spento"}
    </p>
  );

  return (
    <>
      {/* ── Sidebar, da 900px in su ─────────────────────────────────────── */}
      <aside className="relative sticky top-0 hidden h-dvh flex-col px-5 pb-5 pt-7 lato:flex">
        <span aria-hidden className="righello-v absolute bottom-0 right-0 top-0" />
        <Marchio />
        <nav aria-label="Sezioni" className="mt-8 flex flex-col gap-0.5">
          {voci}
        </nav>
        <div className="mt-auto flex flex-col gap-4">
          <div>
            <p className="px-2 text-[10px] uppercase tracking-[0.1em] text-testo-45">Periodo</p>
            <div className="mt-2">
              <SelettorePeriodo giorni={giorni} onChange={setGiorni} />
            </div>
          </div>
          <div className="px-2">{indicatoreScheduler}</div>
          <Bottone onClick={esci} inCorso={uscendo}>
            <SignOut size={16} aria-hidden />
            Esci
          </Bottone>
        </div>
      </aside>

      {/* ── Barra superiore, sotto i 900px ──────────────────────────────── */}
      <header className="lato:hidden">
        <div className="flex items-center justify-between gap-3 px-4 pt-4">
          <Marchio />
          <div className="flex items-center gap-2">
            <SelettorePeriodo giorni={giorni} onChange={setGiorni} />
            <Bottone onClick={esci} inCorso={uscendo}>
              <SignOut size={16} aria-hidden />
              <span className="sr-only">Esci</span>
            </Bottone>
          </div>
        </div>
        <nav
          aria-label="Sezioni"
          className="scorrevole mt-3 flex gap-1 px-4 pb-2"
        >
          {voci}
        </nav>
        <div className="righello" />
      </header>
    </>
  );
}

function Marchio() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <span
        aria-hidden
        className="h-[9px] w-[9px] shrink-0 rounded-[3px] bg-accento bagliore"
      />
      <div className="min-w-0">
        <p className="display whitespace-nowrap text-base leading-tight">Visibilità AI</p>
        <p className="whitespace-nowrap text-[11px] text-testo-45">edunews24.it</p>
      </div>
    </div>
  );
}

function Login({ onEntrato }: { onEntrato: () => void }) {
  const [password, setPassword] = useState("");
  const [errore, setErrore] = useState<string | null>(null);

  const entra = useMutation({
    mutationFn: () => api.login(password),
    onSuccess: onEntrato,
    onError: (e: unknown) =>
      setErrore(e instanceof Error ? e.message : "accesso non riuscito"),
  });

  return (
    <main
      className="grid min-h-dvh place-items-center px-6 py-12"
      style={{
        background:
          "radial-gradient(600px 400px at 50% 30%, color-mix(in srgb, var(--color-accento) 7%, transparent), transparent 70%)",
      }}
    >
      <div className="w-full max-w-[380px]">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden
            className="h-2.5 w-2.5 rounded-[3px] bg-accento bagliore"
          />
          <h1 className="display text-[26px]">Visibilità AI</h1>
        </div>
        <p className="mt-2 text-sm text-testo-55">
          Cruscotto interno di edunews24.it. Accesso riservato.
        </p>

        <form
          className="mt-8 flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            setErrore(null);
            entra.mutate();
          }}
        >
          <div>
            {/* Etichetta visibile, non solo placeholder. */}
            <label htmlFor="password" className="block text-xs text-testo-70">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={errore ? true : undefined}
              aria-describedby={errore ? "errore-login" : undefined}
              className="mt-1.5 min-h-11 w-full rounded-md border border-divisore bg-superficie px-3 text-base caret-accento hover:border-testo-45 focus-visible:border-accento sm:min-h-9"
            />
            {errore && (
              <p id="errore-login" role="alert" className="mt-2 text-sm text-accento-300">
                {errore === "password non valida"
                  ? "Password non valida. Riprova."
                  : errore.includes("tentativi")
                    ? "Troppi tentativi falliti: riprova fra un quarto d'ora."
                    : errore}
              </p>
            )}
          </div>

          <Bottone type="submit" variante="primario" inCorso={entra.isPending}>
            Entra
          </Bottone>
        </form>

        <p className="mt-7 text-xs leading-relaxed text-testo-45">
          Il cookie di sessione è <code className="font-mono">Secure</code>: in HTTP puro il
          login non persiste. Servire sempre dietro TLS.
        </p>
      </div>
    </main>
  );
}
