# Aggiornamento giornaliero sulla VM

Questa configurazione usa il checkout `/opt/romabus`, l’utente `romabus` e il
servizio web `romabus` già presenti sulla VM. Node/npm devono essere disponibili
all’utente del servizio in `/usr/local/bin` o `/usr/bin`; il backend usa la
virtualenv `/opt/romabus/.venv`.

Dopo aver integrato la modifica in `main`, esegui una sola volta:

```sh
sudo aggiorna-romabus
sudo bash /opt/romabus/scripts/install-data-refresh.sh
```

Il primo comando scarica i nuovi file. Il secondo installa e attiva il timer
`romabus-data-import.timer`, oltre ad aggiornare
`/usr/local/bin/aggiorna-romabus`. Le versioni precedenti dei file modificati
vengono conservate accanto agli originali con suffisso `.backup.*`.
Le esecuzioni successive dell’installer sono idempotenti.

Da quel momento il timer esegue `npm run data:import` ogni giorno alle **04:00
nel fuso Europe/Rome**, anche dopo un riavvio. Il calendario segue automaticamente
ora solare e ora legale. Se la VM era spenta all’orario previsto, `Persistent=true`
recupera l’esecuzione saltata quando il timer viene riattivato.

L’importazione gira come `romabus`, senza riavviare il sito. Il database viene
sostituito solo dopo un’importazione riuscita; in caso di errore resta quello
precedente. Su Linux il lock `server/data/.import.lock` impedisce sovrapposizioni
con altre importazioni da CLI o con lo script di aggiornamento. Il servizio
ha un limite di 30 minuti, comprensivo dell’eventuale attesa del lock.

Per i successivi aggiornamenti del codice basta il consueto comando:

```sh
sudo aggiorna-romabus
```

Lo script installato aggiorna anche le unità systemd prima di riavviare il sito.

## Verifica ed esecuzione manuale

Controlla la prossima esecuzione:

```sh
systemctl list-timers romabus-data-import.timer
```

Avvia subito un’importazione e consulta l’esito:

```sh
sudo systemctl start romabus-data-import.service
sudo systemctl status romabus-data-import.service --no-pager
sudo journalctl -u romabus-data-import.service -n 50 --no-pager
```

Il servizio è `oneshot`: dopo un’importazione riuscita torna inattivo; il timer
resta attivo. Per confermare l’esito puoi controllare `Result` ed `ExecMainStatus`:

```sh
systemctl show romabus-data-import.service -p Result -p ExecMainStatus
curl -fsS http://127.0.0.1:8000/api/status
```

`Result=success` ed `ExecMainStatus=0` indicano il completamento del comando;
`staticImportedAt`, `staticAvailable` e `serviceToday` nella risposta dell’API
permettono di verificare il dataset. I feed live continuano ad aggiornarsi
separatamente, come prima.

Per disattivare il solo aggiornamento giornaliero:

```sh
sudo systemctl disable --now romabus-data-import.timer
```

## Server della VM e prove di carico

La configurazione di base è pensata per una VM con **2 vCPU e 4 GB di RAM**:
un processo aiohttp serve le risposte già in cache direttamente con I/O asincrono;
un pool di otto thread esegue i calcoli mancanti e le letture dei file. I client
che attendono lo stesso risultato condividono il lavoro senza occupare altri
thread. Feed e storico delle vetture rimangono unici nel processo, con i feed
aggiornati in background ogni 10 secondi.
Non avviare più processi indipendenti per aumentare il numero di worker:
duplicherebbero i download, le cache e lo storico delle vetture.

Dopo il merge in `main` basta il comando già usato:

```sh
sudo aggiorna-romabus
sudo systemctl status romabus --no-pager
```

Lo script installa le dipendenze da `server/requirements.txt`. L’avvio resta
`npm run serve:web` (oppure `.venv/bin/python -m server.web`), sulla porta già
configurata. HTTPS e il reverse proxy della VM continuano a inoltrare alla stessa
porta. Non occorrono Redis, un nuovo database o modifiche ai timer.

`WEB_THREADS` controlla il pool dei calcoli, non il numero di utenti o di
connessioni HTTP. La cache live continua a essere rivalutata ogni secondo e
invalidata dai nuovi feed. Se un client si disconnette, l’attesa viene cancellata
senza interrompere un calcolo condiviso con altri lettori. L’arresto del servizio
ferma i lettori dei feed e chiude il pool. Per ripristinare il vecchio percorso
WSGI, impostare temporaneamente `WEB_SERVER=waitress` nell’ambiente del servizio
e riavviarlo; il valore predefinito è `aiohttp`.

Le cache del catalogo contengono al massimo 200.000 righe fermata/corsa; quelle
delle sequenze richieste dagli arrivi altre 100.000 righe. La cache delle risposte
serializzate ha limite di 8 MiB e quella degli asset 16 MiB. Ogni cache ha anche
un limite al numero di elementi; i risultati troppo grandi non vengono trattenuti.
La sostituzione atomica del database giornaliero cambia la generazione del dataset
e invalida i risultati precedenti. Le cache non modificano i timestamp live.
I refresh ravvicinati condividono il download per due secondi; oltre questo limite
un refresh manuale può saltare la normale cache di 10 secondi.

Il calcolo dei percorsi usa una lettura indipendente del database, così una
scansione lunga non occupa il blocco delle letture live. È ammesso un calcolo alla
volta: durante quel lavoro un altro calcolo non già disponibile in cache riceve
un messaggio che invita a riprovare, senza occupare tutti i thread del server.
I risultati completati si riutilizzano per cinque secondi. Il motore di routing
rimane l’operazione più lenta e non è dimensionato per cento calcoli simultanei.

### Ripetere la prova sulla VM

Eseguire sul server, dopo l’aggiornamento:

```sh
cd /opt/romabus
.venv/bin/python scripts/load-test.py --users 100 --duration 60 --interval 10 --output /tmp/romabus-load.json
```

Il comando simula 100 visitatori con un aggiornamento ogni 10 secondi, distribuiti
tra dettagli delle linee e arrivi alle fermate. Le cinque linee predefinite sono
706, 714, 64, 40 e 90; il catalogo viene preparato prima della misura. `--lines`
accetta altri numeri separati da virgole. Il test usa HTTP locale, evitando la
rete esterna e il TLS, mentre l’istanza continua a scaricare normalmente i feed.
Per avviare tutti i visitatori nello stesso momento aggiungere `--burst`.
`--paths-file` accetta una lista JSON di percorsi `/api/` già scelti, evitando la
preparazione iniziale delle linee.

Il report mostra richieste, errori e percentili dei tempi di risposta. Verificare
zero errori, un p95 entro un secondo a regime e CPU/RAM senza crescita continua;
le aperture a cache vuote possono richiedere più tempo. Ripetere con le linee
effettivamente più usate e con il reverse proxy pubblico prima di attribuire
alla distribuzione una capacità garantita. Il test dei poll non simula cento
calcoli di percorso simultanei o il rendering dei browser.

I risultati misurati nell’ambiente cloud sono in [PERFORMANCE.md](PERFORMANCE.md).

### Prova con 10.000 utenti virtuali

Il generatore asincrono accetta fino a 10.000 visitatori virtuali e riutilizza
un insieme limitato di connessioni HTTP. Non crea un thread o una connessione
per ciascun visitatore. L’aggiornamento con `sudo aggiorna-romabus` installa
automaticamente anche la dipendenza `aiohttp`.

```sh
cd /opt/romabus
.venv/bin/python scripts/load-test.py --users 10000 --duration 60 --interval 10 --connections 256 --output /tmp/romabus-load-10000.json
```

Questa prova pianifica 60.000 richieste in un minuto, circa 1.000 al secondo.
`--connections` imposta il numero massimo di richieste HTTP attive del client,
indipendentemente dal numero di utenti virtuali. `--burst` allinea i poll di
tutti gli utenti e produce ondate di 10.000 richieste, anziché distribuirle
uniformemente nei dieci secondi.

Per misurare la sola capacità del server, eseguire il generatore da un’altra
macchina con il repository e le dipendenze installate, aggiungendo
`--base-url https://romabus.duckdns.org`. Il test avviato sulla VM condivide CPU
e RAM con il server e misura il costo di entrambi. Le prove da Internet includono
anche HTTPS, il reverse proxy e la rete.

Il report distingue:

- `target_requests_per_second`: carico previsto dalla configurazione.
- `offered_requests_per_second`: richieste effettivamente avviate nella finestra
  di misura; `missed_requests` conta quelle mancanti rispetto al piano.
- `errors`: errori HTTP, di rete o timeout dopo l’avvio della richiesta.
- `generator_queue_timeouts`: poll scaduti aspettando una connessione del client.
- `latency_ms`: attesa complessiva, inclusa la coda del client;
  `http_latency_ms` misura il tempo dalla disponibilità di una connessione.
- `client_queue_ms` e `scheduler_lag_ms`: coda e ritardo del generatore.

Ogni visitatore attende la conclusione di un poll lento prima di riprendere i
successivi; i poll saltati restano visibili nel confronto con il piano. I timeout
comprendono sia la coda del client sia la richiesta HTTP. `drain_seconds` indica
il tempo usato dopo la finestra di misura per completare richieste già iniziate.

`load_target_met` è vero se almeno il 99% dei poll previsti viene avviato nella
finestra configurata. Il comando termina con codice 1 se questo obiettivo non
è raggiunto o se ci sono errori o timeout in coda: zero errori HTTP da solo non
dimostra che il server abbia ricevuto tutto il carico richiesto. Le connessioni
riutilizzate rendono i tempi del nuovo client diversi dai test precedenti che
aprivano una connessione per ogni richiesta.
