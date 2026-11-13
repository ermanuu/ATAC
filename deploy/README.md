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

Se sulla VM sono stati copiati a mano i file della bozza Metro, conservarli
una sola volta prima del primo aggiornamento da GitHub. Questo evita che
`git pull` si interrompa per modifiche locali o file ancora non tracciati:

```sh
sudo git -C /opt/romabus stash push --include-untracked -m 'Backup bozza Metro manuale' -- \
  server/infomobility.py server/metro_cache.py server/requirements-browser.txt \
  'scripts/*atac*' 'scripts/*metro*' 'deploy/systemd/romabus-metro*' \
  src/components/Infomobility.tsx
sudo aggiorna-romabus
```

La copia resta nello stash locale. Il codice verificato viene fornito dal
repository aggiornato; non riapplicare lo stash dopo l'aggiornamento.
Il profilo Firefox, i cookie e i dati in `server/data/` restano nei loro
percorsi. Il lettore Metro già attivo continua a funzionare durante
l'aggiornamento del sito. Le esecuzioni successive richiedono soltanto
`sudo aggiorna-romabus`.

Metro usa il servizio JSON della home ATAC: `POST https://www.atac.roma.it/Service/WebService.asmx/GetPrimaryLinesData`, con corpo `{"languageName":"it"}`. Le segnalazioni consultano il feed RSS pubblico `https://www.atac.roma.it/feeds/stato-del-servizio-in-tempo-reale`; News consulta `https://romamobilita.it/wp-json/wp/v2/infomobilita` e `https://romamobilita.it/wp-json/wp/v2/primo-piano`. La VM deve poter raggiungere in HTTPS `www.atac.roma.it` e `romamobilita.it`. Non servono token. Il lettore browser opzionale aggiunge Playwright e il suo Firefox. Le API `/api/metro` e `/api/news` permettono di verificare le fonti anche senza un database GTFS importato. Una fonte irraggiungibile è segnalata nelle pagine interessate e non blocca posizioni, partenze e arrivi dei bus.

Lo script installato aggiorna anche le unità systemd prima di riavviare il sito.

## Verificare l'accesso ATAC dalla VM

Eseguire nel terminale SSH della VM. Questa prova non richiede aggiornamenti del
codice né riavvii e usa gli stessi header e il corpo JSON del backend:

```sh
curl -sS --max-time 20 \
  -H 'User-Agent: ROMABUS/1.0 (independent transit app)' \
  -H 'Accept: application/json, application/rss+xml, text/xml' \
  -H 'Content-Type: application/json' \
  -H 'Cache-Control: no-cache' \
  --data '{"languageName":"it"}' \
  -o /tmp/romabus-atac-check.json \
  -w 'HTTP %{http_code}\nTipo %{content_type}\n' \
  'https://www.atac.roma.it/Service/WebService.asmx/GetPrimaryLinesData'
```

`HTTP 200` con tipo `application/json` indica una risposta JSON da verificare nel
file `/tmp/romabus-atac-check.json`. Un redirect `302`, un errore `403` o una
risposta HTML richiedono di controllare il blocco del sito: dal cloud ATAC
reindirizza a un CAPTCHA e non restituisce i dati. Il risultato dalla VM può
essere diverso perché usa un altro indirizzo IP. Il comando non segue i
redirect e non tenta di risolvere il CAPTCHA automaticamente.

### Prova del widget con un browser senza interfaccia grafica

Sulla VM il browser Firefox interattivo ha restituito HTTP 200 e i quattro
record Metro attesi; le richieste dirette continuano a ricevere il redirect
al CAPTCHA. Per verificare il funzionamento senza una sessione SSH grafica,
`scripts/check-atac-browser.py` osserva la richiesta POST effettuata dal widget
della home in Firefox Playwright. La prova non esporta cookie, non risolve
CAPTCHA e non modifica il backend in esecuzione.

Se il file non è ancora nel checkout della VM, copiarlo separatamente, per
esempio in `/root/check-atac-browser.py` con il pannello SFTP di MobaXterm.
Preparare un ambiente isolato dall'applicazione:

```sh
python3 -m venv /root/romabus-atac-test/venv
/root/romabus-atac-test/venv/bin/python -m pip install playwright==1.64.1
/root/romabus-atac-test/venv/bin/python -m playwright install --with-deps firefox
/root/romabus-atac-test/venv/bin/python /root/check-atac-browser.py --profile /root/romabus-atac-test/profile
```

L'installer scarica Firefox Playwright e installa le librerie di sistema
necessarie; il pacchetto Firefox Snap già presente non viene usato. Il profilo
è dedicato alla prova e va conservato sulla VM. L'output mostra codice HTTP,
tipo della risposta e i campi pubblici delle linee Metro. Un timeout o una
risposta HTML/redirect indica che la lettura automatica non è verificata.
`--headed` permette una prova visibile nella sessione X11, con lo stesso
profilo dedicato. Sulla VM anche il browser Playwright visibile ha mostrato
il CAPTCHA. Per lasciare il browser aperto durante la verifica manuale,
copiare la versione aggiornata dello script sulla VM e usare:

```sh
/root/romabus-atac-test/venv/bin/python /root/check-atac-browser.py --profile /root/romabus-atac-test/profile --headed --manual
```

Completare personalmente l'eventuale CAPTCHA e premere Submit nel browser.
Quando compare la home ATAC, premere Invio nel terminale: la prova mantiene
la stessa pagina e attende fino a tre minuti un nuovo aggiornamento automatico
del widget, che normalmente si aggiorna ogni due minuti. Le risposte dei POST
iniziati prima della conferma vengono ignorate, anche quando arrivano dopo.
Non vengono aperte altre schede né ricaricata la pagina dopo Invio. Se la
verifica non riporta alla home, non viene riportato un esito positivo.
La sola presenza della home non conferma l'accesso al servizio JSON: un
redirect o un errore del widget rende la prova non verificata.
Un successo dopo questa procedura conferma soltanto la sessione verificata:
per controllare se rimane utilizzabile senza finestra, ripetere il comando
originale senza `--headed --manual`, con lo stesso profilo. Non avviare le
due prove contemporaneamente sullo stesso profilo.

Un esito positivo soltanto con `--headed` non conferma il funzionamento senza
interfaccia grafica. L'utente ha successivamente confermato HTTP 200 anche
senza finestra con il profilo verificato. I test opzionali del progetto usano
Chromium locale contro un server di prova; questa conferma dal vivo riguarda
la VM e la sessione provata, non una durata garantita dell'autorizzazione.

## Lettore continuo Metro sulla VM

Questa installazione è opzionale e presuppone che il codice aggiornato sia
disponibile in `/opt/romabus`. La copia del solo diagnostico in `/root` non
aggiorna il backend. I comandi seguenti sono una procedura di installazione:
non sono stati eseguiti dal cloud e non pubblicano codice su GitHub.

Il servizio `romabus-metro-browser.service` gira come utente `romabus`, con un
profilo privato in `/var/lib/romabus-metro/profile`. Mantiene aperto un solo
Firefox senza finestra e osserva i POST generati dal widget ogni due minuti,
senza ricaricare la pagina a ogni raccolta. Il browser non viene avviato
dalle richieste dei visitatori. Il backend legge il file pubblico
`/opt/romabus/server/data/metro-browser.json` quando è configurato
`ATAC_METRO_SNAPSHOT`. I cookie restano nel profilo privato sulla VM.

### Preparazione senza attivazione

Chiudere le prove che usano il profilo sorgente, poi eseguire:

```sh
cd /opt/romabus
sudo bash scripts/install-metro-browser.sh --profile-source /root/romabus-atac-test/profile
```

Lo script installa le dipendenze da `server/requirements-browser.txt`, scarica
Firefox in `/var/lib/romabus-metro/browsers`, copia il profilo verificato solo
se manca quello di servizio e ne assegna la proprietà a `romabus`. Conserva il
profilo sorgente. Prepara servizio e drop-in del backend con copie di backup
dei file modificati, senza avviare il lettore né riavviare il sito.
Per esaminare soltanto i file di configurazione, senza pacchetti né profili:

```sh
DESTDIR=/tmp/romabus-metro-stage bash scripts/install-metro-browser.sh
```

### Verifica e attivazione

Se era stato installato il precedente timer che riapriva Firefox a ogni
raccolta, disabilitarlo prima di avviare il nuovo lettore:

```sh
sudo systemctl disable --now romabus-metro-browser.timer
sudo systemctl stop romabus-metro-browser.service
```

La sessione copiata va verificata sotto l'utente del servizio prima
dell'attivazione sul sito:

```sh
sudo systemctl start romabus-metro-browser.service
sudo journalctl -u romabus-metro-browser.service -n 20 --no-pager
sudo -u romabus .venv/bin/python -c 'from server.metro_cache import read_snapshot; s=read_snapshot("/opt/romabus/server/data/metro-browser.json"); print({k:v for k,v in s.items() if k != "data"}); assert s["available"]'
```

Il servizio usa `Type=notify`: `systemctl start` attende la prima risposta
JSON valida e poi il processo resta `active (running)`. Il watchdog verifica
che il lettore continui a elaborare eventi. Un errore temporaneo può provocare
un riavvio dopo due minuti; l'uscita 3 indica una verifica manuale richiesta
e impedisce riavvii automatici ripetuti al CAPTCHA.

Prima di attivarlo sul sito, lasciare il servizio in prova per almeno 15 minuti
e controllare che aumentino i messaggi `Metro: lettura verificata #...`, con
uno snapshot ancora disponibile. La prova precedente si è interrotta dopo
circa undici minuti: un solo successo non dimostra continuità.

```sh
sudo journalctl -u romabus-metro-browser.service -n 20 --no-pager
sudo systemctl status romabus-metro-browser.service --no-pager
```

Una volta decisa l'attivazione della modifica, aggiornare la copia web e attivare:

```sh
sudo -u romabus npm run build:web
sudo systemctl enable romabus-metro-browser.service
sudo systemctl restart romabus
curl -fsS http://127.0.0.1:8000/api/metro
systemctl status romabus-metro-browser.service --no-pager
```

La risposta deve indicare `available: true` con i quattro stati e l'orario
della verifica. Il client consulta questa risposta ogni 30 secondi. Anche
`fresh=1` rilegge il file già disponibile: il nuovo download ATAC viene
eseguito dal widget nel browser mantenuto aperto. Non dipende da MobaXterm
o da una sessione SSH aperta.

### Scadenza della sessione e nuova verifica manuale

In caso di CAPTCHA, HTML, errore di rete o formato inatteso, la raccolta
scrive `available: false` conservando data e dettagli dell'ultimo successo.
Il backend mostra subito gli stati come non verificabili. Se il lettore si
ferma o non riesce a scrivere il file, la copia scade comunque dopo cinque
minuti dalla lettura originale, anche se viene riletta o copiata. Il browser
non risolve automaticamente nuove verifiche. Dalla sessione MobaXterm con
X11 attivo, eseguire il comando di ripristino:

```sh
sudo bash /opt/romabus/scripts/verify-metro-browser.sh
```

Il comando controlla X11 prima di fermare il lettore, prepara l'autorizzazione
grafica per l'utente `romabus` e apre il profilo del servizio. Completare
personalmente l'eventuale CAPTCHA, premere Submit e, quando compare la home,
premere Invio nel terminale. Attendere il successivo aggiornamento del widget
nella stessa pagina, fino a tre minuti. Solo dopo una lettura JSON valida il
comando riavvia il lettore senza finestra e mostra la risposta dell'API Metro.
Se la verifica del widget fallisce, il comando si ferma, conserva la data
dell'ultimo successo e marca i dati come non verificabili. Il sito non viene
riavviato da questo comando.

### Disabilitare il lettore browser

```sh
sudo systemctl disable --now romabus-metro-browser.service
sudo rm /etc/systemd/system/romabus.service.d/metro-browser.conf
sudo systemctl daemon-reload
sudo systemctl restart romabus
```

Questo rimuove la scelta dello snapshot e riattiva il metodo HTTP diretto,
che sulla VM provata riceve un redirect al CAPTCHA. Se esisteva una precedente
configurazione con quel nome, ripristinare la copia `.backup.*` al posto della
rimozione. Profili e cookie restano sulla VM e non vengono inclusi nel codice.

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
