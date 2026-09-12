# Codebase Concerns

**Analysis Date:** 2026-09-12

Legenda: **VERIFICATO** = confermato leggendo il codice sorgente. **SOSPETTO** = ipotesi plausibile non confermata (nessun accesso al DB di produzione o a metriche live).

## Tech Debt

**Valori di `quality` scritti in modo incoerente (VERIFICATO):**
- Problema: la colonna `quality` in `titles` riceve stringhe con casing diverso a seconda del percorso di codice che le produce, quindi lo stesso concetto ("720p") finisce nel DB come più valori distinti.
  - `parser.extract_quality()` fa sempre `.upper()` sul match finale → produce `2160P`, `1080P`, `720P`, `4K` (`src/parser.py:121-127`).
  - Il fallback su hint di sezione nella stessa funzione di parsing lista scrive invece minuscolo per la "p": `'4K'`, `'1080p'`, `'720p'`, `'SD'` (`src/parser.py:413-423`).
  - `extract_quality_from_icons()` scrive un terzo mix: `'4K'`, `'1080p'`, `'720p'` (`src/parser.py:171-176`).
  - Risultato: per lo stesso contenuto reale possono coesistere `720p`/`720P`, `1080p`/`1080P`, `4K`/`2160P` nella stessa colonna, popolata da tre funzioni diverse senza un punto di normalizzazione unico.
- Files: `src/parser.py:121-127`, `src/parser.py:165-177`, `src/parser.py:298-324`, `src/parser.py:413-423`.
- Impact: `database.get_section_titles()` calcola `available_qualities` con `SELECT DISTINCT quality` (`src/database.py:801-806`) e il filtro fa un match esatto (`AND quality = ?`, `src/database.py:764-766`). Il template `section_detail.html` renderizza un bottone per ogni valore distinto (`src/templates/section_detail.html:294-306`): l'utente vede due bottoni "720p" e "720P" che filtrano ciascuno solo un sottoinsieme dei titoli in quella risoluzione. Bug visibile, non solo cosmetico.
- Fix approach: introdurre una funzione unica `normalize_quality()` usata da tutti e tre i punti di scrittura in `parser.py` (schema canonico consigliato: sempre `p` minuscola per le risoluzioni progressive, `4K` per l'ultra HD), poi una migrazione one-off in stile `database.migrate_refresh_policy()` (`src/database.py:615-661`) che riscrive i valori esistenti in `titles.quality`.

**Nessuna normalizzazione né vincolo sui valori di `quality` a livello DB (VERIFICATO):**
- La colonna è `TEXT` libero, senza CHECK constraint né tabella di lookup (`src/database.py:135-147`). Qualunque stringa può finire nella colonna; l'unica difesa è la disciplina del parser, che come sopra non è uniforme.
- Fix approach: valutare un CHECK constraint o quantomeno un set fisso di valori ammessi lato applicazione dopo la normalizzazione.

**Estrazione di `director`/`year` via regex su titoli in formato libero (VERIFICATO):**
- `extract_director_and_year()` (`src/database.py:34-121`) tenta 5 pattern regex diversi su testo scritto a mano da utenti del forum. È un parser euristico intrinsecamente fragile: cambi minimi di formattazione nei titoli producono `director`/`year` `NULL` o sbagliati.
- Files: `src/database.py:34-121`.
- Impact: esiste già una pagina dedicata proprio a questo (`/sections/missing-data`, `src/server.py:218-222`, `src/database.py:843-887`), segno che il problema è noto e monitorato, non ignorato.
- Fix approach: nessuna azione urgente: il problema è già osservabile e gestito con una coda di revisione manuale. Da tenere presente se la UI v2 vuole ridurre l'affidamento su `director`/`year` regex-based a favore dei metadati TMDB (già più affidabili, vedi `ratings.py`).

**Costanti duplicate lato client per l'URL delle immagini TMDB (VERIFICATO):**
- `const POSTER_BASE = 'https://image.tmdb.org/t/p/w92';` è ripetuta identica in due template (`src/templates/index.html:387`, `src/templates/ratings.html:226`). Nessun'altra pagina che mostra poster esiste, ma la duplicazione è già a 2 copie.
- Impact: cambiare dimensione poster o passare a un proxy/cache richiede modifiche sincronizzate in più file HTML incorporati (zero build, niente componenti condivisi lato JS).
- Fix approach: la UI v2 è il momento naturale per centralizzare questa costante (es. iniettata dal server in un blocco `<script>` comune o in un file JS condiviso).

## Known Bugs

**Filtro qualità con voci duplicate (VERIFICATO, conseguenza diretta del problema sopra):**
- Sintomi: nella pagina di dettaglio sezione, i bottoni di filtro qualità mostrano varianti duplicate dello stesso valore semantico (es. "720p" e "720P" come bottoni separati), ciascuno filtra solo il sottoinsieme scritto con quel casing esatto.
- Files: `src/database.py:801-806` (query `DISTINCT`), `src/templates/section_detail.html:294-306` (render), `src/database.py:764-766` (match esatto nel filtro).
- Trigger: aprire una qualsiasi sezione che abbia titoli scritti da percorsi di scraping diversi (con e senza dettaglio post) per la stessa risoluzione.
- Workaround: nessuno lato utente; l'unico modo per vedere tutti i titoli in quella risoluzione è cliccare più bottoni in sequenza (l'interfaccia non supporta multi-select, va verificato ma non risulta dal JS letto).

## Security Considerations

**Gestione chiavi TMDB/OMDb (VERIFICATO — nessun problema rilevato):**
- Le chiavi (`TMDB_API_KEY`, `OMDB_API_KEY`) sono lette solo da `config.py` via variabili d'ambiente (`src/config.py:56,59`) e usate esclusivamente lato server in `ratings.py` (`src/ratings.py:132-143`, `:352`). Non vengono mai serializzate in una risposta JSON o incorporate in un template: gli endpoint `/api/ratings/status` espongono solo booleani `tmdb_key`/`omdb_key` (`src/server.py:692-693`), mai il valore. Nessuna fuga di segreti verificata verso il client.
- `.env` è in `.gitignore` (verificato) e non è mai letto da questo agente per policy.

**Endpoint di relay sessione protetto da token con confronto costante-time (VERIFICATO — corretto):**
- `POST /api/session` confronta il token con `hmac.compare_digest` (`src/server.py:341-344`), evitando timing attack banali. L'endpoint è disabilitato di default se `SESSION_TOKEN` è vuoto (`src/server.py:336-337`).
- Nota minore: il file `session.json` risultante contiene cookie di sessione validi del forum in chiaro su disco (`src/session_store.py:81-108`), condiviso tra i due container via bind mount. Non è un errore di codice ma un dato sensibile persistito senza cifratura — accettabile per un homelab a singolo host, da tenere a mente se l'host cambia contesto di fiducia.

**Nessuna autenticazione sulle route admin (SOSPETTO/da verificare in produzione):**
- `/admin`, `/api/import/*`, `/api/schedule`, `/api/pages` (lettura e scrittura di `pages.txt`) non hanno alcun controllo di autenticazione nel codice Flask (`src/server.py:193-196`, `:283-317`, `:403-438`, `:441-556`). Chiunque raggiunga la porta del servizio può avviare import, riscrivere `pages.txt` o disabilitare lo scheduling.
- Impact reale dipende dall'esposizione di rete: se il servizio è raggiungibile solo su rete interna xhub (come suggerito da CLAUDE.md, "gira su xhub"), il rischio è basso; se mai esposto pubblicamente, è un problema serio.
- Fix approach: non necessario per uso homelab interno; da rivalutare solo se cambia l'esposizione di rete.

## Performance Bottlenecks

**Ricerca testuale con `LIKE '%...%'` non indicizzabile (VERIFICATO nel codice, impatto reale non misurato):**
- `search_titles()` con `search_type` in `contains` (default), `ends_with`, `all_words` costruisce condizioni `title LIKE '%query%'` o `'%query'` (`src/database.py:411-427`). Un pattern con wildcard iniziale non può sfruttare `idx_title` (`src/database.py:187`): SQLite esegue una scansione completa della tabella `titles` (~67.714 righe) per ogni ricerca di questo tipo, più una seconda scansione identica per il `COUNT(*)` di paginazione (`src/database.py:455-456`).
- Solo `search_type=starts_with` (pattern `'query%'`) può usare l'indice via il LIKE-optimization di SQLite.
- Files: `src/database.py:377-478`.
- Cause: nessun indice FTS (`FTS5`) né indice a prefisso multiplo; il design attuale usa solo B-tree standard.
- Improvement path: a 67k righe una scansione completa in SQLite è nell'ordine dei millisecondi ed è **plausibilmente non un problema oggi** (nessuna misura diretta disponibile, ma il volume è modesto per SQLite). Diventa rilevante solo se la UI v2 introduce ricerca "live" a ogni tasto digitato con alta concorrenza, o se il dataset cresce di un ordine di grandezza. In quel caso la soluzione naturale è una tabella virtuale `FTS5` popolata da `title`.

**Nessun N+1 rilevato nelle query di lista (VERIFICATO — nessun problema):**
- Sia `search_titles()` sia `get_section_titles()` sia `get_rating_matches()` recuperano i dati di rating con un singolo `LEFT JOIN title_ratings` (`RATING_JOIN`, `src/database.py:894`) invece di una query per riga. Il rendering di ~50 risultati con poster non genera richieste aggiuntive lato server: l'URL del poster è costruito lato client concatenando `POSTER_BASE` (statico) con `poster_path` già presente nella riga JSON.

**Indici presenti coprono i filtri principali (VERIFICATO — nessun problema):**
- `idx_title`, `idx_section`, `idx_director`, `idx_year`, `idx_title_first_letter` su `titles` e `idx_rating_status`, `idx_rating_imdb_id`, indice a espressione `idx_rating_score` su `COALESCE(imdb_rating, tmdb_rating)` in `title_ratings` (`src/database.py:187-191`, `:238-243`). I filtri per sezione, anno, lettera, director e l'ordinamento per voto hanno tutti un indice dedicato. Manca solo un indice su `quality` (non presente), ma è sempre applicato in combinazione con `section` che ha già indice, quindi l'impatto è limitato al sottoinsieme di righe della sezione.

**SQLite senza WAL né busy_timeout, con due processi scrittori concorrenti (VERIFICATO nel codice, non riprodotto):**
- `get_connection()` apre la connessione con le impostazioni di default di `sqlite3` (`src/database.py:13-17`): nessun `PRAGMA journal_mode=WAL`, nessun `PRAGMA busy_timeout`. Il `docker-compose.yml` fa girare due container (`web` e `scheduler`) che montano la stessa directory `./data` e quindi lo stesso file `.db` (`docker-compose.yml`, servizi `web`/`scheduler`, volume `./data:/app/data`).
- Impact: se un'importazione schedulata (container scheduler) e un'importazione manuale o un arricchimento voti avviati dall'admin UI (container web) scrivono nello stesso momento, il journal mode di default (rollback journal) con timeout di attesa nullo può restituire `sqlite3.OperationalError: database is locked` invece di attendere. Non verificato in produzione, ma è una condizione di gara plausibile e non mitigata nel codice.
- Fix approach: aggiungere `conn.execute("PRAGMA journal_mode=WAL")` e `conn.execute("PRAGMA busy_timeout=5000")` in `get_connection()` (`src/database.py:13-17`) elimina la maggior parte del rischio con una modifica minima.

## Fragile Areas

**Login al forum bloccato da Cloudflare, sostituito da un relay di sessione fragile (VERIFICATO, stato attuale):**
- Il commento in testa a `session_store.py` documenta esplicitamente il problema: "Cloudflare fronts the login endpoint with a JS challenge, so the scraper cannot authenticate on its own" (`src/session_store.py:1-7`). `scraper.login()` (`src/scraper.py:139-199`) esiste ancora come fallback a username/password ma è verosimilmente inutilizzabile contro la challenge JS (non testato qui, ma coerente con quanto riportato nel diario di sessione dell'utente).
- Il meccanismo primario è `apply_session()` + `verify_session()` (`src/scraper.py:61-112`): carica cookie salvati da un'estensione browser tramite `POST /api/session` (`src/server.py:328-393`) e verifica che raggiungano davvero contenuto autenticato (non si fida dello status code, vedi commento `src/scraper.py:89-95`).
- Fragilità intrinseca: phpBB lega la sessione allo User-Agent (documentato nel diario utente) e ruota `sid`/autologin key a ogni richiesta; `session_store.refresh()` (`src/session_store.py:111-128`) e `authenticate()` (`src/scraper.py:114-137`) tengono conto di questo, ma l'intera catena dipende da un processo umano esterno al codice (estensione che ripusha cookie freschi) — non c'è modo, dal solo codice, di recuperare automaticamente da una sessione scaduta.
- Files: `src/session_store.py` (intero modulo), `src/scraper.py:61-137`, `src/server.py:320-401`.
- Stato: il codice gestisce bene i casi che *può* gestire (verifica reale del contenuto, non sovrascrivere una sessione funzionante con una peggiore — commento `src/server.py:356-363` — namespace dei cookie transient come `cf_clearance` esclusi dal calcolo di scadenza in `session_store.earliest_expiry()`, `src/session_store.py:60-78`). Il punto debole resta esterno al codice: se l'estensione browser smette di pushare, gli import restano fermi senza alcun meccanismo di allarme attivo oltre ai log.
- Da verificare per la UI v2: `session_store.status()` (`src/session_store.py:153-178`) espone stato/scadenza già pronto per essere mostrato in admin UI in modo più visibile.

**Accoppiamento diretto tra nomi di colonna DB e JS nei template (VERIFICATO):**
- `src/templates/index.html` e `src/templates/ratings.html` costruiscono l'HTML dei risultati leggendo direttamente i nomi di campo JSON restituiti da `/api/search` (es. `item.poster_path`, `item.quality`, `item.director` — `src/templates/index.html:365-410` circa, verificato via grep su `item.poster_path` riga 390/393). Questi campi corrispondono 1:1 ai nomi di colonna in `titles`/`title_ratings` restituiti da `dict(row)` in `database.search_titles()` (`src/database.py:468-477`, `RATING_COLUMNS` in `src/database.py:896-900`).
- Impact per la UI v2: qualunque rinomina di colonna DB o di chiave nella risposta JSON rompe silenziosamente il rendering lato client (nessun livello di serializzazione/DTO intermedio che isoli lo schema DB dal contratto API).
- Safe modification: se la UI v2 introduce nuovi campi o rinomina quelli esistenti, farlo aggiungendo alias nella query SQL (`SELECT col AS nome_pubblico`) piuttosto che rinominare le colonne fisiche, oppure introdurre un livello di serializzazione esplicito lato Flask.

**Stato globale in-process per lo stato di import/enrichment (VERIFICATO, rischio basso):**
- `import_status` e `ratings_status` sono dict a livello di modulo in `server.py` (`src/server.py:62-72`), mutati sia dal thread principale di Flask sia dai thread `daemon` avviati per le operazioni lunghe (`src/server.py:465-494`, `:716-741`), senza lock. Su un processo singolo (nessun `threaded=True` esplicito, nessun `processes=N` in `app.run()`, `src/server.py:866-871`) il rischio di race condition reale è basso: nel peggiore dei casi un messaggio di stato viene sovrascritto. Da tenere presente se la UI v2 introducesse un web server multi-processo (es. gunicorn con worker multipli): questi dict non sopravvivono al riavvio e non sono condivisi tra processi, quindi lo stato di import mostrato in UI diventerebbe inconsistente con più worker.

## Scaling Limits

**Budget giornaliero OMDb tracciato correttamente (VERIFICATO — nessun problema, ben progettato):**
- Il limite di ~1000 richieste/giorno del piano gratuito OMDb è gestito con un contatore persistito in `settings` (`database.get_setting`/`set_setting`), chiave `omdb_calls_date`/`omdb_calls_count`, azzerato automaticamente al cambio di data (`src/ratings.py:329-345`). Il default configurabile `OMDB_DAILY_LIMIT=900` (`src/config.py:61`) lascia deliberatamente un margine sotto il tetto reale di 1000.
- Comportamento a budget esaurito: `fetch_imdb_votes()` ritorna `{'skipped': 'budget'}` senza eccezioni (`src/ratings.py:426-435`), e `refresh_imdb_vote()` (usato dal match manuale in `/api/ratings/match`) fallisce silenziosamente restituendo `False` se il budget è a zero (`src/ratings.py:374-382`) — l'endpoint Flask non lo comunica esplicitamente all'utente (`src/server.py:787-816`: `refresh_imdb_vote` viene chiamato ma il suo valore di ritorno non è controllato), quindi un match manuale fatto a budget esaurito non riceve un voto IMDb e l'utente non viene avvisato del perché.
- Fix approach minore: controllare il valore di ritorno di `ratings.refresh_imdb_vote()` in `src/server.py:814` e includere un flag `imdb_pending: true` nella risposta JSON quando il budget è esaurito.

**Rate limiting TMDB gestito con backoff, non con conteggio budget (VERIFICATO — nessun problema noto):**
- TMDB non ha un tetto giornaliero fisso paragonabile a OMDb; il client gestisce solo i 429 con `Retry-After` e backoff esponenziale (`src/ratings.py:151-177`). Nessun problema di scaling rilevato qui.

## Dependencies at Risk

**Nessuna versione pinnata nei requirements (VERIFICATO):**
- `requirements.txt` usa solo limiti minimi (`requests>=2.31.0`, `beautifulsoup4>=4.12.0`, `flask>=3.0.0`, `python-dotenv>=1.0.0`), senza lockfile (nessun `requirements.lock`, `Pipfile.lock` o simile trovato). Una build su xhub in un momento diverso da un'altra può installare versioni differenti delle stesse dipendenze.
- Impact: rischio di comportamento non riproducibile tra build, specialmente per `beautifulsoup4` il cui parsing HTML in `parser.py` è già sensibile a piccole differenze di markup del forum.
- Fix approach: pinnare versioni esatte o introdurre un lockfile quando si ritocca la pipeline di build su xhub.

## Missing Critical Features

**Nessun meccanismo di allarme se la sessione forum scade (VERIFICATO tramite assenza):**
- `session_store.status()` calcola correttamente gli stati `ok`/`expiring`/`expired` (`src/session_store.py:153-178`) ed è già esposto su `GET /api/session` (`src/server.py:320-325`), ma nulla nel codice invia una notifica proattiva (email, webhook) quando lo stato passa a `expiring`/`expired`: l'unico modo per accorgersene è aprire `/admin` o leggere i log. Coerente con l'esperienza già vissuta ("import fermi da luglio") citata nella memoria di progetto.
- Blocks: rilevamento tempestivo della scadenza sessione senza controllo manuale periodico.

## Test Coverage Gaps

**Nessuna suite di test nel repository (VERIFICATO):**
- Non esiste alcuna directory `tests/`, file `test_*.py`, `*_test.py`, né configurazione di `pytest`/`unittest` nel repository. Nessuno dei moduli (`parser.py`, `ratings.py`, `database.py`, `scraper.py`) ha copertura automatica.
- Rischio maggiore: `parser.py` (estrazione titolo/qualità/lingua da HTML del forum) e `database.extract_director_and_year()` (5 pattern regex) sono il codice più euristico e più soggetto a rompersi silenziosamente a fronte di piccoli cambi di markup o di formato titolo — sono anche i moduli meno coperti da qualunque rete di sicurezza.
- Priority: Alta per `parser.py` ed `extract_director_and_year()` prima di qualunque refactoring che li tocchi; Media per `ratings.py` (matching TMDB), dato che gli errori qui sono già mitigati da una pagina di revisione umana (`/ratings`).

---

*Concerns audit: 2026-09-12*
