# ROMABUS · Autobus di Roma per iPhone

Prima versione di un’app indipendente Expo / React Native, con un backend Python che legge gli open data di Roma Servizi per la Mobilità. Il nome del progetto non implica affiliazione con ATAC o Roma Mobilità.

Per provarla gratuitamente da Windows su iPhone, segui [la guida passo passo](PROVA-IPHONE-WINDOWS.md). Non serve Apple Developer a pagamento.

## Funzionalità

La home adotta il layout **01 · ROMABUS**, con logo e indicatore feed in alto, slogan **“L’attesa ha i minuti contati.”**, sottotitolo **“I bus di Roma, in tempo reale.”** e fino a tre **ultime linee cercate** apribili con un tocco. La cronologia esistente resta disponibile e gli identificativi GTFS vengono risolti dal nome pubblico della linea quando cambiano. In **Impostazioni → Home** si può scegliere tra **Linee recenti** (predefinite) e **Fermate preferite**; scelta e cronologia sono salvate sul dispositivo. Le preferite aprono gli arrivi della fermata senza richiedere previsioni nella home. Seguono i due pulsanti affiancati **Cerca linea** e **Cerca fermata**, la voce disattivata **Calcola percorso** e, in fondo, il disclaimer **“ROMABUS è un progetto indipendente.”** con il testo di non affiliazione e la provenienza dei dati, sopra **Impostazioni**. Il chip **Feed live** condivide con le partenze il pallino verde e la pulsazione tenue, disabilitata se è richiesta una riduzione delle animazioni; feed indisponibili, parziali o non verificabili hanno indicazione statica e neutra. Fuori dalla home una barra flottante inferiore permette di passare fra Linee/Fermate/Percorso/Impostazioni, anche nei dettagli di linee e fermate. I ritorni restano in alto a sinistra; nel percorso il titolo linea-direzione è fisso al centro e Cambia Direzione è a destra. Le partenze sono una riga orizzontale compatta e le fermate si aprono con la freccia accanto al nome.

L’aspetto segue il dispositivo: **Chiaro** usa superfici bianche e rosso scuro; **Scuro** usa blu notte, testo avorio e accenti rossi. In **Impostazioni → Aspetto** si sceglie uno dei temi oppure **Automatico**. La preferenza viene salvata sul dispositivo e vale per tutte le schermate. Gli indicatori live restano verdi in entrambi i temi. Il nome visualizzato, il titolo web e il nome dell’app installata sono **ROMABUS**.

Le **Impostazioni** mostrano anche versione e copyright configurati in `app.json` e lo stato dei feed realtime di `romamobilita.it`. Posizioni autobus e previsioni di arrivo vengono controllate separatamente tramite `/api/status`, all’apertura e con **Verifica ora** per richiedere dati nuovi. La pagina non esegue controlli periodici né ricarica al ritorno dell’app in primo piano. Lo stato considera la validità dei timestamp all’ultima verifica: dati scaduti o conservati dopo un errore non fanno risultare operativa la fonte. Se il servizio dell’app non è raggiungibile, lo stato della fonte viene indicato come non verificabile.

Entrambi i temi mantengono lo sfondo originale con sfere sfumate rosse e azzurre: toni chiari nella versione diurna e sfumature più profonde nella versione notturna.

Le schede e i controlli usano superfici opache e bordi definiti per mantenere leggibili orari e fermate sullo sfondo decorativo. Le sfumature dello sfondo usano `expo-linear-gradient`, incluso in Expo Go SDK 58.

- Ritorno fisso alla home in alto a sinistra nelle tre categorie. Le ultime dieci linee aperte vengono salvate sul dispositivo e mostrate per prime nei risultati compatibili con la ricerca.
- Ricerca delle linee autobus, scelta della direzione e delle varianti di percorso, partenze dal capolinea da 5 minuti fa a 90 minuti avanti ed elenco delle fermate.
- Le schede di direzione e l’intestazione degli orari condividono l’ordine **TIPO CORSA** in maiuscolo, **direzione**, **DA capolinea**. Nella tendina delle non attive le ordinarie precedono sempre tutte le altre categorie; le voci restano più piccole e secondarie rispetto alle direzioni attive.
- L’aggiornamento ogni 10 secondi riguarda solo scelta della direzione, percorso della linea e arrivi della fermata aperta. Richieste e contatori live sono sospesi quando la pagina perde il focus o l’app va in background. Home, ricerche, orari programmati e impostazioni caricano all’apertura o su aggiornamento manuale, senza timer né ricarica al ritorno dell’app in primo piano. Il refresh globale coinvolge solo i caricamenti della pagina attualmente aperta.
- Gli orari programmati appartengono alla sequenza di fermate selezionata: corse ordinarie, scolastiche e festive con gli stessi capolinea restano separate. La tabella mostra il giorno 00:00–23:59 e le sole 00:00–02:59 successive, con un’ora per riga e solo i minuti nelle celle. Un percorso senza corse nella data scelta mostra uno stato vuoto, senza ereditare gli orari degli altri percorsi; i pulsanti data permettono di consultare gli altri giorni.
- Le varianti non attive sono in fondo alla scelta della direzione. Il GTFS di Roma non contiene i carteggi DS/PS/LS: `server/school_services.json` raccoglie le sigle e gli orari di riferimento pubblicati nel [catalogo delle corse scolastiche](https://romaatac.altervista.org/en/stato-servizio/corse-scolastiche/) e le sequenze documentate nelle pagine dei singoli percorsi. Il classificatore richiede una sequenza di fermate documentata identica oppure che tutti gli orari di partenza coincidano con un profilo pubblicato; risolve eventuali omonimie tramite i capolinea e non deduce lo stato scolastico dai soli giorni feriali o dalla rarità delle corse. La tabella di riferimento serve solo per il nome della variante: gli orari mostrati provengono sempre dal GTFS e dal suo calendario. Profili mancanti, cambiati o ambigui mantengono una descrizione generica; aggiornare il catalogo quando il gestore modifica percorsi o corse. Nei dettagli degli orari compare anche una fermata che distingue il percorso deviato, quando identificabile.
- Miniature rosse frontali dei bus, preparate dal riferimento fornito e precaricate in memoria con `expo-image`, a sinistra delle fermate: alla fermata se fermi, nel tratto precedente se in arrivo. Posizioni dal feed GTFS Realtime, dettaglio veicolo e apertura in Mappe di Apple; eventuali associazioni GPS approssimate sono marcate con ≈.
- Fermate preferite salvate sul dispositivo: aggiunta/rimozione tramite stella nel dettaglio, elenco nella scheda Fermate e apertura diretta degli arrivi.
- Tocco su una fermata del percorso per gli arrivi delle linee nella prossima ora (fino a 60 minuti inclusi), senza limite di 20 risultati. Il limite viene applicato sia dal server sia dalla schermata, usando la previsione live quando valida o l’orario programmato di fallback. Le vetture live non al capolinea precedono quelle ferme al capolinea, mantenendo l’ordine temporale dentro ciascun gruppo; gli orari programmati restano in fondo; per una stessa linea, direzione pubblica e giornata di servizio, i programmati sono mostrati solo in assenza di live. Le diverse vetture live rimangono visibili. La vista mostra **In arrivo tra:** sopra i minuti d’attesa; per attese fino a un minuto mostra **In arrivo** su un’unica riga, con il numero vettura su una riga separata sotto lo stato live. Le schede mantengono le stesse dimensioni e la stessa struttura: badge a sinistra, destinazione/stato/vettura al centro e tempi nella colonna destra. Quando il bus è al capolinea, i minuti vengono sostituiti nella stessa colonna da **Prossima partenza: HH:mm**, usando la partenza del capolinea distinta dall’arrivo alla fermata. Se la previsione di partenza live manca o non è più valida, viene usata la partenza programmata della stessa corsa anche quando l’orario è già trascorso, con la dicitura **Programmata**; in assenza di un orario valido compare **Non disponibile**. La vista mantiene aggiornamento automatico/manuale con indicatore soltanto nel tasto di refresh, senza spinner in alto né pull-to-refresh nella vista della singola fermata, e ritorno fisso alla direzione selezionata. Toccando una linea in arrivo si apre il suo itinerario nella direzione della corsa, con le posizioni dei relativi bus. Previsioni live quando presenti, altrimenti orari esplicitamente programmati; corse cancellate e fermate saltate vengono escluse.
- **Calcola percorso** è temporaneamente disattivato nella home e nella barra inferiore e mostra **Funzionalità in arrivo**. Anche l’apertura diretta di `/plan` mostra solo questo avviso e non invia richieste di calcolo. Il motore del backend resta disponibile per lo sviluppo.
- Nessun dato dimostrativo nell’app. Feed indisponibili o scaduti producono stati espliciti, senza simulare il servizio.

## Fonti

Le sezioni **Metro** e **News** sono accessibili dalle due nuove scorciatoie nella home, nello stesso stile chiaro/scuro dell’app. Le due pagine hanno anche collegamenti reciproci e il pulsante di aggiornamento manuale.

- **Metro** mostra separatamente A, B, B1 e C. La fonte è il [feed ufficiale ATAC dello stato del servizio](https://www.atac.roma.it/feeds/stato-del-servizio-in-tempo-reale), documentato nella [pagina RSS del gestore](https://www.atac.roma.it/feed-rss). Solo un messaggio esplicito può indicare servizio regolare: linee assenti dal feed, esiti sconosciuti, errori o copie non più verificabili restano non verificabili. Una chiusura di stazione è distinta da un’interruzione del servizio. Il dato non rappresenta la posizione dei treni né una previsione di arrivo.
- **News** legge le raccolte pubbliche `infomobilita` e `primo-piano` dell’API WordPress di Roma Mobilità: fino a 100 articoli per raccolta modificati negli ultimi 30 giorni. Le notizie sono unite senza duplicati, ordinate per aggiornamento e filtrabili per categoria. Ogni scheda conserva fonte, data, testo consultabile e collegamento all’originale; il primo caricamento mostra 20 notizie, con pulsante per le successive.
- **Segnalazioni e novità** compare nella scelta della direzione e nel percorso della linea quando sono presenti comunicazioni pertinenti. Gli avvisi del feed del gestore e le notizie di Roma Mobilità sono distinti per fonte; le notizie datate non vengono presentate come prova che una vecchia deviazione sia ancora attiva. L’associazione usa il nome pubblico esatto della linea, incluse notturne, zeri e suffissi (`75` e `075` restano distinte), ricavato da riferimenti espliciti alle linee; numeri di fermata e orari non sono riferimenti di linea. Il riquadro è inizialmente compatto, con il primo titolo e la sua data; il tocco apre tutti i dettagli e i collegamenti alle fonti. Gli avvisi restano separati dalle previsioni e dalle posizioni: un errore della fonte informativa non interrompe la consultazione dei bus.

Le nuove API sono `GET /api/metro`, `GET /api/news` e `GET /api/routes/{route_id}/alerts`, tutte con `fresh=1` per una verifica manuale. I download delle fonti sono condivisi e memorizzati per 60 secondi; un aggiornamento ordinario conserva la copia precedente durante il download, gli errori hanno un breve intervallo di riprova e sono indicati senza spacciare la copia conservata per una verifica riuscita. Il timestamp mostrato è quello della verifica della fonte; date di pubblicazione e aggiornamento degli articoli sono separate. I bollettini di servizio presenti nel feed corrente restano validi fino alla modifica/rimozione da parte del gestore: la loro data di pubblicazione non è la scadenza di una posizione GPS. Un errore di verifica o una data di generazione futura di oltre un minuto impediscono di presentarli come stato corrente.

Il client aggiorna Metro ogni 30 secondi e News/segnalazioni ogni 60 secondi, soltanto con la pagina visibile e l’app in primo piano. Tornando all’app viene richiesta una verifica; home, ricerche, orari e impostazioni mantengono il caricamento all’apertura/manuale. I nuovi collegamenti nella home non avviano richieste informative prima di aprire le rispettive pagine. Queste funzioni non aggiungono dipendenze né richiedono chiavi API.

Feed individuati nel catalogo pubblico [MobilityData](https://github.com/MobilityData/mobility-database-catalogs), record 1294 (GTFS), 1776 (Vehicle Positions) e 1778 (Trip Updates), provider Roma Servizi per la Mobilità, senza autenticazione dichiarata:

- GTFS: https://romamobilita.it/sites/default/files/rome_static_gtfs.zip
- Posizioni: https://romamobilita.it/sites/default/files/rome_rtgtfs_vehicle_positions_feed.pb
- Corse: https://romamobilita.it/sites/default/files/rome_rtgtfs_trip_updates_feed.pb
- Condizioni del dataset: https://romamobilita.it/it/tecnologie/open-data/dataset

L’importazione del GTFS e la lettura dei feed realtime sono state verificate nell’ambiente cloud il 2 novembre 2026. L’accesso richiede che `romamobilita.it` sia consentito dalla policy di rete. Prima della distribuzione occorre verificare licenza e attribuzione sulla pagina ufficiale. I feed non sono inclusi nel repository.

## Ambiente di sviluppo

Prerequisiti: Node 24, npm 11, Python 3.12 con venv. Dalla radice del checkout:

```sh
npm ci
python3 -m venv .venv
.venv/bin/python -m pip install -r server/requirements.txt
npm run data:import
npm run api
```

Il comando di importazione richiede accesso HTTPS a `romamobilita.it` e agli eventuali host di redirect ufficiali. Costruisce un database SQLite indicizzato in `server/data/` e lo sostituisce solo dopo un’importazione riuscita. Ripetere ogni giorno per aggiornare il calendario. Non avviare importazioni concorrenti.

Sulla VM Linux con systemd puoi automatizzare `npm run data:import` ogni giorno alle **04:00, ora di Roma**. La [guida per la VM](deploy/README.md) spiega l’attivazione e aggiorna anche lo script `aggiorna-romabus`. Su Linux un blocco condiviso serializza importazioni manuali, importazioni giornaliere e aggiornamenti del codice.

L’API di sviluppo ascolta su loopback porta 8000. Verifica interna: `curl -f http://127.0.0.1:8000/api/status`. Stato HTTP 200 indica che l’API risponde: verificare anche `staticAvailable`, `serviceToday`, `vehicles.available` e `updates.available`. Senza orari importati, gli endpoint di ricerca restituiscono 503.

In un secondo terminale:

```sh
EXPO_NO_TELEMETRY=1 EXPO_PUBLIC_API_URL=https://HOST-HTTPS-DEL-BACKEND npm start
```

`EXPO_PUBLIC_API_URL` è un indirizzo pubblico non segreto incorporato nel bundle. Il telefono deve poterlo raggiungere. Non usare l’indirizzo loopback del cloud sul telefono. Pubblicare l’API dietro HTTPS con un servizio di deployment/forwarding supportato; non è stato creato un endpoint pubblico in questo task. Per sviluppo su una rete locale controllata si può usare `API_HOST=0.0.0.0 npm run api`, limitando l’accesso alla rete di sviluppo.

Il progetto usa Expo SDK 58, corrispondente alla versione di Expo Go segnalata sull’iPhone dell’utente. Expo Go per iPhone supporta soltanto il proprio SDK corrente: verificare sempre il messaggio sul dispositivo. Per Windows usa `setup-windows.cmd` e la guida dedicata: backend e app possono collegarsi via HTTP sulla stessa rete privata, senza hosting. Per un backend esposto su Internet serve HTTPS. Nessuna prova su iPhone fisico è stata effettuata. Il cloud Linux verifica il bundle JavaScript, non una build nativa firmata:

```sh
EXPO_NO_TELEMETRY=1 CI=1 npx expo export --platform ios
```

L’assenza di una variabile API lascia l’app avviabile, ma mostra istruzioni di configurazione invece di dati.

## Verifiche

```sh
npm run typecheck
EXPO_NO_TELEMETRY=1 npm run lint
npm run test:server
```

I test backend usano GTFS sintetici isolati in directory temporanee, mai caricati nell’app. Coprono cambi, tempi minimi di cambio, calendari, corse dopo mezzanotte, dati live scaduti, cancellazioni e conservazione atomica del database.

Se il servizio metadati Expo non è accessibile, `EXPO_OFFLINE=1` consente alla CLI di usare le versioni compatibili incluse nell’SDK per installare da npm, senza disabilitare TLS o controlli d’integrità.

## Limiti della prima versione

Il calcolo è solo autobus, fra fermate selezionate, con cambi alla stessa fermata e margine di 2 minuti; considera partenze nelle prossime 4 ore. Non include indirizzi, cammino, metropolitana, accessibilità, frequenze non basate su orari o ottimizzazione del percorso in base al traffico. I tempi live sono visibili alle fermate ma non ricalcolano gli itinerari. Le direzioni con sequenze di fermate diverse sono scelte separate. La scelta mostra solo varianti con una corsa programmata già in viaggio o in partenza entro un’ora, secondo calendario ed eccezioni GTFS (incluse corse oltre mezzanotte). Non deduce l’attività dal nome “scolastica” o “deviata” e non integra ancora cancellazioni live nel filtro delle direzioni. Le miniature sono collocate tramite corsa e sequenza/ID della fermata; se questi riferimenti mancano, solo i bus di una direzione non ambigua possono essere associati al percorso. Per le corse note, il GPS può indicare approssimativamente la fermata più vicina entro 500 metri; le posizioni ambigue o troppo distanti non sono collocate. Alert e deviazioni non sono ancora integrati.

Il server aggiorna posizioni e previsioni in background ogni **10 secondi**, con cache condivisa; direzione e arrivi si aggiornano sul client ogni **10 secondi**. Il pulsante flottante ↻ nella linea resta visibile mentre si scorre e mostra l’indicatore durante l’aggiornamento, anche automatico. Il pulsante, il trascinamento verso il basso e il ritorno alla direzione saltano la cache ordinaria di 10 secondi; i refresh entro due secondi dallo stesso download condividono la copia appena acquisita. Un download lento non blocca chi legge un feed ancora valido, e i due feed vengono scaricati indipendentemente. Le richieste lente del client vengono completate prima di iniziare un altro aggiornamento. Gli arrivi entro un minuto sono indicati come **In arrivo**.

Le icone non allungano la distanza fra le fermate. Le posizioni attuali hanno una misura non più vecchia di 90 secondi. Un’omissione temporanea del feed viene tollerata per 45 secondi; le posizioni conservate, quelle fra 90 e 180 secondi e quelle visibili durante un errore di richiesta sono indicate come ultima posizione nota nel dettaglio della vettura. Nessuna icona resta oltre tre minuti dalla misura originale e i timestamp delle previsioni devono essere ancora validi: una nuova risposta non ringiovanisce la vecchia posizione.

Il backend ricorda l’avanzamento mostrato per vettura, percorso e istanza di corsa. Un riferimento che arretra, una previsione mancante o un GPS temporaneamente non associabile conservano l’ultima collocazione come posizione nota fino alla sua scadenza. Un ETA ancora futuro impedisce a GPS o storico di collocare l’icona oltre quella fermata; una previsione più recente può correggere un’icona che era stata mostrata troppo avanti. Le risposte precedenti non possono annullare questa correzione. Una nuova corsa, data di servizio o ora iniziale azzera lo storico. Questa memoria è locale al processo backend e si azzera al riavvio.

Se manca il timestamp del veicolo, un nuovo timestamp globale del feed non ringiovanisce una misura identica; una firma conservata per sei ore dall’ultima presenza impedisce che ricompaia dopo la scadenza dello storico. La fermata `stop_id` prevale su contatori di sequenza discordanti; nei percorsi ad anello la sequenza distingue le occorrenze della stessa fermata. Il GPS può correggere un riferimento bloccato quando la proiezione è sufficientemente vicina e non ambigua, ma non fa arretrare un riferimento valido verso una fermata precedente. Nei dettagli si legge l’orario della misura, con i secondi. I numeri vettura usano soltanto `VehicleDescriptor.label`, destinato al pubblico; ID tecnici di veicolo, entità e corsa non vengono presentati come matricole. In assenza di label compare “non disponibile” (— nell’icona).

Gli ETA live sono verdi; quelli programmati restano neutri. L’API mantiene le corse programmate come fallback e deduplica soltanto la stessa istanza di corsa/fermata/data. Il client mette i live prima e usa i programmati per direzioni senza live; non confonde due vetture live o passaggi diversi di un percorso ad anello. La scadenza di una previsione (180 secondi) riattiva il fallback programmato.

Nella vista fermata vengono mostrati come live soltanto gli eventi espliciti riferiti al passaggio selezionato. Non vengono creati ETA propagati da altre fermate o righe di presenza “In attesa” senza una previsione diretta. I normali orari programmati restano il fallback già previsto quando manca il live.

Previsioni e posizioni provengono da feed distinti: il timestamp del pacchetto GPS non è una prova che il riferimento alla prossima fermata sia più recente. L’icona usa gli stessi orari live della vista fermata, con aggiornamenti validi per 180 secondi: quando il passaggio previsto è trascorso avanza al tratto successivo, anche se il GPS indica ancora la fermata precedente o manca il prossimo ETA. Una partenza live ancora futura impedisce di saltare una fermata in cui il bus è in sosta. Il calcolo si ripete ogni 10 secondi anche se il pacchetto del feed non è cambiato; nuovi ETA possono rinviare il passaggio, mentre lo storico impedisce arretramenti dopo l’avanzamento.

Il feed può omettere le fermate iniziali già percorse. Un passaggio live esplicito della stessa vettura/corsa, trascorso da non più di tre minuti, permette di avanzare al tratto immediatamente successivo anche quando mancano eventi precedenti o il capolinea è `NO_DATA`. Se manca un passaggio recente, per superare il prefisso servono due fermate consecutive con eventi espliciti e ordinati; la prima previsione deve essere fra tre minuti fa e dieci minuti avanti. Un ETA futuro isolato o un ritardo propagato alle fermate omesse non autorizzano salti. Tempi assoluti, ritardi espliciti e riferimenti `stop_id`/`stop_sequence` sono interpretati con le stesse funzioni per arrivi e percorso, incluse le fermate ripetute.

Una riassegnazione live univoca della stessa vettura a un’altra corsa, più recente della posizione, esclude l’icona dalla corsa precedente; un aggiornamento live ancora valido per la corsa attuale la mantiene visibile anche se è già pubblicata la successiva. Le posizioni conservate per un’omissione o un errore del feed non vengono fatte avanzare soltanto perché una previsione è trascorsa.

Per verificare un errore reale, toccare la vettura e scegliere **Condividi dati della vettura**: il pannello di condivisione contiene fermata visualizzata, dati del marker e i record pubblici VehiclePosition/TripUpdate del mezzo. La lettura avviene su richiesta tramite `/api/vehicles/NUMERO/diagnostics`; non viene inviato alcun messaggio automaticamente. I test riproducono PAVESE/COLOMBO ma non sostituiscono la verifica del feed effettivo.

Il server web e l’API usano aiohttp: un processo serve le risposte già in cache con I/O asincrono e riserva otto thread (`WEB_THREADS`) ai calcoli mancanti e ai file. Le attese sullo stesso risultato condividono un calcolo; la disconnessione di un client non lo cancella per gli altri. Feed, cache e storico delle vetture rimangono condivisi nel processo. Le risposte live vengono riutilizzate soltanto nello stesso secondo e invalidate da un nuovo feed, per rivalutare ETA e scadenza delle icone anche quando la fonte non cambia. Percorsi, metadati delle fermate e sequenze statiche vengono riutilizzati e invalidati automaticamente dopo l’importazione del database. I feed sono indicizzati per corsa, vettura e linea. Le letture SQLite sono accodate per evitare il rallentamento delle scansioni simultanee; download e risposte già in cache restano indipendenti. JSON e risorse testuali supportano gzip; i file con nome fingerprinted hanno cache lunga, mentre HTML e manifest vengono rivalidati. Avvio, porta e proxy rimangono compatibili; `WEB_SERVER=waitress` abilita il precedente percorso WSGI. Aggiornamento e prove di carico sono in [deploy/README.md](deploy/README.md).

Gli arrivi restano apribili anche con un backend precedente che non fornisce routeId/variantId: il client risolve linea e direzione dai dati disponibili, oppure apre una scelta esplicita. Se il numero vettura non è fornito dal servizio viene indicato come non disponibile, invece di nascondere il campo. La risposta `/api/status` e quella degli arrivi includono `apiVersion: 2` nel backend aggiornato. Verifica del fallback client: `npm run test:client`.

Il simbolo dell’app è lo stesso autobus rosso usato nell’itinerario (`assets/bus-front.png`): compare nella home e all’avvio. Le icone native, favicon e icona web usano il bus su sfondo bianco. Expo Go può mostrare l’icona al posto dello splash nativo: l’aspetto finale dello splash richiede una build release per la verifica.


L’immagine del bus viene decodificata una sola volta per itinerario, con limite 96×96 pixel, e condivisa come `ImageRef` fra tutte le miniature. Il cambio di riga usa la bitmap già pronta, con placeholder identico e transizione a zero, per evitare un nuovo caricamento visibile. La cache dell’immagine è indipendente dalla validità delle posizioni del feed. `expo-image` è incluso in Expo Go SDK 58.

## Versione web installabile sul PC di casa

La stessa app può funzionare senza Expo Go: `npm run build:web`, poi
`avvia-web-windows.cmd` su Windows. Sito e API sono serviti insieme sulla porta 8000.
La guida completa per Safari, icona sulla Home e rete domestica è in [WEB-WINDOWS.md](WEB-WINDOWS.md).
