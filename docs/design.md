# Il design «Nocturne»

> Il linguaggio visivo della dashboard dalla riprogettazione dell'agosto 2026.
> Fonte di verita': il design system Nocturne del progetto Claude Design
> «Redesign dashboard Nocturne» (i due file `Dashboard Nocturne*.dc.html` e il
> DS in `_ds/nocturne-*/styles.css`). Questo documento e' la trascrizione
> operativa: cosa vale nel codice e perche'.

---

## 1. Di cosa parla questa interfaccia

Non di analytics. Di **assenza**.

Un giornale locale che compete con le testate grandi non verra' citato spesso:
il dato dominante di questa dashboard e' lo zero. La persona che la apre — una
sola, l'amministratore — la apre per rispondere a una domanda operativa: **su
cosa sono invisibile e cosa devo scrivere.** Le due regole che ne discendono
sopravvivono intatte al cambio di pelle:

1. **L'incertezza e' parte del dato.** Ogni percentuale porta denominatore e
   intervallo di confidenza al 95%; sotto i 10 probe si mostra un trattino,
   fra 10 e 30 il valore e' sbiadito. Prima erano bande grafiche, ora sono la
   riga di conto sotto ogni cifra: la resa cambia, la regola no.
2. **La sezione operativa e' «Dove sei invisibile».** Ha una vista dedicata,
   ordinata per costo di rimedio, con il drill-down su chi e' citato al posto
   nostro.

---

## 2. Il carattere di Nocturne

Un'interfaccia quieta e compatta: fondo blu-grigio quasi neutro, Inter a peso
medio, raggi morbidi da 8 px, e un solo accento — il blurple `--color-accento`
— usato **come linea, contorno e bagliore, mai come campitura**. Il contrasto
viene dalle rampe tonali, non dalla saturazione.

- **La firma: i righelli che sfumano.** Le linee di separazione non si fermano
  di netto: sfumano a trasparente alle estremita' (48 px per lato; `@utility
  righello` / `righello-v`). Righe di tabella, divisori di sezione, il bordo
  della sidebar. I contorni dei box e i marchi corti restano solidi.
- **Bottone primario = contorno accento.** Mai riempito: l'accento che riempie
  e' fuori dal linguaggio. Gli unici riempimenti d'accento sono i passi scuri
  delle rampe (tag, tinte di hover).
- **Bagliori.** Il pallino del brand, l'indicatore dello scheduler, la
  sottolineatura del KPI e le barre del budget portano un `box-shadow`
  dell'accento (`--shadow-bagliore*`), piu' intenso sul fondo scuro che su
  quello chiaro.
- **Gerarchia = dimensione e spazio.** Un solo font (Inter, self-hosted via
  fontsource); i titoli non superano il peso 500. Le cifre sono sempre
  tabulari (`.cifre`).

## 3. I token (frontend/src/index.css)

Dark-first: `@theme` porta la variante scura canonica, la chiara e' un
override su `:root` dentro `@media (prefers-color-scheme: light)` — mai un
`@theme` annidato, che Tailwind v4 ignora in silenzio. Regola d'oro: i token
che contengono `var()` (smorzati, bagliori) si risolvono su `:root`, quindi un
eventuale futuro toggle manuale dovra' mettere la classe su `<html>`.

| Ruolo | Dark | Light |
|---|---|---|
| `--color-fondo` | `#161826` | `#eff1f9` |
| `--color-superficie` | `#232532` | `#fcfcfe` |
| `--color-testo` | `#e9e9ed` | `#232532` |
| `--color-accento` | `#9184d9` | `#796cbf` |
| `--color-pervinca` | `#a7a1db` | `#7972a9` |

- **Rampe 100–900** per `neutro`, `accento`, `pervinca` (il secondo accento
  del DS: stessa tinta, meno croma — nome proprio per non confondere le
  classi). I passi sono relativi al fondo: il passo N chiaro corrisponde al
  passo 1000−N scuro, coi 900 ritoccati a mano dal design.
- **Testo smorzato pre-mixato**: `--color-testo-70/60/55/45/40` e
  `--color-divisore` via `color-mix`, cosi' esistono le utility
  (`text-testo-55`, `border-divisore`) e i `var()` per Recharts.
- **Serie del grafico**: `--color-serie-1…4`, contratto separato dalla
  tavolozza UI, con valori per tema (piu' chiare sul fondo scuro). Consumate
  solo da `SERIE_PROVIDER` in `lib/format.ts`, insieme ai tratteggi che
  tengono le serie leggibili in scala di grigi.
- **Niente rosso/verde.** Tavolozza mono-accento per scelta del design: gli
  stati vivono sulle rampe. Il vocabolario e' quello del `Distintivo`:
  `accento` (segnale positivo pieno), `neutro` (esito normale), `pervinca`
  (stati a meta': parziale, recuperato, senza ricerca), `muto` (contorno
  smorzato dei salti), `allarme` (contorno accento dei guasti), `contorno`
  (contorno accento dei marcatori positivi). Gli errori si rendono con
  `accento-300` + icona Warning + `role="alert"`: e' il contesto a dire che
  e' un problema, non un colore semantico.

## 4. Il guscio

Sidebar sticky da 236 px con il righello verticale sfumato; sei viste su
percorsi reali (`/`, `/invisibile`, `/confronti`, `/esplora`, `/sistema`,
`/guida`) servite dal catch-all della SPA, mini-router in `App.tsx` (history
API + `popstate`, niente libreria). Al cambio di vista: scroll in cima e focus
sul contenuto. In sidebar: periodo globale 7/30/90 (controllo segmentato),
badge con il conteggio delle lacune (da `/api/kpi`), indicatore vivo dello
scheduler (da `/api/health`), Esci. Sotto i 900 px (`--breakpoint-lato`) la
sidebar diventa una barra superiore con la nav scorrevole.

Le spiegazioni delle metriche vivono SOLO nella vista «Guida alle metriche»
(scelta esplicita dell'utente): il glossario resta in `lib/glossario.ts`, i
pannelli per-card non esistono piu'.

## 5. Le regole che il restyling non puo' toccare

Sono le regole di correttezza del sistema, e ogni futura modifica visiva deve
lasciarle intatte:

1. i probe falliti e quelli senza ricerca **non entrano nei denominatori**;
2. `retrieval` e `memory` **non si mescolano mai** (la colonna Memoria e'
   separata da un filetto verticale e dichiarata «metrica diversa»);
3. ogni tasso viaggia col suo denominatore, **mai una percentuale nuda**;
4. nel grafico i giorni sotto soglia sono `null` e la linea **si interrompe**
   (`connectNulls={false}`): un segmento sopra un giorno mai misurato e' un
   numero inventato;
5. il delta del KPI mostra la freccia **solo se significativo** (gli
   intervalli dei due periodi non si sovrappongono);
6. la banda d'incertezza nel grafico si disegna solo con un provider
   selezionato: con piu' serie sarebbe illeggibile.

## 6. Accessibilita'

Focus visibile ovunque (`:focus-visible` 2 px accento, offset 2); bersagli
tocco da 44 px su mobile (`min-h-11` che scende con `sm:`); tabelle che
scorrono in orizzontale dentro `.scorrevole` invece di rompere il layout;
`prefers-reduced-motion` azzera le animazioni (le uniche: l'ingresso di vista
da 200 ms e le transizioni di colore); stati vuoti che dicono cosa fare;
`aria-live` sui messaggi, `role="alert"` sugli errori; il contrasto dei testi
smorzati principali resta sopra 4.5:1 su entrambi i fondi.
