# Analisi e piano di evoluzione di ha iliadbox

**Analisi storica della versione 0.10.4.** I difetti sotto descrivono il codice di partenza. Le correzioni e le nuove funzioni sono ora implementate nel branch di sviluppo; la mappa aggiornata e le istruzioni di test sono in [DEVELOPMENT.md](DEVELOPMENT.md).

Il progetto ha già una buona copertura delle funzioni quotidiane: presenza LAN, traffico, sensori del router, controllo Wi-Fi, accessi ospiti e pannello dedicato. Il miglioramento più utile è rendere affidabili autenticazione, aggiornamenti parziali e gestione delle credenziali, quindi aggiungere diagnosi di rete e automazioni più evolute.

La proposta è mantenere l'integrazione locale e compatibile con le entità esistenti, sviluppandola in cinque incrementi verificabili. Una riscrittura completa non è necessaria.

## Versione e perimetro

- Repository: [Bassysta/ha-iliadbox](https://github.com/Bassysta/ha-iliadbox).
- Revisione analizzata: `2ffa682`, versione `0.10.4`, scaricata il 21 novembre 2026.
- Copia locale: `/home/frapas/ILIAD_HA`.
- Analisi di tutti i moduli Python, dei due componenti frontend, delle traduzioni, della configurazione HACS e della CI.
- Prove isolate sul codice originale con risposte sintetiche. Non è stata eseguita un'istanza completa di Home Assistant né una prova su un router reale.
- Al momento dell’analisi iniziale il codice era quello scaricato. Le prove isolate sono state successivamente sostituite dalla suite di regressione in `tests/`.

Le priorità sono: **P1** per affidabilità, credenziali e identità del router; **P2** per correttezza dei dati e compatibilità; **P3** per manutenzione e usabilità. Le nuove funzioni che richiedono endpoint del router sono proposte subordinate alla verifica sul modello e firmware effettivi.

## Aspetti da preservare

Il client è asincrono e riceve la sessione HTTP da Home Assistant. Il coordinatore concentra le letture, le entità hanno identificatori stabili e il progetto distingue almeno in parte errori di rete, autorizzazione e permessi. Il flusso di configurazione, la riconfigurazione e le riparazioni guidate costituiscono una base utile.

Sono corrette anche la generazione delle password con `secrets`, la selezione esplicita dei campi delle radio per escludere le chiavi principali e l'esclusione delle password dagli attributi dei sensori ospiti. Le azioni WebSocket privilegiate controllano il ruolo amministratore. Queste protezioni vanno mantenute ed estese agli altri canali.

## Difetti riprodotti

### A01 Errori temporanei trasformati in credenziali non valide

**P1 · `api.py:171–188` · tre casi riprodotti.**

`open_session()` converte qualsiasi `IliadboxError` della richiesta di apertura sessione in `IliadboxAuthError`. Questo include timeout, errori TLS e un router temporaneamente occupato. Il setup e il coordinatore interpretano poi l'errore come necessità di riautorizzare l'integrazione.

Correggere la classificazione: rete e indisponibilità devono conservare la propria natura; la riautorizzazione deve scattare solo per errori di credenziali pertinenti. Applicare attese progressive ai guasti temporanei e rispettare eventuali indicazioni di rate limit. Evitare ritentativi automatici indiscriminati di creazioni ospiti e riavvii, il cui risultato può essere incerto dopo un timeout. Home Assistant distingue esplicitamente errori recuperabili di setup ed errori di autenticazione nella [documentazione sugli errori](https://developers.home-assistant.io/docs/integration_setup_failures/).

**Criterio di accettazione:** un timeout durante il login si risolve con un nuovo tentativo; una revoca effettiva del token richiede nuovamente l'autorizzazione.

### A02 Risposte JSON inattese causano eccezioni non gestite

**P2 · `api.py:130,236` · due casi riprodotti.**

Una risposta JSON valida ma di tipo lista genera `AttributeError` sia in discovery sia nelle richieste API. Il client presuppone un dizionario e non valida lo schema. Inoltre `_request()` non verifica esplicitamente lo stato HTTP prima di interpretare il corpo, a differenza di `discover()`.

Validare struttura e campi obbligatori alle frontiere del client, distinguere errori HTTP e messaggi del router, conservare codice e percorso senza includere segreti. Rifiutare una discovery priva degli elementi necessari anziché assumere che qualsiasi JSON rappresenti un router compatibile.

**Criterio di accettazione:** HTML, JSON inatteso, corpo vuoto, HTTP 429 e 5xx producono errori classificati senza traceback incontrollati.

### A03 Un errore opzionale cancella dati sani

**P1 · `coordinator.py:72–79`; `sensor.py:608–614` · due casi riprodotti.**

Radio e accessi ospiti sono letti insieme. Se una delle due letture fallisce, entrambe diventano liste vuote. Nei test un errore degli ospiti cancella radio sane; un errore delle radio cancella ospiti sani. Il callback delle entità ospiti interpreta l'assenza come revoca e rimuove le entità dal registro.

Separare gli esiti delle letture e distinguere tre condizioni: elenco vuoto confermato, funzione non supportata e lettura fallita. Conservare l'ultimo campione valido con timestamp e stato di freschezza; rendere indisponibili le sole entità interessate. Rimuovere entità soltanto dopo una lettura autorevole che ne confermi l'assenza.

**Criterio di accettazione:** un guasto temporaneo del sottosistema ospiti non cambia radio o registro delle entità; la successiva lettura valida ripristina lo stato.

### A04 Radio diverse sulla stessa banda si sovrascrivono

**P2 · `api.py:270–308`; `coordinator.py:112` · un caso riprodotto.**

Il client restituisce una voce per BSS, ma il coordinatore usa la banda come chiave unica. Due voci `5G` con 2 e 3 client diventano una sola voce con 3 client. Il problema si manifesta se il router espone più BSS o radio sulla stessa banda; la frequenza reale sui modelli Iliad va verificata.

Conservare gli identificatori AP/BSS, distinguere radio fisiche e reti logiche, definire come aggregare i client senza contarli due volte. Migrare gli identificatori delle entità già create quando necessario. Attualmente le entità radio vengono aggiunte solo durante il setup: una discovery dinamica deve gestire anche radio inizialmente non disponibili.

**Criterio di accettazione:** due radio o BSS sulla stessa banda restano distinguibili e una radio scoperta dopo il setup compare senza ricaricare l'integrazione.

### A05 La scadenza ospiti dipende dal momento della lettura

**P2 · `sensor.py:589–595` · un caso riprodotto.**

Il sensore calcola `ora attuale + remaining` ogni volta che viene letto. Rileggendo lo stesso campione cinque minuti dopo, la scadenza avanza di cinque minuti. L'arrotondamento al minuto non elimina il problema.

Calcolare e memorizzare una scadenza assoluta alla ricezione del campione, preferendo un timestamp autorevole del router se disponibile. Evitare che una rilettura della cache o un aggiornamento mancato prolunghi apparentemente l'accesso.

**Criterio di accettazione:** la scadenza non cambia quando il campione è identico, anche durante una temporanea indisponibilità.

### A06 Password ospiti nelle notifiche globali

**P1 · `guest.py:116–124`; `image.py`; `services.py` · contenuto della notifica riprodotto.**

La creazione di un accesso inserisce sempre la password in una notifica persistente. Le notifiche standard non costituiscono un canale riservato all'amministratore: il relativo [codice di Home Assistant](https://github.com/home-assistant/core/blob/2024.11.0/homeassistant/components/persistent_notification/__init__.py) restituisce le notifiche alle connessioni autenticate senza un filtro amministratore. Il limite nel pannello WebSocket quindi non protegge questo percorso.

L'immagine QR è abilitata per impostazione predefinita e comunica anch'essa la password a chi può leggerla; questa esposizione è già documentata nel README. I servizi personalizzati non contengono lo stesso controllo amministratore dei WebSocket. I controlli delle entità seguono invece le autorizzazioni standard di Home Assistant: va definita una politica coerente, preservando l'uso legittimo nelle automazioni.

Eliminare i segreti dalle notifiche generiche; mostrare password e QR su richiesta autorizzata. Rendere esplicita e facoltativa la condivisione tramite entità immagine. Verificare anche risposte dei servizi e tracce delle automazioni. Non si tratta di un accesso anonimo da Internet: il problema riguarda la separazione tra utenti dell'istanza HA.

**Criterio di accettazione:** test con amministratore, utente ordinario e automazione; nessuna password nei canali generici quando la condivisione non è stata abilitata.

### A07 Notifiche di box diversi condividono lo stesso identificatore

**P2 · `guest.py:123,133` · un caso riprodotto.**

L'identificatore della notifica include soltanto l'ID dell'accesso. Due box con accesso `1` usano entrambi `iliadbox_guest_1`: una creazione può sovrascrivere la notifica dell'altro e una revoca può rimuoverla.

Includere `entry_id` nell'identificatore e usare la stessa funzione nella creazione e nella revoca.

**Criterio di accettazione:** creare e revocare accessi con lo stesso ID su due box produce effetti indipendenti.

### A08 La riautorizzazione non verifica l'identità del router

**P1 · `config_flow.py:123–129,211–217` · un caso riprodotto.**

Il flusso `reauth` salta il controllo dell'identificatore unico. Se l'indirizzo ora risponde con un altro router, si può avviare l'associazione e aggiornare la vecchia entry con i dati del nuovo dispositivo, mantenendo l'identità precedente. La riconfigurazione e le opzioni fanno già un controllo UID che manca in questo percorso.

Confrontare l'UID scoperto con l'entry prima di richiedere una nuova autorizzazione. Trattare una sostituzione del router come un percorso esplicito, con eventuale migrazione, invece di assimilarla a una semplice riautorizzazione.

**Criterio di accettazione:** un UID diverso interrompe il flusso prima della richiesta di associazione; lo stesso router può essere riautorizzato.

## Altri rilievi sul codice

| Priorità | Rilievo | Intervento |
| --- | --- | --- |
| P2 | `hacs.json` e README dichiarano HA 2024.11, ma `IliadboxOptionsFlow` legge `self.config_entry`, assente in `OptionsFlow` 2024.11 e presente in 2024.12. | Allineare la versione minima alla compatibilità verificata oppure implementare il supporto precedente. Aggiungere test sulla minima e sulla stabile scelta. |
| P2 | Il repository upstream non contiene test Python o frontend; la CI esegue HACS e Hassfest. | Introdurre test del client, fixture anonimizzate, test HA del ciclo di vita, controlli frontend, lint e verifiche dei tipi. |
| P2 | Senza permesso `settings`, il coordinatore apre una sessione a ogni aggiornamento, anche nell'uso intenzionalmente in sola lettura. | Distinguere capacità richieste da capacità disponibili; controllo dei permessi meno frequente e su richiesta. Centralizzare ogni rinnovo nel lock del client. |
| P2 | Le richieste concorrenti che ricevono una risposta tardiva di sessione scaduta azzerano il token senza controllare se è già stato rinnovato. | Legare l'invalidazione alla sessione usata dalla richiesta; testare risposte fuori ordine. È un rischio dedotto dal codice, non incluso nelle riproduzioni. |
| P2 | Il filtro dei dispositivi vecchi stacca davvero il dispositivo dall'entry, mentre la documentazione parla di nasconderlo. | Separare visibilità, retention e rimozione; testare scomparsa, ritorno e dispositivi condivisi con altre integrazioni, verificando la conservazione delle personalizzazioni. |
| P3 | La scheda ospiti cancella il messaggio d'errore quando il successivo refresh riesce, anche se il comando precedente è fallito. | Separare errori di comando ed errori di lettura, mantenendo visibile l'esito finché l'utente lo chiude o ripete l'azione. |
| P3 | Senza `entry_id`, la scheda sceglie `boxes[0]`; con più box può selezionare un dispositivo inatteso o non caricato. | Richiedere una scelta esplicita se ci sono più box; bloccare azioni quando la box scelta non è disponibile. |
| P3 | Esiste solo `translations/en.json`; frontend e diversi errori hanno testi inglesi fissi. | Traduzioni italiane e inglesi, eccezioni traducibili e stringhe frontend condivise. |
| P3 | Opzioni del livello di log per entry modificano il logger globale dell'integrazione. | Dichiarare l'opzione globale oppure gestire correttamente il filtro per box. |
| P3 | URL dell'interfaccia costruiti come `http://host` ignorano porta e HTTPS; host/porta sono poco validati e la concatenazione non gestisce correttamente IPv6 letterale senza parentesi. | Un costruttore URL condiviso, `configuration_url` nel device e validazione degli input. |

La compatibilità delle opzioni è stata verificata confrontando i sorgenti [2024.11.0](https://github.com/home-assistant/core/blob/2024.11.0/homeassistant/config_entries.py) e [2024.12.0](https://github.com/home-assistant/core/blob/2024.12.0/homeassistant/config_entries.py). L'introduzione della proprietà è descritta anche nelle [note ufficiali](https://developers.home-assistant.io/blog/2024/11/12/options-flow/). Questo confronto non certifica da solo tutte le altre dipendenze del progetto su 2024.12.

## Architettura proposta

Mantenere un client HTTP condiviso per ogni box, con un solo responsabile del rinnovo sessione. Il client dovrebbe restituire dati normalizzati e tipizzati; la logica di presentazione e le entità non dovrebbero dipendere direttamente dai dizionari grezzi del firmware.

Separare gli aggiornamenti in gruppi con disponibilità e timestamp propri: connessione/presenza, stato hardware, radio, accessi ospiti. Possono essere coordinatori distinti oppure un coordinatore con risultati separati per dominio. La scelta va guidata dai test e dalla quantità di codice, evitando letture duplicate.

Esporre capacità rilevate come `guest_supported`, `radio_supported` e permessi di lettura/modifica, distinguendole dagli errori temporanei. Un endpoint non supportato non va interrogato a ogni ciclo; un errore temporaneo non deve far dichiarare la funzione inesistente.

Il polling normale esegue sette richieste API per ciclo, esclusi login e tentativi aggiuntivi: sette al minuto con il valore predefinito di 60 secondi, 42 al minuto con 10 secondi. Il rinnovo dei permessi aggiunge due richieste per ciclo quando manca `settings`. Sono conteggi del codice, non misure sul router.

Usare frequenze separate, inizialmente conservative: presenza e traffico più frequenti, hardware più lento, ospiti aggiornati dopo le azioni e periodicamente. Il frontend oggi richiede l'intero stato di tutti i box ogni dieci secondi per scheda/pannello: introdurre sottoscrizioni agli aggiornamenti HA e payload mirati. Queste richieste frontend attualmente leggono la cache e non equivalgono a nuove interrogazioni del router.

Ogni host crea potenzialmente 14 entità: tracker, connettività e 12 sensori, alcuni disabilitati di default. Aggiungere profili di esposizione e selezione dei dispositivi; misurare l'impatto sul recorder prima di abilitare più statistiche. Cento host possono già comportare 1.400 entità registrate.

## Estensioni con maggiore utilità

| Estensione | Utilità concreta | Vincoli e verifica |
| --- | --- | --- |
| Diagnostica esportabile | Riduce il tempo necessario per segnalare e correggere problemi. Include modello, versione API, capacità, errori e freschezza dei dati. | Mascherare token, password, identificatori e indirizzi; usare una lista esplicita di campi ammessi e test di redazione. |
| Qualità della connessione | Latenza, perdita pacchetti e durata delle interruzioni aiutano a capire quando e perché la rete degrada. | Non dedurre la raggiungibilità Internet dal solo stato WAN. Riutilizzare integrazioni HA esistenti per sonde esterne quando opportuno; misurare separatamente le fonti. |
| Presenza più affidabile | Ritardo configurabile prima di dichiarare assente un dispositivo, selezione dei client e gestione dei ritorni dopo sleep. | Non trasformare un router indisponibile in “tutti fuori casa”; provare dispositivi mobili con risparmio energetico e MAC privati. |
| Eventi e blueprint | Notifiche per nuova periferica, cambio IP pubblico, WAN interrotta o ripristinata, temperatura alta e accesso ospite prossimo alla scadenza. | Sopprimere eventi duplicati e picchi al primo caricamento; ricordare che un'interruzione più breve del polling può non essere rilevata. |
| Gestione ospiti evoluta | Preset durata/dispositivi, selezione dell'accesso da condividere, QR su richiesta, rotazione e revoca pianificata. | Prima correggere identità, scadenza e permessi; distinguere scadenza del router da pianificazione HA e verificarne il comportamento dopo un riavvio. |
| Discovery automatica | Riconoscimento del router e aggiornamento indirizzo senza riconfigurazioni manuali. | Verificare che Iliadbox annunci un servizio compatibile; usare UID stabile e controllo del modello. Il manifest Freebox di HA usa `_fbx-api._tcp.local.`. |
| Diagnostica Ethernet e fibra | Stato e velocità delle porte, errori, potenza ottica e parametri FTTH rendono l'integrazione utile per trovare guasti fisici. | Verificare endpoint, unità e disponibilità su ogni modello; creare entità solo per dati realmente disponibili. |
| Controllo Wi-Fi per radio | Accensione per banda, informazioni canale/ampiezza e client associati, con supporto per radio multiple. | Identità AP/BSS corretta prima dei controlli; non promettere 6 GHz, Wi-Fi 7 o mesh su modelli che non li espongono. |
| Rete avanzata opzionale | Prenotazioni DHCP, Wake-on-LAN, parental control, VPN e stato NAT possono integrare automazioni domestiche. | Studio separato di endpoint e permessi. Iniziare da letture; modifiche di rete con schema validato e conferma dell'esito. |

La [Freebox ufficiale di Home Assistant](https://www.home-assistant.io/integrations/freebox/) è un riferimento utile per discovery e funzioni ulteriori. Il suo supporto a una funzione non ne dimostra la disponibilità sulle Iliadbox italiane. Anche sostituire il client con una libreria Freebox richiede prima un confronto di autenticazione, API ospiti e versioni: non è una scorciatoia automaticamente migliore.

## Piano di sviluppo e criteri di completamento

| Incremento proposto | Contenuto | Condizione per considerarlo completato |
| --- | --- | --- |
| 1 · Correzioni di base | A01–A08, versione minima coerente, test di regressione e CI. | I casi attualmente falliti passano senza `xfail`; test HA reali per setup, reauth, utenti e due box; nessuna modifica involontaria degli ID delle entità. |
| 2 · Aggiornamenti affidabili | Dati tipizzati, capacità, gestione degli errori parziali, rinnovo sessione unico, polling per gruppi e diagnostica. | Un guasto parziale non azzera dati sani; il router torna operativo senza interventi dopo un'interruzione; nessun segreto nel diagnostico. |
| 3 · Esperienza utente | Italiano, frontend condiviso, errori persistenti, selettore box, aggiornamenti tramite sottoscrizione e ospiti migliorati. | Verifica desktop/mobile, accessibilità da tastiera, utenti non amministratori e più schede aperte; niente richieste concorrenti inutili. |
| 4 · Monitoraggio e automazioni | Presenza con ritardo, storico interruzioni, eventi, blueprint e metriche di qualità. | Scenari ripetibili di disconnessione, ritorno, riavvio HA e box; nessun evento spurio all'avvio. |
| 5 · Estensioni hardware | Ethernet, FTTH, radio avanzate e successive funzioni di rete, secondo le capacità osservate. | Fixture e prove reali per ciascun modello dichiarato; funzioni assenti gestite senza errori globali. |

Come obiettivo di qualità, usare la [Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/) come checklist tecnica: flussi testati, gestione degli errori, diagnostica e traduzioni. Per le parti critiche puntare a copertura elevata dei rami, includendo errori e concorrenza; il livello Silver della scala indica oltre il 95% di copertura complessiva. Non attribuire all'integrazione un livello ufficiale senza soddisfare e verificare tutte le condizioni applicabili.

La CI dovrebbe eseguire lint/compilazione, test del client e delle trasformazioni, test HA con fixture, controlli dei componenti frontend, HACS e Hassfest. Una matrice tra versione minima e stabile evita dichiarazioni di compatibilità non controllate; un controllo sulla versione di sviluppo può anticipare rotture future.

Prima di rilasciare cambiamenti strutturali, provare anche la migrazione di un'installazione esistente: entity ID, nomi personalizzati, dispositivi condivisi, automazioni e opzioni devono restare coerenti. I difetti di registro e autorizzazione richiedono test in HA, oltre alle prove isolate.

## Risultati storici e regressioni attuali

L’analisi iniziale del 21 novembre 2026 ha riprodotto otto difetti in dodici casi isolati e verificato tre controlli positivi sulla versione 0.10.4. I fallimenti attesi appartengono a quella versione, non alla suite attuale.

Le prove isolate basate su estrazione AST sono state sostituite da test che importano il codice di produzione ed eseguono anche flussi, registri, piattaforme e WebSocket reali di Home Assistant. Le istruzioni e la matrice di compatibilità sono in [DEVELOPMENT.md](DEVELOPMENT.md).

La verifica hardware richiede ancora modello, firmware, versione API e campioni anonimizzati. Non salvare token o password nelle fixture.
