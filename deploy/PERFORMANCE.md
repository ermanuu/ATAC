# Verifica del carico — 3 novembre 2026

La verifica riguarda 100 visitatori che consultano linee e fermate con un poll
ogni 10 secondi: circa 10 richieste API al secondo. Non è una misura eseguita
sulla VM pubblica `romabus.duckdns.org`.

## Ambiente e metodo

- Server Waitress con un processo, otto thread e affinità limitata a due CPU.
- Database GTFS reale da 646 MiB e snapshot completi dei feed di Roma Mobilità.
- Snapshot riprodotti facendo avanzare insieme clock e timestamp, con 200 ms di
  ritardo simulato per download. Nessun carico inviato alla fonte o al sito pubblico.
- Quarantatré endpoint: dettagli di 20 linee, arrivi a una fermata per linea,
  ricerca linee/fermate e stato del servizio.
- Client HTTP con gzip; la prova misura richieste e risposte API, senza rendering
  dei browser, rete mobile, reverse proxy pubblico o TLS.

Le linee sono 706, 714, 64, 40, 90, 170, 913, 310, 60, 80, 719, 23, 70, 46,
30, 38, 61, 63, 105 e 492. Per le prove sono stati preparati i percorsi degli
endpoint in un processo separato; il primo test parte con cache del server vuote.

## Risultati

| Prova | Richieste | Errori | Mediana | p95 | Massimo |
| --- | ---: | ---: | ---: | ---: | ---: |
| 100 aperture simultanee, cache vuote | 100 | 0 | 2.22 s | 3.37 s | 3.47 s |
| 100 visitatori, poll ogni 10 s per un minuto | 600 | 0 | 25 ms | 136 ms | 485 ms |
| 100 visitatori, poll ogni 5 s per 30 s | 600 | 0 | 47 ms | 307 ms | 681 ms |

Il picco RSS osservato per il processo server è stato circa 273 MiB, esclusi
client di prova e cache del filesystem del sistema operativo.

Nell’ultima prova è stato eseguito anche un calcolo di percorso. Quel calcolo
ha richiesto circa 18 secondi; le altre pagine hanno continuato a rispondere con
i tempi riportati. Il routing rimane un lavoro costoso: l’API ammette un calcolo
alla volta e risponde con un invito a riprovare agli altri calcoli non già in
cache, mantenendo liberi i thread per le pagine live.

I report numerici sono in [load-test-results.json](load-test-results.json).
I feed e il database non sono inclusi nel repository.

## Portata del risultato

La prova conferma il carico descritto nell’ambiente cloud e distingue le aperture
iniziali dalle richieste a regime. Due CPU nell’ambiente di prova non equivalgono
necessariamente alle due vCPU della VM: tempi di CPU, disco e rete possono variare.
Un minuto di traffico non dimostra la stabilità per giorni né la capacità con
altre distribuzioni di linee e calcoli di percorso.

Per la verifica sulla VM da 2 vCPU e 4 GB usare il comando in [README.md](README.md),
controllando anche CPU, RAM ed errori del servizio. I test automatici verificano
separatamente concorrenza dei download, cache, invalidazione del database,
scadenza delle posizioni e avanzamento delle icone.

## Generatore asincrono per 10.000 visitatori

Il client aggiornato usa coroutine e un insieme limitato di connessioni HTTP
riutilizzate. La verifica del generatore ha eseguito **20.000 richieste** con
10.000 utenti virtuali in 20 secondi, 256 connessioni massime, zero errori e
circa 1.000 richieste al secondo. Il processo client ha raggiunto circa 60 MiB
di RAM e quattro thread, incluso un thread aggiunto per osservare le risorse.

Questa verifica usa un endpoint HTTP locale di prova con risposte JSON compresse,
su un ambiente cloud senza affinità imposta alle CPU. Misura il generatore;
non dimostra la capacità della webapp o della VM pubblica con 10.000 utenti.
Il report è in [load-generator-validation.json](load-generator-validation.json).

Le prove limitate ai core condivisi dell’ambiente cloud hanno completato le
richieste ma sono rimaste sotto il carico previsto. Il report le ha segnalate
con `load_target_met=false` anche in assenza di errori HTTP. Per interpretare
una prova ad alto carico occorre quindi considerare il traffico effettivamente
inviato, il ritardo dello scheduler e la coda del client. Confrontare i nuovi
tempi anche tenendo conto del riuso delle connessioni, assente nel vecchio client.

## Backend HTTP asincrono — 4 novembre 2026

Il campionamento della VM fornito durante la diagnosi mostra il processo Python
vicino al 100% di una vCPU per lunghi tratti, con circa 3,1 GiB di memoria ancora
disponibile e poca attesa disco. Le risposte API già in cache richiedono poco
lavoro applicativo: una misura interna ha eseguito 10.000 chiamate in circa
0,19 secondi, esclusa la gestione HTTP.

Il nuovo avvio serve le risposte pronte direttamente con aiohttp. Solo un
calcolo mancante o un file viene affidato al pool, limitato da `WEB_THREADS`.
Le richieste sullo stesso risultato attendono un unico calcolo senza occupare
altri thread. La cancellazione di un lettore non cancella quel calcolo per
gli altri; alla chiusura vengono rimossi anche i lavori accodati cancellati.
Un processo conserva feed e storico comuni, e le regole di scadenza della cache
e delle posizioni restano invariate.

Il confronto seguente usa HTTP locale, cinque linee e dieci endpoint, database
GTFS reale e gli stessi snapshot completi riprodotti con timestamp avanzati e
200 ms di ritardo simulato per download. Il catalogo viene preparato prima della
misura. L’ambiente cloud ha affinità CPU libera e non equivale alla VM da due
vCPU; non sono compresi Internet, TLS, Caddy o rendering dei browser.

| Percorso HTTP | Finestra | Richieste | Errori | Avviate nella finestra | p95 complessivo |
| --- | ---: | ---: | ---: | ---: | ---: |
| Waitress, misura iniziale | 20 s | 19.998 | 4 | 16.906 | 4,38 s |
| aiohttp, confronto breve | 20 s | 20.000 | 0 | 20.000 | 0,37 s |
| aiohttp, minuto completo | 60 s | 60.000 | 0 | 60.000 | 0,90 s |

Il minuto completo ha raggiunto il carico previsto di 1.000 richieste al secondo,
senza timeout nella coda del client. Il p95 della fase HTTP è stato 256 ms;
il p95 complessivo include anche l’attesa del generatore. Il massimo RSS del
server osservato dopo le prove è circa 96 MiB. I risultati sono in
[http-runtime-load-test.json](http-runtime-load-test.json).

Questo conferma il profilo riprodotto localmente e non garantisce qualsiasi
distribuzione di 10.000 visitatori reali: viste diverse, ricerche, calcoli di
percorso e rete modificano il carico. Dopo il merge e `sudo aggiorna-romabus`,
ripetere dal PC la stessa prova pubblica con 256 connessioni e confrontare
richieste inviate, errori, tempi e CPU. La porta e la configurazione Caddy non
richiedono modifiche per usare il nuovo avvio.

Sono stati superati 159 test backend e 23 test client, oltre a lint e verifica
TypeScript. I test includono risposta da cache con tutti i worker occupati,
richieste concorrenti sullo stesso calcolo, cancellazione di un lettore,
invalidazione del database importato, gzip, HEAD, ETag e identificativi codificati.
È stato verificato anche l’avvio reale `python -m server.web`: HTML e API hanno
risposto HTTP 200, con entrambi i feed disponibili nel controllo puntuale.

## Cache degli orari alle fermate — ricostruzione del 5 novembre 2026

La correzione precedente indicata come `7d42dc6` non è presente nel checkout
pubblicato e il relativo ZIP non è recuperabile. Questa è una nuova modifica
basata su `61105ac`; non recupera quel commit né ne conferma le misure.

Gli arrivi riutilizzano i candidati statici per fermata, versione del database
e minuto. La query include fino a 59 secondi aggiuntivi in avanti; ogni richiesta
riapplica esattamente la finestra originale prima di elaborare il realtime.
Le righe vengono copiate prima dell'arricchimento live: nuove previsioni,
cancellazioni, scadenze e numeri vettura non contaminano gli orari conservati.
La cache HTTP continua a rivalutare gli arrivi ogni secondo e dopo nuovi feed.
La sostituzione atomica del GTFS invalida i candidati; la cache è limitata a
256 voci e un peso di 200.000 righe, contando anche le sequenze delle corse.
Il peso è un limite sul numero di righe, non una misura in byte.

Confronto CPU riproducibile, dalla radice del checkout:

```sh
.venv/bin/python scripts/benchmark-stop-schedule.py
```

Il benchmark usa GTFS **sintetico isolato**, 200 corse alla stessa fermata e 200
aggiornamenti live, senza download. Confronta la funzione originale di `61105ac`
con quella nuova per 60 secondi logici, verifica l'uguaglianza delle 60 risposte
e misura cinque coppie di prove in ordine alternato. Le sequenze statiche delle
corse sono già calde per entrambi; la cache degli arrivi parte vuota in ogni prova.

| CPU per 60 chiamate, mediana di cinque prove | Risultato |
| --- | ---: |
| Versione `61105ac` | 0,530 s |
| Nuova cache | 0,138 s |
| Riduzione nel solo scenario sintetico | 73,95% |

Dati delle prove in [stop-schedule-benchmark.json](stop-schedule-benchmark.json).
Non sono misure HTTP o della VM, né confermano il precedente miglioramento del
52%. Non è stata ripetuta la prova da 60.000 richieste o dimostrata la capacità
con 10.000 utenti. Dopo l'eventuale pubblicazione del codice e aggiornamento
della VM occorre ripetere il test pubblico a 512 connessioni, confrontando
`load_target_met`, richieste avviate nella finestra, errori, latenza e CPU.

Verifiche della nuova modifica: 165 test backend e 23 client superati, lint e
TypeScript superati. Sei nuovi test coprono riuso fra secondi, separazione di
fermate/minuti, aggiornamento/scadenza/cancellazione live e isolamento delle
mutazioni, estremi temporali esatti, invalidazione dopo importazione e calendario
dopo mezzanotte. Nessuna pubblicazione GitHub o modifica alla VM eseguita.
