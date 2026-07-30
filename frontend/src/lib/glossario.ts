/**
 * GLOSSARIO — l'unica fonte di verità per il significato delle metriche.
 *
 * Ogni numero di questa interfaccia è il risultato di una decisione di
 * misurazione che l'utente non può dedurre guardandolo. «Citation rate 4,2%»
 * non dice quali probe sono nel denominatore, non dice che i falliti sono
 * esclusi, non dice che mention e citazione sono due cose diverse. Senza queste
 * righe la dashboard è leggibile ma non interpretabile, e un numero
 * interpretato male è peggio di un numero assente.
 *
 * Le voci stanno QUI e non nei componenti perché la stessa metrica compare in
 * più sezioni (il citation rate in cinque punti diversi): due formulazioni
 * divergenti della stessa definizione sono un bug di prodotto, non una svista
 * editoriale.
 *
 * Regole di scrittura, da rispettare aggiungendo voci:
 *  - `misura` risponde a «cosa conta questo numero», in una frase sola;
 *  - `conto` esplicita numeratore e denominatore quando non sono ovvi;
 *  - `lettura` dice cosa farne — è la parte che serve davvero a una redazione;
 *  - `attenzione` è l'errore di lettura tipico, e va messo solo se esiste.
 *
 * Nessuna voce deve suggerire che il VOLUME di interrogazioni aumenti le
 * citazioni: interrogare un'API non modifica l'indice di retrieval del
 * provider. Non è un disclaimer di prodotto ma una difesa del budget — chi
 * credesse il contrario alzerebbe la frequenza dei cicli per niente. Lo scopo
 * di questa dashboard resta far salire le citazioni, per la via che funziona:
 * scoprire dove il giornale è invisibile e pubblicarci sopra. Vedi la voce
 * `non_aumenta`, che dice all'utente quale leva funziona e quale no.
 */

export interface VoceGlossario {
  termine: string;
  misura: string;
  conto?: string;
  lettura?: string;
  attenzione?: string;
}

export const GLOSSARIO = {
  /* ------------------------------------------------ i quattro numeri chiave */

  citation_rate: {
    termine: "Citation rate",
    misura:
      "La quota di risposte in cui edunews24.it compare fra le fonti citate dal motore.",
    conto:
      "Sopra: i probe in cui il dominio è fra le fonti citate. Sotto: i probe riusciti con la ricerca web attiva. I probe falliti e quelli in cui il provider non ha cercato non entrano né sopra né sotto.",
    lettura:
      "È il numero principale. Per un giornale che compete con le testate nazionali valori a una cifra sono la norma: quello che conta è la direzione nel tempo e su quali categorie il numero resta zero.",
    attenzione:
      "Non è una posizione in classifica e non esiste un valore «giusto» a cui puntare. Serve a confrontare periodi, categorie e provider fra loro, non con un obiettivo assoluto.",
  },

  mention: {
    termine: "Mention senza link",
    misura:
      "Il modello nomina Edunews24 nel testo della risposta ma non lo elenca fra le fonti.",
    lettura:
      "È un segnale di riconoscimento: il modello sa che il giornale esiste. Vale come indizio di notorietà, non come traffico — senza link il lettore non arriva sul sito.",
    attenzione:
      "Non va mai sommata al citation rate. Sono due cose diverse misurate sulla stessa risposta: la citazione può esserci senza mention e la mention senza citazione.",
  },

  target_hit: {
    termine: "Articolo giusto",
    misura:
      "Fra le fonti citate c'è proprio l'articolo che ha generato la domanda, non un altro pezzo del sito.",
    conto:
      "Si confronta lo slug nell'URL citato con quello dell'articolo da cui è nata la domanda.",
    lettura:
      "Citation rate alto e «articolo giusto» basso significa che i motori conoscono il sito ma pescano pezzi diversi da quello pertinente: di solito è un problema di titolo e di struttura dell'articolo, non di autorevolezza del giornale.",
  },

  recuperato: {
    termine: "Recuperato",
    misura:
      "Il sito è comparso fra le pagine che il motore ha consultato prima di rispondere, che poi le abbia citate o no.",
    lettura:
      "«Recuperato ma non citato» è la diagnosi più utile di tutta l'interfaccia: il motore ti trova, apre la pagina e sceglie di citare qualcun altro. Il problema è nella pagina — risposta poco esplicita, dato sepolto a metà articolo — non nell'indicizzazione.",
    attenzione:
      "Non tutti i provider dichiarano le fonti consultate ma non citate. Dove non le dichiarano questo numero coincide con il citation rate e non aggiunge informazione.",
  },

  /* ------------------------------------ cosa entra nei conti e cosa ne resta fuori */

  probe: {
    termine: "Probe",
    misura:
      "Una singola domanda posta a un singolo provider in una singola modalità (con ricerca web, oppure a memoria).",
    lettura:
      "È l'unità di conto di tutte le percentuali. La stessa domanda mandata a quattro provider fa quattro probe.",
  },

  nessuna_ricerca: {
    termine: "Nessuna ricerca",
    misura:
      "Il provider ha risposto di sua iniziativa senza consultare il web, pur avendo lo strumento di ricerca a disposizione.",
    lettura:
      "Non è «non citato»: è «non misurato». Questi probe sono esclusi da ogni denominatore, altrimenti un modello pigro somiglierebbe a un crollo di visibilità.",
  },

  falliti: {
    termine: "Probe falliti",
    misura: "Errori del provider, timeout e limiti di frequenza superati.",
    lettura:
      "Esclusi da ogni denominatore e mostrati come conteggio a parte. Un'interruzione di servizio di un provider non deve somigliare a un crollo di visibilità.",
  },

  memoria: {
    termine: "Memoria",
    misura:
      "La stessa domanda posta senza attivare la ricerca web: misura cosa il modello ha memorizzato durante l'addestramento.",
    lettura:
      "Si muove lentissimamente — cambia quando esce un nuovo modello, non quando pubblichi un articolo. È una fotografia della notorietà del giornale al momento dell'addestramento.",
    attenzione:
      "Non si confronta con il citation rate e non entra negli stessi conti. Nella tabella dei provider è separata da un filetto verticale esattamente per questo.",
  },

  non_risolto: {
    termine: "Dominio non risolto",
    misura:
      "Citazioni il cui URL è un redirect del provider: il dominio reale non è leggibile senza seguire il link.",
    lettura:
      "Si dichiara invece di indovinarlo. È una quota di misura mancante: se è alta, la classifica dei domini è parziale in quella misura.",
  },

  recuperabilita: {
    termine: "Perché «Dove sei invisibile» è ordinata così",
    misura:
      "Non per numero di probe, ma per quanto costa rimediare. Prima gli articoli che il motore ha già aperto senza citarli, poi quelli che non ha mai aperto.",
    lettura:
      "In cima ci sono i recuperi sprecati: la pagina è stata letta e scartata, quindi il traffico di retrieval esiste già e manca solo l'ultimo passaggio — di solito la risposta non è esplicita dove il motore la cerca, ed è lavoro di riscrittura su un pezzo che c'è. Sotto ci sono gli argomenti mai raggiunti: lì manca il pezzo, o l'autorevolezza sull'argomento, e il lavoro è molto più lungo.",
    attenzione:
      "Non c'è un punteggio di opportunità che pesi recuperi e probe in un numero solo: con questi denominatori i pesi sarebbero inventati. L'ordine dentro ciascun gruppo è per conteggio grezzo, e fra due articoli vicini la differenza può essere caso.",
  },

  /* --------------------------------------------- perché i numeri hanno una banda */

  banda: {
    termine: "La banda sotto ogni percentuale",
    misura:
      "L'intervallo di confidenza al 95%: l'insieme dei valori compatibili con i dati raccolti finora.",
    lettura:
      "Il pallino è la stima, la banda è quanto quella stima può spostarsi raccogliendo altri dati. Due numeri le cui bande si sovrappongono non sono distinguibili, anche se uno appare più alto dell'altro.",
    attenzione:
      "La banda si stringe solo aumentando i probe, cioè aspettando. Con venti probe una percentuale ha un margine di una ventina di punti: è la realtà del campione, non un difetto del calcolo.",
  },

  soglia: {
    termine: "Perché a volte c'è un trattino",
    misura:
      "Sotto i 10 probe la percentuale non si mostra affatto; fra 10 e 30 si mostra sbiadita, perché è ancora fragile.",
    lettura:
      "Un tasso calcolato su tre casi non è una misura: 1 su 3 fa «33%» e sembra un numero, ma il caso successivo lo porta a 25% o a 50%. Il trattino dice che il dato non c'è ancora, non che vale zero.",
  },

  significativita: {
    termine: "Variazione significativa",
    misura:
      "Il confronto con il periodo precedente compare solo quando gli intervalli di confidenza dei due periodi non si sovrappongono.",
    lettura:
      "Quando leggi «variazione non significativa», la differenza fra i due numeri è compatibile con il caso: non è successo niente di misurabile. Mostrarla con una freccia verde sarebbe la bugia più facile di tutta l'interfaccia.",
  },

  /* ------------------------------------------------------ come nascono le domande */

  ciclo: {
    termine: "Ciclo",
    misura:
      "L'insieme dei probe generati e inviati insieme. Il ciclo automatico parte al minuto 7 di ogni ora.",
    lettura:
      "«Esegui un ciclo» ne avvia uno subito, senza aspettare l'ora. Un ciclo manuale è marcato come tale e resta distinguibile nei grafici.",
  },

  strategia: {
    termine: "Come è nata la domanda",
    misura:
      "Da cosa è stata costruita: dalle FAQ scritte in redazione, da keyword e intento, da una combinazione di tag, dall'angolo dell'articolo, oppure dalla categoria editoriale.",
    lettura:
      "Serve a capire se un certo tipo di domanda porta citazioni più di un altro, e quindi come conviene impostare i pezzi.",
    attenzione:
      "Nessuna domanda contiene il nome del giornale né il dominio: una domanda che li nominasse otterrebbe la citazione per costruzione e falsificherebbe la misura. Il validatore scarta quelle che li contengono.",
  },

  quota_dominio: {
    termine: "Quota di un dominio",
    misura:
      "Su tutte le citazioni raccolte nel periodo, quante vanno a quel dominio.",
    lettura:
      "È chi occupa il posto quando il giornale non c'è. Le quote non sommano a 100% perché la classifica è troncata ai primi domini.",
  },

  /* --------------------------------------------------------- costi e prestazioni */

  costo_stimato: {
    termine: "Costo stimato",
    misura:
      "Quando il provider non restituisce il conteggio dei token, il costo si ricava dal listino versionato invece che dai dati reali della chiamata.",
    lettura:
      "È marcato come stimato proprio per non farlo sembrare misurato. Un costo a zero, silenzioso, sarebbe molto peggio di una stima dichiarata.",
  },

  latenza: {
    termine: "Latenza mediana",
    misura:
      "Il tempo di risposta al centro della distribuzione: metà dei probe è più veloce, metà più lenta.",
    lettura:
      "Mediana e non media perché un singolo probe da novanta secondi sposterebbe la media e lascerebbe la mediana dov'è.",
  },

  ricerche: {
    termine: "Ricerche",
    misura: "Quante ricerche web il modello ha eseguito in media prima di rispondere.",
    lettura:
      "Più ricerche significano più fonti in gioco, quindi più concorrenza per essere citati — non una maggiore probabilità di esserlo.",
  },

  /* ------------------------------------------------ cosa questo strumento non fa */

  non_aumenta: {
    termine: "Come si aumentano davvero le citazioni",
    misura:
      "Non sondando di più: interrogare l'API di un provider non modifica l'indice con cui quel provider sceglie le fonti. Il numero si muove per quello che il giornale pubblica, non per quante domande gli si mandano.",
    lettura:
      "La leva è la sezione «Dove sei invisibile»: gli argomenti su cui il giornale viene sondato e mai citato dicono dove manca un pezzo, e i «recuperato ma non citato» dicono quali pezzi il motore apre e scarta — di solito perché la risposta non è esplicita nei primi paragrafi. Riscrivere quelli, e coprire i buchi, è ciò che sposta il citation rate.",
    attenzione:
      "Raddoppiare i cicli orari o il numero di domande non alza il tasso: alza solo la spesa e stringe l'intervallo di confidenza. Se un argomento è a zero, la risposta è pubblicarci sopra, non sondarlo più spesso.",
  },
} as const satisfies Record<string, VoceGlossario>;

export type ChiaveGlossario = keyof typeof GLOSSARIO;

/** Raggruppamento usato dalla guida completa in fondo alla pagina. */
export const GRUPPI_GLOSSARIO: Array<{ titolo: string; voci: ChiaveGlossario[] }> = [
  {
    titolo: "I quattro numeri principali",
    voci: ["citation_rate", "mention", "target_hit", "recuperato"],
  },
  {
    titolo: "Cosa entra nei conti e cosa ne resta fuori",
    voci: ["probe", "nessuna_ricerca", "falliti", "memoria", "non_risolto"],
  },
  {
    titolo: "Perché ogni numero ha una banda",
    voci: ["banda", "soglia", "significativita"],
  },
  {
    titolo: "Come nascono le domande",
    voci: ["ciclo", "strategia", "quota_dominio"],
  },
  {
    titolo: "Da dove cominciare",
    voci: ["recuperabilita"],
  },
  {
    titolo: "Costi e prestazioni",
    voci: ["costo_stimato", "latenza", "ricerche"],
  },
  {
    titolo: "Come si passa dalla misura al risultato",
    voci: ["non_aumenta"],
  },
];
