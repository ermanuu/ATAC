# ATAC · Autobus Roma per iPhone

Prima versione di un’app indipendente Expo / React Native, con un backend Python che legge gli open data di Roma Servizi per la Mobilità. Il nome del progetto non implica affiliazione con ATAC o Roma Mobilità.

Per provarla gratuitamente da Windows su iPhone, segui [la guida passo passo](PROVA-IPHONE-WINDOWS.md). Non serve Apple Developer a pagamento.

## Funzionalità

La home mostra il logo ATAC aggiornato con ROMA · AUTOBUS sotto, titolo, sottotitolo e tre pulsanti: **Cerca linea**, **Cerca fermata**, **Calcola percorso**. Fuori dalla home una barra flottante inferiore permette di passare fra Linee/Fermate/Percorso, anche nei dettagli di linee e fermate. I ritorni restano in alto a sinistra; nel percorso il titolo linea-direzione è fisso al centro e Cambia Direzione è a destra. Le partenze sono una riga orizzontale compatta e le fermate si aprono con la freccia accanto al nome.

Lo stile usa superfici traslucide, sfocatura, bordi luminosi e sfondo sfumato. I controlli flottanti usano `expo-glass-effect` con Liquid Glass nativo quando entrambe le verifiche API/runtime confermano la compatibilità (iOS 26+); altrove usano `expo-blur`. Con “Riduci trasparenza” di iOS le superfici diventano opache. I tre moduli Expo aggiunti sono inclusi in Expo Go SDK 58. L’effetto nativo e le impostazioni di accessibilità vanno verificati su iPhone: il controllo in browser verifica il fallback.

- Ritorno fisso alla home in alto a sinistra nelle tre categorie. Le ultime dieci linee aperte vengono salvate sul dispositivo e mostrate per prime nei risultati compatibili con la ricerca.
- Ricerca delle linee autobus, scelta della direzione e delle varianti di percorso, partenze dal capolinea da 10 minuti fa a un’ora avanti ed elenco delle fermate.
- Miniature rosse frontali dei bus, preparate dal riferimento fornito e precaricate in memoria con `expo-image`, a sinistra delle fermate: alla fermata se fermi, nel tratto precedente se in arrivo. Posizioni dal feed GTFS Realtime, dettaglio veicolo e apertura in Mappe di Apple; eventuali associazioni GPS approssimate sono marcate con ≈.
- Fermate preferite salvate sul dispositivo: aggiunta/rimozione tramite stella nel dettaglio, elenco nella scheda Fermate e apertura diretta degli arrivi.
- Tocco su una fermata del percorso per gli arrivi delle linee nelle prossime due ore, senza limite di 20 risultati. Gli arrivi live precedono i programmati; per una stessa linea, direzione pubblica e giornata di servizio, i programmati sono mostrati solo in assenza di live. Le diverse vetture live rimangono visibili. La vista mostra minuti d’attesa, orari, numero vettura accanto alla previsione live quando disponibile, aggiornamento automatico/manuale e ritorno fisso alla direzione selezionata. Toccando una linea in arrivo si apre il suo itinerario nella direzione della corsa, con le posizioni dei relativi bus. Previsioni live quando presenti, altrimenti orari esplicitamente programmati; corse cancellate e fermate saltate vengono escluse.
- Calcolo dell’itinerario fra due fermate usando orari GTFS e calendario effettivo, con cambi e corse oltre mezzanotte.
- Nessun dato dimostrativo nell’app. Feed indisponibili o scaduti producono stati espliciti, senza simulare il servizio.

## Fonti

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

I feed live vengono letti su richiesta, con cache di 10 secondi per posizioni e previsioni. Direzione e arrivi si aggiornano ogni **10 secondi**. Il pulsante flottante ↻ nella linea resta visibile mentre si scorre e mostra l’indicatore durante l’aggiornamento, anche automatico. Il pulsante e il trascinamento verso il basso richiedono nuove copie dei feed, saltando la cache del backend; anche il ritorno alla direzione rilegge la fonte. Le richieste lente vengono completate prima di iniziare un altro aggiornamento. Gli arrivi entro un minuto sono indicati come **In arrivo**.

Le icone non allungano la distanza fra le fermate. Le posizioni attuali hanno una misura non più vecchia di 90 secondi. Un’omissione temporanea del feed viene tollerata per 45 secondi; le posizioni conservate, quelle fra 90 e 180 secondi e quelle visibili durante un errore di richiesta sono indicate come ultima posizione nota nel dettaglio della vettura. Nessuna icona resta oltre tre minuti dalla misura originale e i timestamp delle previsioni devono essere ancora validi: una nuova risposta non ringiovanisce la vecchia posizione.

Il backend ricorda l’avanzamento mostrato per vettura, percorso e istanza di corsa. Un riferimento che arretra, una previsione mancante o un GPS temporaneamente non associabile conservano l’ultima collocazione come posizione nota fino alla sua scadenza. Un ETA ancora futuro impedisce a GPS o storico di collocare l’icona oltre quella fermata; una previsione più recente può correggere un’icona che era stata mostrata troppo avanti. Le risposte precedenti non possono annullare questa correzione. Una nuova corsa, data di servizio o ora iniziale azzera lo storico. Questa memoria è locale al processo backend e si azzera al riavvio.

Se manca il timestamp del veicolo, un nuovo timestamp globale del feed non ringiovanisce una misura identica; una firma conservata per sei ore dall’ultima presenza impedisce che ricompaia dopo la scadenza dello storico. La fermata `stop_id` prevale su contatori di sequenza discordanti; nei percorsi ad anello la sequenza distingue le occorrenze della stessa fermata. Il GPS può correggere un riferimento bloccato quando la proiezione è sufficientemente vicina e non ambigua, ma non fa arretrare un riferimento valido verso una fermata precedente. Nei dettagli si legge l’orario della misura, con i secondi. I numeri vettura usano soltanto `VehicleDescriptor.label`, destinato al pubblico; ID tecnici di veicolo, entità e corsa non vengono presentati come matricole. In assenza di label compare “non disponibile” (— nell’icona).

Gli ETA live sono verdi; quelli programmati restano neutri. L’API mantiene le corse programmate come fallback e deduplica soltanto la stessa istanza di corsa/fermata/data. Il client mette i live prima e usa i programmati per direzioni senza live; non confonde due vetture live o passaggi diversi di un percorso ad anello. La scadenza di una previsione (180 secondi) riattiva il fallback programmato.

Le fermate omesse da un TripUpdate ereditano il ritardo live dell’ultimo evento precedente, secondo GTFS Realtime, fino al prossimo aggiornamento esplicito. Un tempo assoluto prevale sul campo delay; NO_DATA interrompe la propagazione e SKIPPED esclude la fermata. Per la 74354 è quindi possibile usare la partenza live dal capolinea 74353, anziché mostrare il solo orario programmato, mentre la 74355 mantiene la propria previsione diretta. Gli ETA propagati sono indicati come **Live · stima** e scadono con l’aggiornamento di origine.

Se il GPS rileva la vettura al capolinea ma non esiste alcuna previsione valida, viene mostrato il solo stato **Live · al capolinea · vettura …**, con **In attesa**, senza un orario o conto alla rovescia ricavati dal programma. La presenza richiede la stessa corsa e giornata di servizio, un numero vettura non ambiguo e una misura valida entro 180 secondi; se presente, il GPS deve essere vicino al capolinea. La dicitura scade usando il timestamp della posizione e non viene nascosta da un’altra vettura con ETA live nella stessa direzione.

Previsioni e posizioni provengono da feed distinti: il timestamp del pacchetto GPS non è una prova che il riferimento alla prossima fermata sia più recente. L’icona usa gli stessi orari live della vista fermata, con aggiornamenti validi per 180 secondi: quando il passaggio previsto è trascorso avanza al tratto successivo, anche se il GPS indica ancora la fermata precedente o manca il prossimo ETA. Una partenza live ancora futura impedisce di saltare una fermata in cui il bus è in sosta. Il calcolo si ripete ogni 10 secondi anche se il pacchetto del feed non è cambiato; nuovi ETA possono rinviare il passaggio, mentre lo storico impedisce arretramenti dopo l’avanzamento.

Il feed può omettere le fermate iniziali già percorse. Per superare questo prefisso servono due fermate consecutive con eventi espliciti e ordinati della stessa vettura/corsa; la prima previsione deve essere fra tre minuti fa e dieci minuti avanti. Il primo evento può quindi essere appena trascorso senza bloccare l’icona a monte. Un ETA isolato più avanti non autorizza salti; dopo un evento passato si può avanzare soltanto al tratto immediatamente successivo, finché mancano informazioni sulle altre fermate. Tempi assoluti, ritardi e riferimenti `stop_id`/`stop_sequence` sono interpretati con le stesse funzioni per arrivi e percorso, incluse le fermate ripetute.

Per verificare un errore reale, toccare la vettura e scegliere **Condividi dati della vettura**: il pannello di condivisione contiene fermata visualizzata, dati del marker e i record pubblici VehiclePosition/TripUpdate del mezzo. La lettura avviene su richiesta tramite `/api/vehicles/NUMERO/diagnostics`; non viene inviato alcun messaggio automaticamente. I test riproducono PAVESE/COLOMBO ma non sostituiscono la verifica del feed effettivo. L’API HTTP inclusa è un server di sviluppo, non un deployment di produzione.

Gli arrivi restano apribili anche con un backend precedente che non fornisce routeId/variantId: il client risolve linea e direzione dai dati disponibili, oppure apre una scelta esplicita. Se il numero vettura non è fornito dal servizio viene indicato come non disponibile, invece di nascondere il campo. La risposta `/api/status` e quella degli arrivi includono `apiVersion: 2` nel backend aggiornato. Verifica del fallback client: `npm run test:client`.

Il simbolo dell’app è lo stesso autobus rosso usato nell’itinerario (`assets/bus-front.png`): compare nella home e all’avvio. Le icone native, favicon e icona web usano il bus su sfondo bianco. Expo Go può mostrare l’icona al posto dello splash nativo: l’aspetto finale dello splash richiede una build release per la verifica.


L’immagine del bus viene decodificata una sola volta per itinerario, con limite 96×96 pixel, e condivisa come `ImageRef` fra tutte le miniature. Il cambio di riga usa la bitmap già pronta, con placeholder identico e transizione a zero, per evitare un nuovo caricamento visibile. La cache dell’immagine è indipendente dalla validità delle posizioni del feed. `expo-image` è incluso in Expo Go SDK 58.

## Versione web installabile sul PC di casa

La stessa app può funzionare senza Expo Go: `npm run build:web`, poi
`avvia-web-windows.cmd` su Windows. Sito e API sono serviti insieme sulla porta 8000.
La guida completa per Safari, icona sulla Home e rete domestica è in [WEB-WINDOWS.md](WEB-WINDOWS.md).
