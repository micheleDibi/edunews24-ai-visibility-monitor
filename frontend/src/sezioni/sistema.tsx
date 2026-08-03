/** Vista «Stato del sistema»: cicli, prossime esecuzioni e budget residuo. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Database, Play, Pulse, Wrench } from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { useState } from "react";

import { Bottone, Distintivo, Scheletro, StatoErrore, StatoVuoto } from "../components/base";
import { api } from "../lib/api";
import { ETICHETTA_STATO, dataOra, euro, intero } from "../lib/format";

export function StatoSistema() {
  const cache = useQueryClient();
  const [messaggio, setMessaggio] = useState<string | null>(null);

  const salute = useQuery({ queryKey: ["salute"], queryFn: api.salute, refetchInterval: 60_000 });
  const costi = useQuery({ queryKey: ["costi"], queryFn: api.costi });
  // 25 e non 15: il ciclo e' orario, quindi servono almeno 24 righe perche' la
  // tabella copra una giornata intera.
  const run = useQuery({ queryKey: ["run"], queryFn: () => api.run(25) });

  const esegui = useMutation({
    mutationFn: () => api.eseguiOra(5),
    onSuccess: (d) => {
      setMessaggio(d.messaggio);
      // Il ciclo dura minuti: si ricarica l'elenco dopo qualche secondo, non
      // subito, perche' subito non c'e' ancora niente da vedere.
      setTimeout(() => void cache.invalidateQueries({ queryKey: ["run"] }), 4000);
    },
    onError: (e: unknown) =>
      setMessaggio(e instanceof Error ? e.message : "impossibile avviare il ciclo"),
  });

  const budget = costi.data;
  const superato = budget?.budget_superato ?? false;

  return (
    <section aria-labelledby="sistema-titolo">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.1em] text-accento">Operazioni</p>
          <h1 id="sistema-titolo" className="display mt-1.5 text-xl">
            Stato del sistema
          </h1>
          <p className="mt-1.5 max-w-[60ch] text-sm text-testo-55">
            Cicli, prossime esecuzioni e budget residuo.
          </p>
        </div>
        <Bottone
          variante="primario"
          onClick={() => esegui.mutate()}
          inCorso={esegui.isPending}
          disabilitato={superato}
        >
          <Play size={15} aria-hidden />
          Esegui un ciclo
        </Bottone>
      </div>

      {/* La regione live esiste SEMPRE: montarla insieme al messaggio fa
          perdere l'annuncio agli screen reader, che ascoltano i cambiamenti
          di regioni gia' presenti. */}
      <p
        aria-live="polite"
        className={
          messaggio
            ? "mt-5 rounded-md bg-accento-900 px-4 py-2.5 text-sm text-accento-200"
            : "sr-only"
        }
      >
        {messaggio}
      </p>

      {superato && (
        <div role="alert" className="mt-5 rounded-md bg-accento-900 px-4 py-3">
          <p className="font-medium text-accento-200">
            Budget superato: i cicli orari sono sospesi.
          </p>
          <p className="mt-1 text-sm text-testo-55">
            {budget?.motivo}. I cicli riprendono da soli quando la finestra si azzera, oppure
            alza <code className="font-mono">MAX_DAILY_SPEND_EUR</code> nel .env e riavvia.
          </p>
        </div>
      )}

      {/* ── Le quattro tessere di stato ─────────────────────────────────── */}
      {salute.error ? (
        <div className="mt-7">
          <StatoErrore errore={salute.error} riprova={() => void salute.refetch()} />
        </div>
      ) : (
        <div className="mt-7 grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-6">
          <Tessera
            icona={Database}
            etichetta="Database"
            valore={salute.isPending ? null : (salute.data?.database ?? "—")}
            inAccento={false}
          />
          <Tessera
            icona={Pulse}
            etichetta="Scheduler"
            valore={salute.isPending ? null : (salute.data?.scheduler ?? "—")}
            inAccento={salute.data?.scheduler === "attivo"}
          />
          <Tessera
            icona={Clock}
            etichetta="Prossimo ciclo"
            valore={
              salute.isPending
                ? null
                : quando(salute.data?.prossime_esecuzioni?.ciclo_orario)
            }
            inAccento={false}
          />
          <Tessera
            icona={Wrench}
            etichetta="Manutenzione"
            valore={
              salute.isPending
                ? null
                : quando(salute.data?.prossime_esecuzioni?.manutenzione_notturna)
            }
            inAccento={false}
          />
        </div>
      )}
      {salute.data && salute.data.scheduler !== "attivo" && (
        <p className="mt-3 text-sm text-testo-55">
          Nessun ciclo automatico partirà. Imposta{" "}
          <code className="font-mono">SCHEDULER_ENABLED=true</code> e riavvia il container.
        </p>
      )}

      {/* ── Budget ──────────────────────────────────────────────────────── */}
      <div className="mt-6 rounded-md bg-superficie p-7">
        <h2 className="display text-md">Budget</h2>
        {costi.error ? (
          <div className="mt-4">
            <StatoErrore errore={costi.error} riprova={() => void costi.refetch()} />
          </div>
        ) : costi.isPending ? (
          <div className="mt-4">
            <Scheletro righe={2} />
          </div>
        ) : (
          <div className="mt-5 grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-8">
            <Barra
              etichetta="Oggi"
              speso={Number(budget!.giorno_eur)}
              tetto={Number(budget!.tetto_giorno_eur)}
            />
            <Barra
              etichetta="Questo mese"
              speso={Number(budget!.mese_eur)}
              tetto={Number(budget!.tetto_mese_eur)}
            />
          </div>
        )}
      </div>

      {/* ── Ultimi cicli ────────────────────────────────────────────────── */}
      <div className="mt-6 rounded-md bg-superficie p-7">
        <h2 className="display text-md">Ultimi cicli</h2>
        <p className="mt-1 max-w-[65ch] text-sm text-testo-55">
          Uno all'ora, al minuto 7, tutte le 24: ogni ora lascia una riga, anche quando il
          ciclo non parte — eseguita, saltata con il motivo, o conteggiata come «servizio
          fermo» al riavvio. Un'ora del tutto assente indica un fermo ancora in corso.
        </p>
        {run.error ? (
          <div className="mt-4">
            <StatoErrore errore={run.error} riprova={() => void run.refetch()} />
          </div>
        ) : run.isPending ? (
          <div className="mt-4">
            <Scheletro righe={4} />
          </div>
        ) : !run.data?.length ? (
          <div className="mt-4">
            <StatoVuoto
              titolo="Nessun ciclo ancora eseguito."
              cosaFare="Il cron gira al minuto 7 di ogni ora. Con «Esegui un ciclo» ne parte uno subito."
            />
          </div>
        ) : (
          <div className="scorrevole -mx-4 mt-4 px-4">
            <table className="tabella min-w-[40rem]">
              <thead>
                <tr>
                  <th scope="col">Avvio</th>
                  <th scope="col">Tipo</th>
                  <th scope="col">Esito</th>
                  <th scope="col">Probe</th>
                  <th scope="col">Costo</th>
                </tr>
              </thead>
              <tbody>
                {run.data.map((r) => (
                  <tr key={r.id}>
                    <td className="cifre whitespace-nowrap text-xs text-testo-70">
                      {dataOra(r.started_at)}
                    </td>
                    <td className="text-xs text-testo-55">
                      {r.kind === "hourly" ? "orario" : r.kind === "manual" ? "manuale" : r.kind}
                    </td>
                    <td>
                      <Distintivo
                        tinta={
                          r.status === "ok"
                            ? "neutro"
                            : r.status === "partial"
                              ? "pervinca"
                              : r.status === "running"
                                ? "accento"
                                : r.status.startsWith("skipped")
                                  ? "muto"
                                  : "allarme"
                        }
                      >
                        {ETICHETTA_STATO[r.status] ?? r.status}
                      </Distintivo>
                      {r.notes && (
                        <span className="mt-1 block max-w-xs text-xs text-testo-45">
                          {r.notes}
                        </span>
                      )}
                    </td>
                    <td className="cifre text-xs">
                      {intero(r.completed)}/{intero(r.planned)}
                      {r.failed > 0 && (
                        <span className="text-accento-300"> · {intero(r.failed)} falliti</span>
                      )}
                    </td>
                    <td className="cifre text-xs">{euro(r.costo_eur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

/** «oggi, 15:07» se e' oggi, altrimenti data e ora complete. */
function quando(iso: string | null | undefined): string {
  if (!iso) return "non pianificata";
  const d = new Date(iso);
  const oggi = new Date();
  const ora = d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === oggi.toDateString() ? `oggi, ${ora}` : dataOra(iso);
}

function Tessera({
  icona: Icona,
  etichetta,
  valore,
  inAccento,
}: {
  icona: Icon;
  etichetta: string;
  valore: string | null;
  inAccento: boolean;
}) {
  return (
    <div className="rounded-md bg-superficie p-5">
      <p className="flex items-center gap-2 text-[11px] uppercase tracking-[0.1em] text-testo-55">
        <Icona size={14} aria-hidden />
        {etichetta}
      </p>
      {valore === null ? (
        <div className="mt-2.5">
          <Scheletro righe={1} />
        </div>
      ) : (
        <p
          className={`cifre mt-2.5 whitespace-nowrap text-[17px] font-medium ${
            inAccento ? "text-accento" : "text-testo"
          }`}
        >
          {valore}
        </p>
      )}
    </div>
  );
}

function Barra({ etichetta, speso, tetto }: { etichetta: string; speso: number; tetto: number }) {
  const quota = tetto > 0 ? Math.min(1, speso / tetto) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="text-testo-55">{etichetta}</span>
        <span className="cifre whitespace-nowrap">
          {euro(speso)} <span className="text-xs text-testo-45">/ {euro(tetto)}</span>
        </span>
      </div>
      <div
        className="relative mt-2 h-[5px] overflow-hidden rounded-[3px] bg-neutro-900"
        role="progressbar"
        aria-valuenow={Math.round(quota * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Budget ${etichetta.toLowerCase()}: ${euro(speso)} su ${euro(tetto)}`}
      >
        <div
          // `accento` base, non il passo 600: sul fondo chiaro il 600 chiaro
          // (#b5abfc) scendeva a 1.8:1 sulla traccia — sotto il 3:1 dei
          // componenti d'interfaccia.
          className="absolute bottom-0 left-0 top-0 rounded-[3px] bg-accento bagliore-barra transition-[width] duration-200"
          style={{ width: `${quota * 100}%` }}
        />
      </div>
    </div>
  );
}
