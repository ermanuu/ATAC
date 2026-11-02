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
