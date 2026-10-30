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

- **Linee**: cerca una linea, apri il percorso e controlla le posizioni dei bus quando presenti.
- **Fermate**: cerca una fermata; distingue le previsioni live dagli orari programmati.
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
