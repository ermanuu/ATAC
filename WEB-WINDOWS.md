# Roma Autobus sul Wi-Fi di casa

Questa versione usa Safari: non servono Expo Go, account Expo o Apple Developer.
Il PC Windows ospita sia il sito sia i dati. Deve restare acceso, con il servizio aperto.

## Prima installazione o aggiornamento

Scarica lo ZIP aggiornato del repository da GitHub ed estrailo in `C:\ATAC`.
Conserva `.env`, `.venv` e soprattutto `server\data`: contiene gli orari già importati.
Se il progetto non è mai stato configurato, esegui prima `setup-windows.cmd`.

Dal Prompt dei comandi:

```bat
cd /d C:\ATAC
npm ci
npm run build:web
avvia-web-windows.cmd
```

Se il vecchio backend occupa già la porta 8000, fermalo con Ctrl+C prima di avviare il sito.
Il comando di build prepara la versione web; ripetilo dopo ogni aggiornamento del codice.
Non modifica `.env`: il sito usa automaticamente il proprio indirizzo per chiamare i dati.

## Aprirla su iPhone

1. Collega PC e iPhone alla stessa rete Wi-Fi (evita la rete ospiti con isolamento).
2. Sul PC verifica `http://localhost:8000` nel browser.
3. In un altro Prompt esegui `ipconfig` e cerca l'indirizzo IPv4 della scheda connessa, per esempio `192.168.1.20`.
4. In Safari sull'iPhone apri **http://192.168.1.20:8000**, sostituendo l'indirizzo con quello del PC.
5. Da Condividi scegli **Aggiungi alla schermata Home**; se compare, lascia attiva l'opzione di apertura come app web.

Consenti Python su **reti private** se Windows Firewall lo chiede. Se la pagina non si apre,
controlla che il profilo della rete domestica sia Privato e che Python sia consentito su quel profilo.
Non è necessario aprire porte sul modem.

Avvia nuovamente `avvia-web-windows.cmd` quando riaccendi il PC. Per fermare il servizio premi Ctrl+C.
Se cambia l'IP del PC, aggiorna l'indirizzo e ricrea l'icona; puoi prenotare un IP al PC nel router.
I preferiti della versione web sono salvati nel browser per quell'indirizzo: non vengono trasferiti da Expo Go.

## Limiti e accesso fuori casa

Questa configurazione HTTP è pensata per il Wi-Fi domestico fidato; non rende il sito privato con una password.
Gli altri dispositivi della stessa rete possono raggiungerlo. Non pubblicare la porta 8000 su Internet.
Su iOS puoi aggiungere il sito alla Home; alcuni browser richiedono HTTPS per l'installazione completa.
L'aspetto glass è quello web, mentre dati live e percorsi richiedono il PC e la connessione attivi.
Non vengono salvate risposte live in una cache offline.

Per usarla in seguito fuori casa, configura Tailscale su PC e iPhone e un indirizzo HTTPS privato
con Tailscale Serve. Non occorrono modifiche al codice della web app; questa procedura non configura
né installa Tailscale sul tuo PC.
