# Piano di design

> Scritto prima di qualunque componente, come previsto dalla Fase 6. Contiene i
> token, la scala tipografica, l'elemento firma, e — in fondo — la rilettura
> critica che scarta le scelte che si farebbero per «una dashboard qualunque».

---

## 1. Di cosa parla questa interfaccia

Non di analytics. Di **assenza**.

Un giornale locale che compete con le testate grandi non verra' citato spesso:
il dato dominante di questa dashboard sara' lo zero. E la persona che la apre —
una sola, l'amministratore — non la apre per compiacersi di un numero, la apre
per rispondere a una domanda operativa: **su cosa sono invisibile e cosa devo
scrivere.**

Da qui due conseguenze che guidano ogni scelta successiva:

1. **L'incertezza e' parte del dato, non una postilla.** Con 200 query al giorno
   divise su quattro provider e dodici categorie, molte celle avranno
   denominatori a una cifra. Una dashboard che stampa «2,3%» su tre casi non
   informa: mente con precisione. L'intervallo di confidenza deve essere
   *visibile*, non nascosto in un tooltip.
2. **La sezione operativa e' «dove sei invisibile».** E' quella che si guarda,
   e va progettata come uno strumento di lavoro: la piu' usabile, non la piu'
   decorata.

---

## 2. I sei colori

Nomi propri, italiani, tratti dal mondo della scuola e dei documenti — non da
una tavolozza di dashboard.

| Nome | Hex | Ruolo |
|---|---|---|
| **lavagna** | `#16211F` | Inchiostro. Testo primario e superfici scure. Un verde-ardesia molto scuro, non nero puro: il nero puro su fondo chiaro affatica, e questo e' uno schermo che si guarda a lungo. |
| **gesso** | `#F1F2EE` | Fondo pagina. Bianco sporco con cast **verde-grigio**, non giallo. Deliberatamente *non* crema (vedi §7). |
| **timbro** | `#5E3B96` | **Presenza**: il giornale e' citato. Viola d'inchiostro, il colore dei timbri sui documenti italiani. Serie del provider OpenAI. |
| **alloro** | `#3F6B4A` | Verde alloro, la corona della laurea. Esiti positivi e serie Perplexity. |
| **ottone** | `#836320` | Avvisi che non sono errori (costo stimato, dato parziale). Serie Anthropic. |
| **grafite** | `#6E7673` | **Assenza**: altri domini, testo secondario, tutto cio' che occupa il posto quando il giornale non c'e'. |

Fuori tavolozza, dichiarato a parte perche' **semantico e mai decorativo**:

| Nome | Hex | Ruolo |
|---|---|---|
| **sigillo** | `#A62A3C` | Solo errori veri e budget superato. Non compare da nessun'altra parte, cosi' quando compare significa qualcosa. |
| **ardesia** | `#3A5670` | Serie Gemini, solo se abilitato. Normalmente non usato. |

### Contrasto verificato

Rapporti **calcolati**, non stimati (su `gesso` / su `foglio`):

| | chiaro | scuro |
|---|---|---|
| `lavagna` | 14.69 / 16.52 | 15.29 / 13.60 |
| `timbro` | 7.35 / 8.26 | 6.85 / 6.09 |
| `alloro` | 5.47 / 6.15 | 7.78 / 6.91 |
| `ottone` | 4.95 / 5.57 | 8.55 / 7.61 |
| `sigillo` | 6.19 / 6.96 | 6.97 / 6.20 |
| `grafite` | **4.15** / 4.66 | 6.78 / 6.03 |

Tutti superano 4.5:1 tranne `grafite`, che sta a 4.15:1 sul tema chiaro: si usa
**solo** per testo secondario e per riempimenti, mai per testo primario.

`ottone` era inizialmente `#8A6A1F`, che misurava 4.49:1 — un centesimo sotto la
soglia. Scurito a `#836320`. E' il tipo di dettaglio che si scopre solo
calcolando, non guardando.

### Il colore non porta mai da solo un significato

Regola dalla ricerca UX (`color-not-only`, `pattern-texture`), qui non
negoziabile perche' l'intera dashboard e' un confronto fra serie:

* le **serie dei provider** si distinguono per **tratteggio** oltre che per
  colore — continuo, tratteggiato, punteggiato, tratto-punto — cosi' restano
  leggibili in scala di grigi e per un daltonico;
* le celle della griglia categorie portano **il numero**, non solo l'intensita';
* «citato / non citato» ha sempre un'etichetta o un'icona, non solo la tinta.

---

## 3. Le due famiglie tipografiche

Due ruoli netti, come richiesto.

### Display — **Bricolage Grotesque** (variabile, 400–800)
Numeri e titoli. E' un grottesco con carattere: proporzioni leggermente
irregolari, tono editoriale, e cifre che reggono bene a corpo grande. Serve al
KPI principale, che deve avere il peso visivo maggiore.

### Dati — **IBM Plex Sans** (400/500/600)
Tabelle, etichette, corpo del testo. Voce neutra che non compete con i numeri, e
soprattutto **cifre tabulari vere**: in una colonna di percentuali le cifre
devono incolonnarsi, altrimenti l'occhio non puo' confrontarle.

```css
font-variant-numeric: tabular-nums;
```
Applicato a ogni cella numerica. Non e' un dettaglio: senza, ogni tabella
"balla" e i confronti verticali diventano faticosi.

### Monospazio — **IBM Plex Mono**
Solo per il `raw_response` nel dettaglio probe e per gli slug. Stessa famiglia
di IBM Plex Sans, quindi coerente senza aggiungere una terza voce.

```css
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
```

---

## 4. Scala tipografica

Passo non uniforme: stretto in basso (dove vivono i dati densi, e servono
gradini fini) e ampio in alto (dove servono salti netti).

| Token | px | Uso |
|---|---|---|
| `--testo-xs` | 12 | Denominatori, note sotto un numero, unita' |
| `--testo-sm` | 13 | Celle di tabella, etichette |
| `--testo-base` | 15 | Corpo. **Su mobile diventa 16px** per evitare lo zoom automatico di iOS |
| `--testo-md` | 18 | Titoli di card |
| `--testo-lg` | 22 | Titoli di sezione |
| `--testo-xl` | 30 | Numeri secondari dei KPI |
| `--testo-2xl` | 44 | — |
| `--testo-cifra` | `clamp(3rem, 10vw, 4.5rem)` | **Il citation rate.** Un solo numero in tutta l'interfaccia ha questo corpo |

Interlinea 1.5 sul corpo, 1.1 sui numeri display (le cifre grandi con interlinea
larga si slegano).

Spaziatura su multipli di 4px. Densita' da dashboard: padding delle celle 8/12px,
non 16/24 — lo spazio serve ai dati.

---

## 5. L'elemento firma: **la banda d'incertezza**

Ogni tasso in questa interfaccia si disegna cosi':

```
        27%          ← cifra, Bricolage, tabular
   ├────●───────┤    ← banda: intervallo di Wilson, in scala
     18/66           ← numeratore/denominatore, sempre
```

La banda e' **in scala reale** sull'asse 0–100%: un intervallo largo *sembra*
largo. Il pallino e' la stima puntuale.

Tre taglie, stesso oggetto:

* **grande** — sotto il KPI principale, larga quanto la card;
* **compatta** — dentro le celle di tabella e della griglia, 48px, senza cifre;
* **banda** — nel grafico di tendenza, come area attorno alla linea (il tipo
  «line with confidence band» che la ricerca sui grafici indica per comunicare
  incertezza).

E quando il campione non basta:

```
         —           ← nessuna cifra: non si stampa un numero che non c'e'
   ├///////////┤     ← banda tratteggiata a tutta larghezza
      2/3            ← i conteggi si mostrano comunque
```

**Perche' questo e' l'elemento firma.** Non e' un ornamento cercato a
posteriori: e' il modello dei dati reso visibile. L'API restituisce
`ic_basso`/`ic_alto`/`affidabile` su ogni tasso proprio perche' questa misura ha
un'incertezza che conta, e l'interfaccia la mostra invece di arrotondarla via.
Nessuna dashboard di analytics lo fa — mostrano tutte un numero nudo e una
freccia verde. Questa mostra quanto sa e quanto non sa, e si riconosce da
questo.

---

## 6. Le otto sezioni

| # | Sezione | Forma | Stato vuoto dice… |
|---|---|---|---|
| 1 | **Header KPI** | Il citation rate a `--testo-cifra` con banda grande. Attorno, tre numeri secondari (mention, target hit, costo del mese) a `--testo-xl`. Il delta compare **solo se `significativo`**: se gli intervalli si sovrappongono non e' un miglioramento, e' rumore | «Nessun probe negli ultimi 30 giorni: il ciclo orario non ha ancora girato» |
| 2 | **Tendenza** | Linea per provider, tratteggi diversi, banda d'incertezza attorno alla linea attiva. Filtro provider. Asse Y in percentuale con tick allo 0 sempre visibile | «Servono almeno due giorni di dati per una tendenza» |
| 3 | **Provider** | Tabella affiancata. La colonna **memory mode** e' separata da un filetto verticale e da un'intestazione che dice *«metrica diversa: cosa il modello ricorda, non cosa trova»* | «Nessun provider configurato: aggiungi una chiave API nel .env» |
| 4 | **Categorie** | Griglia categoria x provider. Ogni cella: numero + banda compatta. Le celle con `tasso: null` mostrano `—` e il denominatore, non un colore chiaro che si confonde con «poco» | «Le categorie compaiono dopo il primo `sync-topics`» |
| 5 | **Dove sei invisibile** | **La sezione operativa.** Lista, non griglia. Ogni riga: titolo dell'articolo, categoria, quante volte sondato, e un distintivo se `recuperato_mai` (recuperato ma non citato = problema diverso). Clic → dettaglio con le risposte ricevute e **chi e' stato citato al posto tuo** | «Nessun articolo e' stato sondato almeno 10 volte senza mai essere citato. Con pochi dati e' normale» |
| 6 | **Cosa funziona** | Articoli citati, ordinati per citazioni. Distingue *citato* da *target hit* (il pezzo giusto) | «Ancora nessuna citazione registrata» |
| 7 | **Esplora probe** | Tabella filtrabile, `overflow-x-auto` su mobile. Riga → pannello con la risposta integrale e le citazioni | «Nessun probe con questi filtri» + pulsante per azzerarli |
| 8 | **Stato del sistema** | Ultimi run, prossime esecuzioni, budget residuo come barra. Banner `sigillo` se il budget e' superato | «Lo scheduler e' spento (`SCHEDULER_ENABLED=false`)» |

Gerarchia: 1 e 5 sono le due sezioni con peso visivo. Le altre sono supporto.

---

## 7. Rilettura critica

> «Se una scelta e' quella che faresti per qualunque dashboard, cambiala e
> annota perche'.»

Cosa la ricerca automatica ha proposto, e cosa ho fatto invece.

| Proposto | Scartato perche' | Scelto |
|---|---|---|
| Palette **blu #1E40AF + ambra #D97706** | E' *la* tavolozza da dashboard SaaS. Riconoscibile al primo sguardo come «generata», e non dice niente su un giornale scolastico italiano | `timbro`/`alloro`/`ottone`: viola da timbro, verde alloro, ottone. Riferimenti al mondo dei documenti e della scuola |
| **Fira Code** per i titoli, Fira Sans per il corpo | Monospazio nei titoli e' la scorciatoia per «technical». Qui il soggetto non e' tecnico, e' editoriale. E Fira Code sui numeri grandi e' inerte | Bricolage Grotesque display + IBM Plex Sans dati. Il monospazio resta dove serve davvero: `raw_response` e slug |
| Pattern **«Real-Time / Operations Landing»** con hero e CTA | E' la struttura di una *landing di vendita*. Questa e' una pagina dietro login per una persona sola: non ha niente da vendere e nessuno da convertire | Otto sezioni, gerarchia per utilita' operativa. Zero hero, zero CTA |
| «Status colors (green/amber/red)» | Il verde/rosso e' inaccessibile ai daltonici ed e' anche semanticamente sbagliato qui: *non essere citato non e' un errore*, e' il caso normale da cui si parte. Colorare di rosso lo stato di default significherebbe dire alla redazione che sta sbagliando sempre | `timbro` per presenza, `grafite` per assenza — nessuno dei due e' un giudizio. `sigillo` esiste solo per gli errori veri (probe falliti, budget) |
| Heat map per la griglia categorie | La ricerca stessa avverte: serve un fallback per i daltonici e i valori esatti a hover. Con denominatori a una cifra, un gradiente di colore comunica una certezza che non c'e' | Griglia di **numeri** con banda compatta. Il colore e' secondario, il numero e la sua incertezza sono il dato |

E i tre default vietati dalla specifica, per completezza:

* **fondo crema + serif alto contrasto + accento terracotta** → `gesso` ha un
  cast verde-grigio, non giallo; il display e' un grottesco, non un serif; non
  esiste terracotta in tavolozza (`ottone` e' desaturato e vive nell'ambito
  degli avvisi, non come accento identitario).
* **fondo quasi-nero con un solo accento acido** → il tema di base e' chiaro.
  Il tema scuro esiste, e' progettato in parallelo (non un'inversione), e ha la
  stessa tavolozza a sei colori — non un accento solo.
* **pastiche da giornale, righe sottili e raggio zero** → raggio 6px sulle card
  e 4px sui controlli, superfici piene con un'ombra minima. Nessun filetto
  hairline, nessuna colonna tipo quotidiano, nessun capolettera.

---

## 8. Vincoli tecnici non negoziabili

* **Focus da tastiera visibile**: anello 2px `timbro` con 2px di offset su ogni
  elemento interattivo. Mai `outline: none` senza sostituto.
* **`prefers-reduced-motion`**: tutte le transizioni a 0ms, nessuna animazione
  d'ingresso dei grafici. I dati devono essere leggibili immediatamente in ogni
  caso — l'animazione e' un miglioramento, non il modo di trasmettere il dato.
* **Transizioni** 150–200ms, `ease-out` in entrata. Solo `transform` e
  `opacity`.
* **Bersagli tocco** ≥44px su mobile, anche per le righe di tabella cliccabili.
* **Responsive**: verificato a 375 / 768 / 1024 / 1440. Tabelle in
  `overflow-x-auto` con ombra di bordo che segnala lo scorrimento; la griglia
  categorie su mobile diventa una lista per categoria.
* **Icone**: Lucide, tratto 1.5px, dimensione a token (16/20/24). Nessuna emoji.
* **Tema scuro**: `lavagna` come fondo, `gesso` come testo, gli accenti
  schiariti (non invertiti) per mantenere il contrasto. Progettato insieme al
  chiaro, non dopo.
* **Ogni percentuale porta il suo denominatore.** Non e' una linea guida
  estetica: e' il requisito che l'API impone col tipo `Tasso`, e la UI non ha
  modo di aggirarlo perche' il dato arriva sempre con `numeratore`,
  `denominatore`, `ic_basso`, `ic_alto`, `affidabile`.
