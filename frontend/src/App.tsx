import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useState } from "react";

import { Bottone, SelettorePeriodo } from "./components/base";
import { NonAutenticato, api } from "./lib/api";
import { Categorie, Domini, Provider } from "./sezioni/confronti";
import { CosaFunziona, DoveInvisibile } from "./sezioni/operativo";
import { EsploraProbe } from "./sezioni/esplora";
import { HeaderKpi, Tendenza } from "./sezioni/panoramica";
import { StatoSistema } from "./sezioni/sistema";

export default function App() {
  const cache = useQueryClient();
  const [giorni, setGiorni] = useState(30);

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

  if (sessione.isPending) {
    return (
      <main className="grid min-h-dvh place-items-center p-6">
        <p className="text-grafite">Verifica della sessione…</p>
      </main>
    );
  }

  if (sessione.error instanceof NonAutenticato || sessione.error) {
    return <Login onEntrato={() => void cache.invalidateQueries()} />;
  }

  return (
    <div className="min-h-dvh">
      {/* Salto al contenuto: primo elemento focalizzabile della pagina. */}
      <a
        href="#contenuto"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-[var(--radius-controllo)] focus:bg-timbro focus:px-3 focus:py-2 focus:text-foglio"
      >
        Salta al contenuto
      </a>

      <header className="border-b border-grafite-tenue bg-foglio">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <h1 className="display text-lg font-bold">Visibilità AI</h1>
            <p className="text-xs text-grafite">
              Quanto i motori di risposta citano edunews24.it. È una misura: non aumenta le
              citazioni.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <SelettorePeriodo giorni={giorni} onChange={setGiorni} />
            <Bottone onClick={() => esci.mutate()} inCorso={esci.isPending}>
              <LogOut size={16} aria-hidden />
              Esci
            </Bottone>
          </div>
        </div>
      </header>

      <main id="contenuto" className="mx-auto max-w-7xl space-y-4 px-4 py-5">
        <HeaderKpi giorni={giorni} />

        {/* Le due sezioni con peso visivo maggiore vengono prima. */}
        <DoveInvisibile giorni={giorni} />
        <Tendenza giorni={giorni} />

        <div className="grid gap-4 xl:grid-cols-2">
          <CosaFunziona giorni={giorni} />
          <Domini giorni={giorni} />
        </div>

        <Provider giorni={giorni} />
        <Categorie giorni={giorni} />
        <EsploraProbe giorni={giorni} />
        <StatoSistema />

        <footer className="pb-6 pt-2 text-xs text-grafite">
          <p>
            Ogni percentuale porta il proprio denominatore e il proprio intervallo di confidenza
            al 95%. Dove il campione è troppo piccolo si mostra un tratto, non una cifra: un
            numero calcolato su tre casi non è una misura.
          </p>
        </footer>
      </main>
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
    <main className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <h1 className="display text-2xl font-bold">Visibilità AI</h1>
        <p className="mt-1 text-sm text-grafite">
          Cruscotto interno di edunews24.it. Accesso riservato all'amministratore.
        </p>

        <form
          className="mt-6 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            setErrore(null);
            entra.mutate();
          }}
        >
          <div>
            {/* Etichetta visibile, non solo placeholder. */}
            <label htmlFor="password" className="block text-sm font-medium">
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
              className="mt-1 min-h-11 w-full rounded-[var(--radius-controllo)] border border-grafite-tenue bg-foglio px-3 text-base"
            />
            {errore && (
              <p id="errore-login" role="alert" className="mt-1.5 text-sm text-sigillo">
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

        <p className="mt-6 text-xs text-grafite">
          Se l'accesso non va a buon fine anche con la password giusta, il servizio potrebbe
          essere raggiunto in HTTP: il cookie di sessione è <code className="font-mono">Secure</code>{" "}
          e il browser non lo invia su connessioni non cifrate.
        </p>
      </div>
    </main>
  );
}
