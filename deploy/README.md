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

## Configurazione per 100 visitatori contemporanei

La configurazione di base è pensata per una VM con **2 vCPU e 4 GB di RAM**:
un processo Waitress, otto thread di elaborazione, fino a 256 connessioni aperte,
feed aggiornati in background ogni 10 secondi e cache condivise nel processo.
Non avviare più processi indipendenti per aumentare il numero di worker:
duplicherebbero i download, le cache e lo storico delle vetture.

Dopo il merge in `main` basta il comando già usato:

```sh
sudo aggiorna-romabus
sudo systemctl status romabus --no-pager
```

Lo script installa anche Waitress da `server/requirements.txt`. L’avvio resta
`npm run serve:web` (oppure `.venv/bin/python -m server.web`), sulla porta già
configurata. HTTPS e il reverse proxy della VM continuano a inoltrare alla stessa
porta. Non occorrono Redis, un nuovo database o modifiche ai timer.

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
