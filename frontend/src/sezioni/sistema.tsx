/** Sezione 8 — Stato del sistema. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { useState } from "react";

import { Bottone, Card, Distintivo, Scheletro, StatoErrore, StatoVuoto } from "../components/base";
import { api } from "../lib/api";
import { ETICHETTA_STATO, dataOra, euro, intero } from "../lib/format";

export function StatoSistema() {
  const cache = useQueryClient();
  const [messaggio, setMessaggio] = useState<string | null>(null);

  const salute = useQuery({ queryKey: ["salute"], queryFn: api.salute, refetchInterval: 60_000 });
  const costi = useQuery({ queryKey: ["costi"], queryFn: api.costi });
  const run = useQuery({ queryKey: ["run"], queryFn: () => api.run(15) });

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
    <Card
      id="sistema"
      titolo="Stato del sistema"
      descrizione="Cicli eseguiti, prossime esecuzioni e budget residuo."
      azioni={
        <Bottone
          variante="primario"
          onClick={() => esegui.mutate()}
          inCorso={esegui.isPending}
          disabilitato={superato}
        >
          <Play size={16} aria-hidden />
          Esegui un ciclo
        </Bottone>
      }
    >
      {/* Banner del budget: `sigillo` compare solo qui e sugli errori veri. */}
      {superato && (
        <div
          role="alert"
          className="mb-4 rounded-[var(--radius-controllo)] bg-sigillo-tenue px-4 py-3"
        >
          <p className="font-medium text-sigillo">Budget superato: i cicli orari sono sospesi.</p>
          <p className="mt-1 text-sm text-grafite">
            {budget?.motivo}. I cicli riprendono da soli quando la finestra si azzera, oppure
            alza <code className="font-mono">MAX_DAILY_SPEND_EUR</code> nel .env e riavvia.
          </p>
        </div>
      )}

      {messaggio && (
        <p
          aria-live="polite"
          className="mb-4 rounded-[var(--radius-controllo)] bg-timbro-tenue px-3 py-2 text-sm"
        >
          {messaggio}
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {/* Servizio */}
        <div>
          <h3 className="text-sm font-medium">Servizio</h3>
          {salute.error ? (
            <StatoErrore errore={salute.error} riprova={() => void salute.refetch()} />
          ) : salute.isPending ? (
            <Scheletro righe={2} />
          ) : (
            <dl className="mt-2 space-y-1.5 text-sm">
              <Riga
                etichetta="Database"
                valore={<Distintivo tinta={salute.data!.database === "ok" ? "alloro" : "sigillo"}>{salute.data!.database}</Distintivo>}
              />
              <Riga
                etichetta="Scheduler"
                valore={
                  <Distintivo tinta={salute.data!.scheduler === "attivo" ? "alloro" : "ottone"}>
                    {salute.data!.scheduler}
                  </Distintivo>
                }
              />
              {salute.data!.scheduler !== "attivo" && (
                <p className="text-sm text-grafite">
                  Nessun ciclo automatico partirà. Imposta{" "}
                  <code className="font-mono">SCHEDULER_ENABLED=true</code> e riavvia il container.
                </p>
              )}
              {Object.entries(salute.data!.prossime_esecuzioni).map(([id, quando]) => (
                <Riga
                  key={id}
                  etichetta={id === "ciclo_orario" ? "Prossimo ciclo" : "Prossima manutenzione"}
                  valore={
                    <span className="cifre">{quando ? dataOra(quando) : "non pianificata"}</span>
                  }
                />
              ))}
            </dl>
          )}
        </div>

        {/* Budget */}
        <div>
          <h3 className="text-sm font-medium">Budget</h3>
          {costi.error ? (
            <StatoErrore errore={costi.error} riprova={() => void costi.refetch()} />
          ) : costi.isPending ? (
            <Scheletro righe={2} />
          ) : (
            <div className="mt-2 space-y-3">
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
      </div>

      {/* Cicli */}
      <div className="mt-5">
        <h3 className="text-sm font-medium">Ultimi cicli</h3>
        {run.error ? (
          <StatoErrore errore={run.error} riprova={() => void run.refetch()} />
        ) : run.isPending ? (
          <div className="mt-2">
            <Scheletro righe={4} />
          </div>
        ) : !run.data?.length ? (
          <div className="mt-2">
            <StatoVuoto
              titolo="Nessun ciclo ancora eseguito."
              cosaFare="Il cron gira al minuto 7 di ogni ora. Con «Esegui un ciclo» ne parte uno subito."
            />
          </div>
        ) : (
          <div className="scorrevole -mx-4 mt-2 px-4">
            <table className="w-full min-w-[34rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-grafite-tenue text-left">
                  <th scope="col" className="py-2 pr-3 font-medium">Avvio</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Tipo</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Esito</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Probe</th>
                  <th scope="col" className="py-2 font-medium">Costo</th>
                </tr>
              </thead>
              <tbody>
                {run.data.map((r) => (
                  <tr key={r.id} className="border-b border-grafite-tenue align-top">
                    <td className="cifre whitespace-nowrap py-2.5 pr-3 text-xs">
                      {dataOra(r.started_at)}
                    </td>
                    <td className="py-2.5 pr-3 text-xs text-grafite">
                      {r.kind === "hourly" ? "orario" : r.kind === "manual" ? "manuale" : r.kind}
                    </td>
                    <td className="py-2.5 pr-3">
                      <Distintivo
                        tinta={
                          r.status === "ok"
                            ? "alloro"
                            : r.status === "partial"
                              ? "ottone"
                              : r.status === "skipped_budget"
                                ? "grafite"
                                : "sigillo"
                        }
                      >
                        {ETICHETTA_STATO[r.status] ?? r.status}
                      </Distintivo>
                      {r.notes && (
                        <span className="mt-0.5 block max-w-xs text-xs text-grafite">
                          {r.notes}
                        </span>
                      )}
                    </td>
                    <td className="cifre py-2.5 pr-3 text-xs">
                      {intero(r.completed)}/{intero(r.planned)}
                      {r.failed > 0 && (
                        <span className="text-sigillo"> · {intero(r.failed)} falliti</span>
                      )}
                    </td>
                    <td className="cifre py-2.5 text-xs">{euro(r.costo_eur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}

function Riga({ etichetta, valore }: { etichetta: string; valore: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-grafite">{etichetta}</dt>
      <dd>{valore}</dd>
    </div>
  );
}

function Barra({ etichetta, speso, tetto }: { etichetta: string; speso: number; tetto: number }) {
  const quota = tetto > 0 ? Math.min(1, speso / tetto) : 0;
  const allarme = quota >= 0.8;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="text-grafite">{etichetta}</span>
        <span className="cifre">
          {euro(speso)} <span className="text-xs text-grafite">/ {euro(tetto)}</span>
        </span>
      </div>
      <div
        className="mt-1 h-2 w-full overflow-hidden rounded-full bg-grafite-tenue"
        role="progressbar"
        aria-valuenow={Math.round(quota * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Budget ${etichetta.toLowerCase()}: ${euro(speso)} su ${euro(tetto)}`}
      >
        <div
          className={`h-full rounded-full transition-[width] duration-200 ${
            allarme ? "bg-sigillo" : "bg-alloro"
          }`}
          style={{ width: `${quota * 100}%` }}
        />
      </div>
    </div>
  );
}
