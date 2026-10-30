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

L’accesso diretto alle fonti è attualmente bloccato dalla policy di rete cloud (403 del proxy). Non sono quindi ancora verificati contenuti attuali, disponibilità, corrispondenza degli ID o condizioni di riutilizzo. Prima della distribuzione occorre verificare licenza e attribuzione sulla pagina ufficiale. I feed non sono inclusi nel repository.

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

I feed live vengono letti su richiesta: cache di 10 secondi per le posizioni e 30 secondi per le previsioni. Direzione e arrivi si aggiornano ogni **30 secondi**. Trascinare verso il basso aggiorna i dati visibili e richiede nuove copie dei feed, saltando la cache del backend; anche il ritorno alla direzione rilegge la fonte. Le richieste lente vengono completate prima di iniziare un altro aggiornamento.

Le icone non allungano la distanza fra le fermate. Vengono mostrate solo posizioni presenti nell’ultimo feed valido, con misura non più vecchia di 90 secondi: lo storico interno per omissioni/errori non viene disegnato come posizione attuale. Se manca il timestamp del veicolo, un nuovo timestamp globale del feed non ringiovanisce una misura identica; una firma conservata per sei ore dall’ultima presenza impedisce che ricompaia dopo la scadenza dello storico. Le risposte precedenti non fanno arretrare una posizione più recente. La fermata `stop_id` prevale su contatori di sequenza discordanti; nei percorsi ad anello la sequenza distingue le occorrenze della stessa fermata. Il GPS può correggere un riferimento bloccato quando la proiezione è sufficientemente vicina e non ambigua (≈), ma non fa arretrare un riferimento valido verso una fermata precedente. Nei dettagli si legge l’orario della misura, con i secondi. I numeri vettura usano soltanto `VehicleDescriptor.label`, destinato al pubblico; ID tecnici di veicolo, entità e corsa non vengono presentati come matricole. In assenza di label compare “non disponibile” (— nell’icona).

Gli ETA live sono verdi; quelli programmati restano neutri. L’API mantiene le corse programmate come fallback e deduplica soltanto la stessa istanza di corsa/fermata/data. Il client mette i live prima e usa i programmati per direzioni senza live; non confonde due vetture live o passaggi diversi di un percorso ad anello. La scadenza di una previsione (180 secondi) riattiva il fallback programmato.

Previsioni e posizioni provengono da feed distinti: il timestamp del pacchetto GPS non è una prova che il riferimento alla prossima fermata sia più recente. Per il prossimo arrivo previsto la vista usa lo stesso limite di validità degli arrivi (180 secondi), anche se il pacchetto GPS è successivo. Una sequenza iniziale di fermate omesse può essere superata se la stessa vettura/corsa ha almeno due fermate future consecutive esplicite, con la prima entro 10 minuti: questo interpreta un aggiornamento che conserva soltanto le fermate future. Un ETA isolato più avanti o un buco intermedio/NO_DATA non autorizzano il salto. Il dettaglio distingue “Prossima fermata da previsioni live” da posizione GPS e riporta entrambi i timestamp; Mappe apre le sole coordinate rilevate. Il collegamento dei riferimenti `stop_id`/`stop_sequence` è condiviso fra arrivi e percorso, incluse le fermate ripetute.

Per verificare un errore reale, toccare la vettura e scegliere **Condividi dati della vettura**: il pannello di condivisione contiene fermata visualizzata, dati del marker e i record pubblici VehiclePosition/TripUpdate del mezzo. La lettura avviene su richiesta tramite `/api/vehicles/NUMERO/diagnostics`; non viene inviato alcun messaggio automaticamente. I test riproducono PAVESE/COLOMBO ma non sostituiscono la verifica del feed effettivo. L’API HTTP inclusa è un server di sviluppo, non un deployment di produzione.

Gli arrivi restano apribili anche con un backend precedente che non fornisce routeId/variantId: il client risolve linea e direzione dai dati disponibili, oppure apre una scelta esplicita. Se il numero vettura non è fornito dal servizio viene indicato come non disponibile, invece di nascondere il campo. La risposta `/api/status` e quella degli arrivi includono `apiVersion: 2` nel backend aggiornato. Verifica del fallback client: `npm run test:client`.

Il logo fornito dall’utente è stato preparato come asset locale in `assets/atac-logo.png`, con sfondo trasparente e una versione quadrata bianca per l’icona (`assets/atac-app-icon.png`). Compare sopra ROMA · AUTOBUS nella home, nella vista JS iniziale durante il caricamento dell’immagine e nello splash nativo configurato con expo-splash-screen. Non richiede download esterni all’avvio. Expo Go può mostrare l’icona al posto dello splash nativo: l’aspetto finale dello splash richiede una build release per la verifica.


L’immagine del bus viene decodificata una sola volta per itinerario, con limite 96×96 pixel, e condivisa come `ImageRef` fra tutte le miniature. Il cambio di riga usa la bitmap già pronta, con placeholder identico e transizione a zero, per evitare un nuovo caricamento visibile. La cache dell’immagine è indipendente dalla validità delle posizioni del feed. `expo-image` è incluso in Expo Go SDK 58.
