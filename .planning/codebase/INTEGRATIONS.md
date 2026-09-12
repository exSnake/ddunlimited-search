# External Integrations

**Analysis Date:** 2026-09-12

## APIs & External Services

**Catalogo film/serie — TMDB (The Movie Database):**
- Uso: abbinare ogni titolo del forum a un film/serie TMDB, da cui si ottengono `tmdb_id`, `imdb_id`, poster, voto e conteggio voti TMDB
- Client: `requests.Session` fatto a mano in `TMDBClient` (`src/ratings.py:128-185`), nessun SDK ufficiale
- Base URL: `https://api.themoviedb.org/3` (`src/ratings.py:34`)
- Endpoint usati: `GET /search/{movie|tv}` (`src/ratings.py:179-181`) e `GET /{movie|tv}/{id}` con `append_to_response=credits` (e `external_ids` per le serie, per recuperare l'`imdb_id`) (`src/ratings.py:183-185`)
- Auth: chiave v3 in query string (`api_key`) oppure token v4 come `Authorization: Bearer` se la chiave comincia per `eyJ` (`src/ratings.py:131-143`); variabile `TMDB_API_KEY`
- Lingua risposte/poster: `TMDB_LANGUAGE` (default `it-IT`, `src/config.py:57`)
- Rate limit: nessun tetto giornaliero esplicito nel codice; pausa fissa `TMDB_REQUEST_DELAY` (default 0.05s, ≈ 20 richieste/sec) tra una chiamata e l'altra (`src/ratings.py:152`); su HTTP 429 rispetta `Retry-After` e riprova fino a `RATE_LIMIT_MAX_RETRIES = 3` (`src/ratings.py:37,163-167`)
- Errori: HTTP 401/403 sollevano `RatingsError` e fermano la passata (chiave rifiutata, `src/ratings.py:168-169`); HTTP 404 → nessun match (`None`); altri errori HTTP loggati e trattati come nessun risultato
- Logica di matching: `match_title()` (`src/ratings.py:272-299`) prova più varianti del titolo (`title_variants`) e più tipi di media (`movie`/`tv`, ordine deciso da `media_types_for`), calcola uno score con `SequenceMatcher` + bonus/penalità su anno e regista (`score_candidate`, `apply_director_bonus`), scarta sotto 0.4; sopra/sotto `RATING_MIN_CONFIDENCE` (default 0.75) il match finisce rispettivamente `matched` o `low_confidence` nella tabella `title_ratings`

**Voto IMDb — OMDb API:**
- Uso: unica fonte del voto IMDb (IMDb non ha API pubbliche); TMDB fornisce l'`imdb_id`, OMDb lo traduce in voto e numero voti
- Client: `requests.Session` diretto in `fetch_omdb_rating()` (`src/ratings.py:348-371`), nessun SDK
- Base URL: `https://www.omdbapi.com/` (`src/ratings.py:35`)
- Auth: query param `apikey`, variabile `OMDB_API_KEY`
- **Rate limit: piano gratuito a ~1000 chiamate/giorno.** Il codice si autolimita a `OMDB_DAILY_LIMIT` (default 900, in `.env.example` e `docker-compose.yml`) per restare sotto il tetto
- Budget giornaliero tracciato in SQLite (non in memoria): chiavi `omdb_calls_date` e `omdb_calls_count` nella tabella `settings`, lette/scritte da `_omdb_budget_left()` / `_record_omdb_calls()` (`src/ratings.py:329-345`) — il contatore si azzera quando cambia la data
- Errori: HTTP 401 solleva `RatingsError` (chiave rifiutata); `Response: "False"` nel JSON (titolo non trovato o non ancora votato su IMDb) → `(None, None)` senza eccezione, e il timestamp `imdb_checked_at` viene comunque scritto per non richiedere lo stesso titolo ogni passata (`src/database.py:1005-1017`)
- Due punti di chiamata: `fetch_imdb_votes()` (passata batch schedulata, consuma il budget residuo) e `refresh_imdb_vote()` (chiamata singola immediata quando un match viene corretto a mano dalla pagina `/ratings`)

**Forum DDUnlimited (scraping):**
- Non è un'API: è HTML scrapato da `https://ddunlimited.net` (`src/config.py:12-13`)
- Client: `requests.Session` con User-Agent desktop Chrome fisso (`src/scraper.py:55-58`), parsing con BeautifulSoup (`src/parser.py`)
- Elenco pagine/sezioni da scrapare: file `pages.txt` (formato `Sezione | URL | numero pagina`, parsing in `src/parser.py`)
- Rate limiting lato nostro: `REQUEST_DELAY` tra le richieste di listing (default 1.5s), fino a `POST_DETAIL_WORKERS` (default 3) richieste parallele per i dettagli dei singoli post, con backoff esponenziale su errori/429 (`RATE_LIMIT_MAX_RETRIES=3`, `RATE_LIMIT_BACKOFF_BASE=30s`, tetto `RATE_LIMIT_BACKOFF_MAX=300s`, `src/scraper.py:46-48`)
- Rilettura dei post: un topic viene riaperto una sola volta, `POST_RECHECK_DAYS` (default 30) giorni dopo la creazione, perché il titolo può ancora cambiare nei primi giorni (`src/config.py:44-46`, colonna `details_next_refresh_at`)

## Autenticazione verso il forum (caso particolare)

Il login diretto (`ucp.php?mode=login`) è dietro una challenge JavaScript di Cloudflare, quindi lo scraper **non può autenticarsi da solo**. La sessione viene invece "iniettata" dall'esterno:

- **Estensione browser** (non presente in questo repository) cattura i cookie da un browser già loggato e li spedisce a `POST /api/session` (`src/server.py:328-393`)
- Autenticazione dell'endpoint: header `X-Session-Token`, confrontato con `hmac.compare_digest` contro la variabile `SESSION_TOKEN` (`src/server.py:341-344`); endpoint disabilitato (503) se `SESSION_TOKEN` è vuota
- Prima di sovrascrivere una sessione funzionante, il server verifica se quella già salvata funziona ancora (`keeper.verify_session()`) e in tal caso la tiene, per non far litigare due sessioni sulla stessa autologin key del forum (`src/server.py:356-363`)
- La sessione verificata viene salvata su file JSON (`session.json`, path in `SESSION_FILE`) tramite scrittura atomica (tempfile + `os.replace`) così i container `web` e `scheduler` — che leggono/scrivono lo stesso volume ma sono processi separati — non si vedono mai un file a metà (`src/session_store.py:81-108`)
- phpBB lega la sessione allo User-Agent e ruota session id/autologin key a ogni uso: per questo lo User-Agent catturato viene riusato (`src/scraper.py:73-74`) e i cookie vengono "rinfrescati" dopo ogni verifica (`session_store.refresh()`, `src/session_store.py:111-128`)
- Cookie transitori di Cloudflare (`__cf_bm`, `cf_clearance`, `__cfruid`, `__cflb`) sono esclusi dal calcolo della scadenza perché vengono riemessi a ogni visita e non riflettono la durata reale della sessione forum (`src/session_store.py:45,60-78`)
- Verifica della sessione: non basta un HTTP 200 (un ospite non loggato riceve comunque 200 con i link nascosti) — `verify_session()` scarica una pagina di riferimento da `pages.txt` e controlla che il parsing produca titoli reali (`src/scraper.py:89-110`)

## Data Storage

**Database:**
- SQLite, file singolo su disco (`DATABASE_PATH`, default `data/ddunlimited.db`)
- Accesso: modulo standard `sqlite3` con `row_factory = sqlite3.Row`, nessun ORM (`src/database.py:13-31`)
- Schema creato/migrato in modo idempotente a ogni avvio da `init_db()` (`src/database.py:124-243`): `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN` guardato da `PRAGMA table_info`
- Non esiste una cartella `migrations/`: ogni evoluzione dello schema è una funzione Python idempotente richiamata all'avvio (vedi anche `migrate_refresh_policy()`, `migrate_existing_titles()`)

### Tabella `titles` (67.714 righe in produzione)

Definita in `src/database.py:135-147`, con colonne aggiunte via migrazione incrementale (righe 154-180):

| Colonna | Tipo | Note |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | |
| `title` | TEXT NOT NULL | titolo così come appare nel forum |
| `url` | TEXT NOT NULL UNIQUE | URL del topic; è la chiave naturale per insert/update (`insert_title`, `src/database.py:246-330`) |
| `section` | TEXT | sezione del forum (es. "Serie TV ITA") |
| `metadata` | TEXT | tag tecnici combinati (codec, contenitore, sub, ecc.), stringa `A \| B \| C` |
| `quality` | TEXT | **vedi sezione dedicata sotto — valori non normati** |
| `director` | TEXT | estratto per regex dal titolo (`extract_director_and_year`, `src/database.py:34-121`) |
| `year` | INTEGER | idem |
| `title_first_letter` | TEXT | prima lettera alfanumerica normalizzata, `#` se assente |
| `created_at` | TIMESTAMP | default `CURRENT_TIMESTAMP`, data di primo inserimento nel nostro DB |
| `languages` | TEXT | lingue audio, codici tipo `ITA \| ENG` |
| `deleted_at` | TIMESTAMP | soft delete quando il topic risponde 404 (`delete_title`, riga 366-374) |
| `raw_info` | TEXT | testo grezzo dell'`<h4>` del post, non parsato |
| `details_scraped_at` | TIMESTAMP | ultima volta che il post è stato aperto per i dettagli |
| `details_next_refresh_at` | TIMESTAMP | prossima rilettura pianificata (politica `POST_RECHECK_DAYS`) |
| `post_created_at` | TIMESTAMP | data di creazione del topic sul forum |

Indici: `idx_title(title)`, `idx_section(section)`, `idx_director(director)`, `idx_year(year)`, `idx_title_first_letter(title_first_letter)` (`src/database.py:187-191`).

Colonna rimossa: `status` (drop best-effort in `migrate_refresh_policy()`, righe 651-658 — non droppabile su SQLite vecchie, in quel caso resta ma inutilizzata).

### Tabella `title_ratings` (una riga per titolo cercato, non solo per titolo trovato)

Definita in `src/database.py:219-237`:

| Colonna | Tipo | Note |
|---|---|---|
| `title_id` | INTEGER PRIMARY KEY | FK verso `titles.id`, `ON DELETE CASCADE` |
| `media_type` | TEXT | `'movie'` o `'tv'` |
| `tmdb_id` | INTEGER | id TMDB del match |
| `imdb_id` | TEXT | id IMDb ottenuto da TMDB (`external_ids.imdb_id` per le serie, `imdb_id` per i film) |
| `tmdb_rating` | REAL | `vote_average` TMDB, `NULL` se `vote_count` è 0 |
| `tmdb_votes` | INTEGER | `vote_count` TMDB |
| `imdb_rating` | REAL | voto da OMDb |
| `imdb_votes` | INTEGER | conteggio voti da OMDb |
| `poster_path` | TEXT | path poster TMDB (relativo, va composto con un CDN TMDB lato client) |
| `matched_title` | TEXT | titolo restituito da TMDB |
| `matched_year` | INTEGER | anno restituito da TMDB |
| `confidence` | REAL | punteggio 0–1 calcolato da `score_candidate` + `apply_director_bonus` |
| `match_status` | TEXT NOT NULL DEFAULT `'unmatched'` | uno tra `matched`, `low_confidence`, `unmatched`, `rejected`, `manual` |
| `matched_at` | TIMESTAMP | quando è stato scritto l'ultimo match |
| `imdb_checked_at` | TIMESTAMP | quando è stato interrogato OMDb (anche se senza risultato, per non richiedere due volte) |

Indici: `idx_rating_status(match_status)`, `idx_rating_imdb_id(imdb_id)`, `idx_rating_score(COALESCE(imdb_rating, tmdb_rating))` (`src/database.py:238-243`).

Il voto "ufficiale" mostrato in UI è sempre `COALESCE(imdb_rating, tmdb_rating)` (costante `RATING_SCORE_SQL`, `src/database.py:892`): IMDb vince quando c'è, altrimenti si mostra TMDB.

### Tabelle di supporto

- `import_history` (`src/database.py:194-204`): una riga per ogni passata di scraping, con conteggi `titles_found/inserted/updated` e `status` (`running`/`completed`/`failed`). Usata dallo scheduler per decidere se un import è dovuto (`should_run_import`, `src/scheduler.py:62-110`).
- `settings` (`src/database.py:208-214`): key-value generico. Ci vivono sia le preferenze di schedulazione modificabili dalla UI admin (`scrape_enabled`, `scrape_interval_days`, `scrape_hour`, `scrape_minute` — hanno priorità sulle env var, `get_schedule()` righe 675-690) sia il contatore giornaliero OMDb (`omdb_calls_date`, `omdb_calls_count`) sia flag di migrazione una tantum (`migrated_refresh_policy`). È anche il meccanismo con cui i container `web` e `scheduler`, che non condividono memoria, si scambiano stato.

### Il campo `quality`: valori non normati (nota per la UI v2)

Il database di produzione non era leggibile da questo ambiente di analisi (nessun file `.db` nel repository); i valori riportati sotto sono dedotti dal codice che li scrive, in due percorsi indipendenti che **non concordano sul casing**:

1. **`extract_quality()`** (`src/parser.py:108-127`), usato per il testo libero dell'`<h4>` del post (sia nel primo passaggio di listing sia nel dettaglio del post via `parse_post_detail`) — fa sempre `match.group(1).upper()`, quindi produce solo maiuscolo:
   `2160P`, `4K`, `1080P`, `1080I`, `720P`, `720I`, `HDTV`, `WEB-DL`, `WEBDL`, `WEBRIP`, `WEB`, `BLURAY`, `BDRIP`, `BRRIP`, `DVDRIP`, `DVD`, `HDCAM`, `CAM`, `TS`, `TELESYNC`

2. **`extract_quality_from_icons()`** e **`detect_section_quality()`** (`src/scraper.py:165-176` e `298-341`), usati quando il testo non contiene un pattern riconoscibile e si deduce la qualità dalle icone (`<img src="full.hd.png">`, `4k`/`uhd` nel filename) o dal contesto di sezione — producono invece **case misto, hardcoded così nel codice**:
   `4K`, `1080p`, `720p`, `SD`

La priorità con cui i due percorsi vengono provati è in `src/scraper.py:402-423`: prima `extract_quality(full_text)` (maiuscolo), poi le icone (case misto), poi il contesto di sezione (case misto), infine un fallback sul nome della sezione. Il dettaglio del post (`parse_post_detail`, sempre maiuscolo) sovrascrive il valore di listing se presente (`src/scraper.py:383-384`). **Risultato atteso in produzione:** lo stesso concetto di qualità convive nel DB come `720P` e `720p`, `4K` e (mai) `4k`, e la variante `2160P` non ha mai un equivalente in case misto perché nessun percorso "icone" la produce — chi filtra o raggruppa per `quality` in una UI nuova deve normalizzare (es. `.upper()`) prima di confrontare o aggregare i valori. La UI attuale espone i valori così come sono in `get_section_titles()` (`src/database.py:801-806`, `SELECT DISTINCT quality ... ORDER BY quality`), quindi la UI stessa mostra oggi la stessa duplicazione.

**File Storage:**
- Nessun object storage esterno. I poster sono referenziati solo come `poster_path` relativo restituito da TMDB (da comporre con il dominio immagini di TMDB lato client/template, non scaricati né cacheati su disco)
- Log applicativi su filesystem locale (vedi sotto)

**Caching:**
- Nessuna cache dedicata (né Redis né in-memory strutturata). L'unico "cache" è lo stato persistito in SQLite (`title_ratings`, `settings`) per non ripetere chiamate esterne

## Autenticazione & Identità

**Provider:** nessuno. Non esiste un sistema di login per gli utenti dell'app — l'unica autenticazione applicativa è quella verso il forum (vedi sopra) e il token condiviso per l'endpoint `/api/session`.

## Monitoring & Observability

**Error tracking:** nessun servizio esterno (no Sentry/Bugsnag). Gli errori finiscono nei log applicativi con `exc_info=True` (es. `src/scheduler.py:128,152,193`, `src/server.py:487,540,736`).

**Log — stato attuale:**
- Tre logger Python separati, uno per processo/ambito, tutti configurati manualmente (non `logging.basicConfig` salvo lo scheduler):
  - `scraper` (`src/scraper.py:24-41`) → file `logs/scraper.log`, anche su stdout
  - `web` (`src/server.py:23-41`) → file `logs/web.log`; il logger `werkzeug` di Flask viene reindirizzato agli stessi handler (righe 44-49); una sottoclasse di `WSGIRequestHandler` (righe 52-57) scrive ogni richiesta HTTP nel log file ma manda su stdout solo le risposte non-200
  - `ratings` (`src/ratings.py:24-32`) → file `logs/ratings.log`, anche su stdout
  - `scheduler` (`src/scheduler.py:18-26`) → usa `logging.basicConfig` con `StreamHandler` + `FileHandler('logs/scheduler.log')`
- Formato uniforme: `'%(asctime)s - %(levelname)s - %(message)s'`, livello controllato da `LOG_LEVEL` (default `INFO`)
- I log sono file di testo semplice sul volume condiviso `./logs` (non strutturati, non JSON)
- Esposti in UI dalla pagina `/logs` (`src/templates/logs.html`) tramite l'endpoint `GET /api/logs` (`src/server.py:225-265`), che legge le ultime N righe del file richiesto (`scraper`/`scheduler`/`web`) con supporto a paginazione via `offset`/`lines`

**Direzione pianificata (non ancora implementata nel codice):** migrazione della pagina Logs verso Grafana, con raccolta tramite Alloy e storage in Loki. Al momento di questa analisi non ci sono tracce nel repository di configurazione Alloy/Loki/Grafana: l'integrazione andrebbe progettata da zero (probabile: Alloy che legge i file in `./logs` sull'host xhub, o i log passati a stdout dei container, e li spedisce a Loki).

## CI/CD & Deployment

**Hosting:** host self-managed **xhub**, definito in un repository separato (`~/source/homelab-infra/hosts/xhub/ddunlimited-search`), non in questo repository.

**Pipeline CI:** nessuna (`.github/` assente, nessun file di workflow).

**Build immagine:** manuale, eseguita direttamente su xhub (x86_64) perché la macchina di sviluppo è arm64 e l'immagine non transita da Docker Hub (`Dockerfile` in root, nessun passo di build automatizzato nel repo).

**Deploy:** `docker-compose.yml` definisce due servizi (`web`, `scheduler`) che condividono la stessa immagine (`build: .`) e gli stessi volumi (`./data`, `./pages.txt`, `./logs`); il riavvio dei container è un'operazione manuale dell'utente.

## Environment Configuration

**Variabili richieste/rilevanti (riferimento completo in `.env.example` e `src/config.py`):**
- `DDU_USERNAME`, `DDU_PASSWORD` — credenziali forum (di fatto non usate per il login automatico, vedi sezione Cloudflare sopra; restano come fallback/placeholder)
- `SESSION_TOKEN` — segreto condiviso con l'estensione browser per `/api/session`
- `DATABASE_PATH`, `SESSION_FILE`, `PAGES_FILE` — path su volume condiviso
- `TMDB_API_KEY`, `TMDB_LANGUAGE`, `TMDB_REQUEST_DELAY`
- `OMDB_API_KEY`, `OMDB_DAILY_LIMIT`
- `RATINGS_ENABLED`, `RATING_MIN_CONFIDENCE`, `RATING_BATCH_SIZE`, `RATING_MAX_PER_RUN`
- `SCRAPE_ENABLED`, `SCRAPE_INTERVAL_DAYS`, `SCRAPE_HOUR`, `SCRAPE_MINUTE` (sovrascrivibili da UI admin, valore in DB vince)
- `REQUEST_DELAY`, `REQUEST_TIMEOUT`, `POST_DETAIL_WORKERS`, `POST_RECHECK_DAYS`
- `FLASK_HOST`, `FLASK_PORT`, `FLASK_DEBUG`, `LOG_LEVEL`

**Ubicazione segreti:** file `.env` locale/produzione (non tracciato in git); in produzione le variabili sono passate ai container via `docker-compose.yml` (che le legge a sua volta dall'ambiente/`.env` dell'host xhub).

## Webhooks & Callbacks

**In ingresso:**
- `POST /api/session` (`src/server.py:328-393`) è di fatto un webhook: riceve i cookie catturati dall'estensione browser, autenticato via header `X-Session-Token`. Non è un webhook di terze parti standard, ma un canale custom fra estensione e backend.

**In uscita:** nessuno (nessuna chiamata push verso servizi esterni all'evento di un'azione utente).

---

*Integration audit: 2026-09-12*
