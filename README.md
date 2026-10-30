# ATAC · Autobus Roma per iPhone

Prima versione di un’app indipendente Expo / React Native, con un backend Python che legge gli open data di Roma Servizi per la Mobilità. Il nome del progetto non implica affiliazione con ATAC o Roma Mobilità.

Per provarla gratuitamente da Windows su iPhone, segui [la guida passo passo](PROVA-IPHONE-WINDOWS.md). Non serve Apple Developer a pagamento.

## Funzionalità

- Ricerca delle linee autobus, scelta della direzione e delle varianti di percorso, partenze dal capolinea da 10 minuti fa a un’ora avanti ed elenco delle fermate.
- Miniature dei bus a sinistra delle fermate: alla fermata se fermi, nel tratto precedente se in arrivo. Posizioni dal feed GTFS Realtime, dettaglio veicolo e apertura in Mappe di Apple; eventuali associazioni GPS approssimate sono marcate con ≈.
- Tocco su una fermata del percorso per tutti gli autobus in arrivo di tutte le linee nelle prossime due ore, senza limite di 20 risultati. La vista mostra minuti d’attesa, orari, aggiornamento automatico/manuale e ritorno alla direzione selezionata. Previsioni live quando presenti, altrimenti orari esplicitamente programmati; corse cancellate e fermate saltate vengono escluse.
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

Il calcolo è solo autobus, fra fermate selezionate, con cambi alla stessa fermata e margine di 2 minuti; considera partenze nelle prossime 4 ore. Non include indirizzi, cammino, metropolitana, accessibilità, frequenze non basate su orari o ottimizzazione del percorso in base al traffico. I tempi live sono visibili alle fermate ma non ricalcolano gli itinerari. Le direzioni con sequenze di fermate diverse sono scelte separate. Le miniature sono collocate tramite corsa e sequenza/ID della fermata; se questi riferimenti mancano, solo i bus di una direzione non ambigua possono essere associati al percorso. Per le corse note, il GPS può indicare approssimativamente la fermata più vicina entro 500 metri; le posizioni ambigue o troppo distanti non sono collocate. Alert e deviazioni non sono ancora integrati.

I feed live vengono letti su richiesta con cache di 30 secondi. Feed e singole posizioni più vecchi di 180 secondi non sono presentati come live. È necessario validare questi criteri contro il feed effettivo. L’API HTTP inclusa è un server di sviluppo, non un deployment di produzione.
