# Prova su iPhone con un PC Windows

Non serve un account Apple Developer a pagamento. Il progetto usa Expo SDK 58 e moduli inclusi in Expo Go. La versione SDK deve coincidere con quella supportata dall’app Expo Go installata sull’iPhone.

## 1. Installa gli strumenti

- Su iPhone, installa **Expo Go** dall’App Store.
- Sul PC, installa **Node.js 24 LTS** da https://nodejs.org e **Python 3.12 o successivo** da https://www.python.org/downloads/windows/ (includi il launcher `py`).
- Estrai tutto il progetto in una cartella, per esempio `C:\ATAC`. Non eseguire i file direttamente dentro lo ZIP.
- Collega PC e iPhone alla stessa rete Wi-Fi privata. Le reti ospiti possono impedire il collegamento fra dispositivi.

## 2. Installa il progetto e scarica i dati

Apri **Prompt dei comandi** nella cartella del progetto. Per esempio:

```bat
cd /d C:\ATAC
setup-windows.cmd
```

Attendi il messaggio di installazione completata. Il programma installa le dipendenze e scarica il GTFS dal sito ufficiale di Roma Mobilità. Se il download fallisce, fermati all’errore: i dati non vengono sostituiti con dati dimostrativi. La restrizione del proxy cloud non si applica al tuo PC, ma la disponibilità del sito va comunque verificata dal PC.

## 3. Trova l’indirizzo del PC

Nel Prompt dei comandi esegui:

```bat
ipconfig
```

Nella scheda **Wi-Fi**, annota **Indirizzo IPv4**, per esempio `192.168.1.20`. Usa l’indirizzo effettivo del tuo PC, non quello di una scheda VPN o virtuale.

## 4. Avvia il servizio dati

Sempre dalla cartella del progetto:

```bat
set API_HOST=0.0.0.0
npm run api
```

Lascia questa finestra aperta. Se Windows chiede il permesso di accesso alla rete, consenti solo la rete privata di casa.

Su Safari dell’iPhone visita **http://INDIRIZZO-DEL-PC:8000/api/status**, sostituendo l’indirizzo. È una verifica sulla tua rete locale, non un link ospitato dal cloud.

Dovresti vedere un testo JSON. `staticAvailable` e `serviceToday` devono essere `true`; `vehicles.available` e `updates.available` indicano separatamente se i feed live funzionano. Il semplice caricamento della pagina non garantisce il funzionamento del servizio trasporti.

Se Safari non apre la pagina, controlla l’indirizzo, che il servizio sia ancora aperto, i permessi sulla rete privata e che la rete Wi-Fi non isoli i dispositivi. Non disabilitare il firewall: autorizza soltanto Python sulla rete privata. Non aprire porte del router verso Internet.

## 5. Avvia l’app

Apri una **seconda finestra del Prompt dei comandi**, nella cartella del progetto, e scrivi:

```bat
cd /d C:\ATAC
set EXPO_PUBLIC_API_URL=http://192.168.1.20:8000
set EXPO_NO_TELEMETRY=1
npm start -- --lan
```

Sostituisci `192.168.1.20` con il tuo IPv4 reale. Per questa prova locale Expo Go permette HTTP; un backend distribuito su Internet dovrà usare HTTPS. La variabile va impostata prima dell’avvio di Expo. Se cambi indirizzo, arresta Expo con Ctrl+C e riavvialo.

Quando appare il QR, inquadralo con **Fotocamera** su iPhone e tocca **Apri in Expo Go**. Consenti a Expo Go l’accesso alla rete locale. Se Windows lo chiede, autorizza Node.js solo sulla rete privata. Se il QR rimanda a una development build, premi `s` nel terminale per passare a Expo Go e scansiona il nuovo QR.

Mantieni entrambe le finestre aperte durante la prova. `localhost` e `127.0.0.1` sull’iPhone indicano il telefono, non il PC: non usarli come indirizzo del backend.

## 6. Cosa provare

All’apertura trovi l’intestazione originale e sotto i tre pulsanti della home. Nelle ricerche compaiono soltanto le schede Linee/Fermate/Percorso in alto. Nei dettagli il ritorno in alto a sinistra rimane visibile durante lo scorrimento.

- **Linee**: cerca una linea, scegli la direzione e consulta le partenze dal capolinea (−10 / +60 minuti). Nell’elenco fermate, le miniature a sinistra indicano i bus fermi o in arrivo; toccale per i dettagli, oppure tocca una fermata per gli arrivi.
- **Fermate**: cerca una fermata oppure tocca la freccia accanto al nome di una fermata del percorso. Mostra tutti gli arrivi disponibili di tutte le linee nelle prossime due ore, con attesa e orario. Usa “Aggiorna arrivi” per ricaricare e il tasto fisso “Torna alla linea” per riprendere la direzione selezionata. Quando disponibile, il numero vettura compare dopo “Previsione live”. Toccando una linea in arrivo si apre direttamente il suo itinerario e l’elenco dei bus in transito.
- **Percorso**: seleziona due fermate e calcola un itinerario solo autobus. Il calcolo usa gli orari programmati, non il traffico live.

Se i feed live non sono raggiungibili, l’app lo indica; senza GTFS importato le ricerche non sono disponibili. Aggiorna gli orari con `npm run data:import` prima della prova o almeno ogni giorno.

## Stato delle verifiche

TypeScript, lint, test del backend e bundle JavaScript iOS sono verificabili nel cloud. L’esecuzione dei comandi Windows, l’apertura su un iPhone fisico e l’accesso attuale ai feed dal PC devono ancora essere verificati: questo documento non li dichiara già riusciti. Non è un’installazione permanente o una pubblicazione su App Store: l’app gira dentro Expo Go mentre il PC fornisce codice e dati.

## Se Expo Go segnala SDK 58 ma il progetto usa SDK 57

Arresta Expo con Ctrl+C. Dal repository GitHub, nel browser autenticato, scarica lo ZIP aggiornato di `main`. Estrai lo ZIP in una cartella separata e copia soltanto `package.json` e `package-lock.json` nella cartella esistente `C:\ATAC`, sostituendo i due file. Mantieni il database degli orari, la correzione Python Windows e le configurazioni locali.

Poi nel Prompt dei comandi, un comando alla volta:

```bat
cd /d C:\ATAC
npm ci
npm start -- --clear --lan
```

Mantieni `EXPO_PUBLIC_API_URL` impostato nel terminale prima di riavviare. Lascia il backend aperto nell’altra finestra. Se un comando termina con errore, fermati e conserva il messaggio. Non usare `--force` o `--legacy-peer-deps`. La sostituzione del lockfile evita conflitti con vecchie risoluzioni delle dipendenze SDK 57. Dopo l’aggiornamento, scansiona il nuovo QR con Expo Go per SDK 58.

## Aggiornamento della sezione Linee

Arresta backend ed Expo con Ctrl+C nelle rispettive finestre. Scarica dal browser autenticato lo ZIP aggiornato di GitHub ed estrailo in una cartella separata. Copia `App.tsx`, la cartella `src` e i file della cartella `server` dentro `C:\ATAC`, unendo le cartelle e sostituendo i file. Conserva `server\data`, `.venv` e le impostazioni locali. Non è necessaria una nuova importazione degli orari per questo aggiornamento.

Riavvia il backend nella prima finestra con `set API_HOST=0.0.0.0` e `npm run api`. Nella seconda mantieni `EXPO_PUBLIC_API_URL` con l’indirizzo del PC e avvia `npm start -- --clear --lan`, poi scansiona il nuovo QR. Occorre aggiornare sia il backend sia l’app: il nuovo elenco di direzioni usa l’API aggiornata.

Le posizioni dei bus vengono rilette ogni 15 secondi e le misure più vecchie di 90 secondi vengono indicate in grigio come ultima posizione nota; tutte scadono dopo 180 secondi. Le vetture omesse da un aggiornamento vengono conservate per un massimo di 45 secondi dall’ultima presenza, mantenendo il timestamp originale. Nel dettaglio del bus è visibile il timestamp con i secondi. Se il GPS contraddice la vecchia fermata, l’app può aggiornare la collocazione in modo approssimato (≈); se la fonte ripete le stesse coordinate, non viene simulato uno spostamento. Per queste modifiche aggiornare anche `server`, oltre a `App.tsx` e all’intera cartella `src`.

Se una riga degli arrivi non apriva l’itinerario, aggiorna `App.tsx` e tutta `src`: il nuovo client gestisce anche le risposte del vecchio servizio. Per vedere i numeri vettura disponibili occorre aggiornare anche tutta `server` e riavviare il backend: `http://IP-DEL-PC:8000/api/status` deve contenere `"apiVersion": 2`. Il campo “vettura non disponibile” significa che il servizio non ha fornito un’identificazione utilizzabile; non è un numero da stimare.

## Aggiornamento del logo e dell’avvio

Dallo ZIP GitHub aggiornato copia `App.tsx`, tutta `assets`, `app.json`, `package.json` e `package-lock.json` nella cartella del progetto. Arresta Expo con Ctrl+C, esegui `npm ci`, poi `npm start -- --clear --lan` mantenendo la variabile del backend. Il logo è visibile sotto ROMA · AUTOBUS nella home e nella breve vista di caricamento JS. In Expo Go la schermata nativa può mostrare l’icona dell’app: lo splash completo configurato sarà verificabile in una build release. Questo aggiornamento non richiede modifiche ai dati degli autobus.


## Aggiornare home, direzioni e linee recenti

1. Ferma backend ed Expo con Ctrl+C nelle due finestre.
2. Scarica [lo ZIP di main](https://github.com/ermanuu/ATAC/archive/refs/heads/main.zip) dal browser con accesso a GitHub ed estrailo in una cartella separata.
3. Copia in `C:\ATAC` i file `App.tsx`, `package.json`, `package-lock.json`, tutta `src` e i file di `server` (incluso il nuovo `positions.py`). Unisci le cartelle e sostituisci i file. **Conserva `server\data`, `.venv` e `.env`**: non eliminare la cartella del progetto. Non occorre reimportare gli orari.
4. Esegui `npm ci` dentro `C:\ATAC`: aggiunge la memoria persistente delle ultime dieci linee aperte, compatibile con Expo Go SDK 58.
5. Prima finestra:

```bat
cd /d C:\ATAC
set API_HOST=0.0.0.0
npm run api
```

6. Seconda finestra: sostituisci l’IP di esempio con l’IPv4 del tuo PC (`ipconfig`).

```bat
cd /d C:\ATAC
set EXPO_PUBLIC_API_URL=http://192.168.1.20:8000
npm start -- --clear --lan
```

Apri il nuovo QR in Expo Go. Nelle tre categorie trovi Home in alto a sinistra. Dopo aver aperto una linea, questa comparirà per prima nelle ricerche compatibili, anche dopo la chiusura dell’app. Le direzioni proposte hanno corse programmate già in viaggio o in partenza entro un’ora, secondo il calendario GTFS. Le partenze restano nella finestra da −10 a +60 minuti.


## Aggiornare logo, barra inferiore e stile Liquid Glass

Arresta Expo con Ctrl+C. Dal nuovo ZIP di `main` copia in `C:\ATAC` `App.tsx`, tutta `src` (inclusa la nuova cartella `ui`), tutta `assets`, `package.json` e `package-lock.json`. Mantieni `server\data`, `.venv` e `.env`.

Dentro `C:\ATAC` esegui:

```bat
npm ci
npm start -- --clear --lan
```

Mantieni `EXPO_PUBLIC_API_URL` impostato all’IP del PC e il backend aperto nell’altra finestra. Questo aggiornamento grafico non richiede una nuova importazione degli orari né modifiche al backend. La barra inferiore compare in tutte le schermate fuori dalla home. Liquid Glass nativo richiede un iPhone e un runtime compatibili (iOS 26+); sugli altri sistemi viene usato il vetro sfocato. Se hai attivato “Riduci trasparenza” nelle impostazioni Accessibilità di iOS, le superfici sono opache.
