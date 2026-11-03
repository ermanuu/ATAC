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
