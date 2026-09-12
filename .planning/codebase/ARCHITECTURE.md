<!-- refreshed: 2026-09-12 -->
# Architecture

**Analysis Date:** 2026-09-12

## System Overview

```text
┌───────────────────────────────────────────────────────────────────────┐
│                     Container "web" (Flask, gunicorn-free)            │
│  `src/server.py` — routes HTML + JSON API, spawns background threads  │
├──────────────────────────┬──────────────────────────┬─────────────────┤
│  Jinja templates          │  Static assets           │  Session relay  │
│  `src/templates/*.html`   │  `src/static/style.css`  │  `src/session_  │
│  (no inheritance, each    │  (unico foglio di stile, │  store.py`      │
│  file è standalone)       │  nessun bundler)          │                 │
└──────────────────────────┴──────────────────────────┴─────────────────┘
                 │                                          ▲
                 ▼                                          │ cookie push
┌───────────────────────────────────────────────────────────────────────┐
│                    Livello dati e dominio (condiviso)                 │
│  `src/database.py`  — SQLite, query e schema                          │
│  `src/parser.py`    — HTML parsing delle pagine forum e dei post      │
│  `src/ratings.py`   — matching TMDB + voti IMDb via OMDb              │
│  `src/config.py`    — tutte le env var, nessun default hard-coded     │
└───────────────────────────────────────────────────────────────────────┘
                 ▲
                 │ stesse funzioni Python, stesso file DB
┌───────────────────────────────────────────────────────────────────────┐
│              Container "scheduler" (nessuna route HTTP)               │
│  `src/scheduler.py` — loop di polling (60s) che decide se lanciare    │
│  `src/scraper.py`   — DDUnlimitedScraper: login/sessione, fetch,      │
│                        parsing pagine, thread pool dettagli post      │
└───────────────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│   SQLite su volume condiviso: `data/ddunlimited.db`                    │
│   File di sessione condiviso: `data/session.json`                      │
└───────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Componente | Responsabilità | File |
|-----------|----------------|------|
| Flask app | Route HTML/JSON, thread per import/enrichment on-demand, logging web | `src/server.py` |
| Database layer | Schema SQLite, query di ricerca/paginazione, tabelle settings/import_history/title_ratings | `src/database.py` |
| Parser | Estrazione titoli dalla pagina indice e dei metadati dal singolo post | `src/parser.py` |
| Scraper | Autenticazione (sessione browser o login), fetch con retry/backoff, orchestrazione import | `src/scraper.py` |
| Ratings | Match contro TMDB (titolo+regista+anno), arricchimento voto IMDb via OMDb, budget giornaliero | `src/ratings.py` |
| Session store | Persistenza atomica dei cookie del browser su file JSON condiviso | `src/session_store.py` |
| Scheduler | Loop indipendente che decide quando lanciare import/enrichment automatici | `src/scheduler.py` |
| Config | Lettura centralizzata di tutte le env var (nessun default sensibile hard-coded) | `src/config.py` |

## Pattern Overview

**Overall:** Monolite Flask a due processi (web + scheduler) che condividono lo stesso codice Python e lo stesso file SQLite. Nessun ORM, nessuna API REST versionata, nessun frontend build — ogni pagina HTML è autosufficiente con CSS/JS inline oltre al foglio condiviso.

**Key Characteristics:**
- Zero build: i template Jinja **non fanno client-side rendering con framework**; il JS inline in ogni pagina chiama `fetch()` sugli endpoint `/api/*` e costruisce l'HTML dei risultati con template string.
- Nessun livello di autenticazione utente per l'app stessa (uso personale): l'unica autenticazione è quella verso il forum esterno (scraper) e un token condiviso per il relay della sessione (`X-Session-Token`).
- Stato applicativo minimo tenuto in memoria di processo (`import_status`, `ratings_status` in `src/server.py:62-72`) — non sopravvive a un riavvio e non è condiviso fra i due container.
- Persistenza runtime (schedule, contatori OMDb) nella tabella `settings` di SQLite proprio perché i due container non condividono memoria (`src/database.py:206-214`).

## Layers

**Presentazione (Flask routes + Jinja):**
- Purpose: Rendere le pagine HTML e rispondere alle chiamate JSON del frontend.
- Location: `src/server.py`, `src/templates/`
- Contains: view function, validazione dei query param, `jsonify`.
- Depends on: `database.py`, `parser.py`, `ratings.py`, `scraper.py`, `session_store.py`, `config.py`.
- Used by: browser dell'utente (HTML + fetch JS).

**Dominio/servizi (import e arricchimento):**
- Purpose: Logica di business — scraping del forum, parsing HTML, matching con cataloghi esterni.
- Location: `src/scraper.py`, `src/parser.py`, `src/ratings.py`
- Contains: classi/funzioni pure, nessuna dipendenza da Flask.
- Depends on: `database.py`, `config.py`, `session_store.py` (solo scraper).
- Used by: sia `server.py` (thread on-demand) sia `scheduler.py` (loop periodico).

**Persistenza (SQLite):**
- Purpose: Unico stato condiviso fra i due container.
- Location: `src/database.py`, file `data/ddunlimited.db`
- Contains: funzioni CRUD dirette con `sqlite3`, nessun ORM; context manager `get_db()` con commit/rollback automatico (`src/database.py:20-31`).
- Depends on: `config.DATABASE_PATH`.
- Used by: tutti gli altri moduli.

## Data Flow

### Ricerca (flusso principale, pagina `/`)

1. L'utente digita in `#query` o `#director` in `src/templates/index.html:27-40`; un debounce di 300ms (`src/templates/index.html:120-143`) evita una richiesta per ogni tasto, e serve almeno 2 caratteri (`hasSearchCriteria`, `src/templates/index.html:113-117`).
2. Il JS inline compone i query param (`q`, `director`, `section`, `search_type`, `include_deleted`, `min_rating`, `sort`, `page`) e chiama `fetch('/api/search?...')` (`src/templates/index.html:192-239`).
3. `api_search()` in `src/server.py:83-160` valida e normalizza i parametri (clamp `page`/`per_page`, whitelist di `search_type` e `sort`, range check su `min_rating`) poi chiama `database.search_titles(...)`.
4. `database.search_titles()` (`src/database.py:377-478`) costruisce dinamicamente la clausola `WHERE` in base a `search_type` (`contains` → `LIKE %q%`, `starts_with`, `ends_with`, `all_words` → AND di `LIKE` per parola), aggiunge il filtro `section`, il filtro `min_rating` tramite `RATING_SCORE_SQL = COALESCE(imdb_rating, tmdb_rating)`, fa un `LEFT JOIN` su `title_ratings` (`RATING_JOIN`, riga 894) e pagina con `LIMIT`/`OFFSET`.
5. Il risultato torna come JSON con `results` e blocco `pagination` (`src/server.py:144-160`).
6. `renderResults()` nel template disegna la lista: poster TMDB (`buildPoster`, righe 389-395), badge voto con sorgente IMDb/TMDB (`buildRating`, righe 397-423), chip lingua/audio/video/sub ricostruiti dal campo `metadata`/`languages` (`buildChips`, righe 325-385), e i controlli di paginazione (righe 288-306).

**Sezioni (`/sections/<section>`):** flusso analogo ma via `database.get_section_titles()` (`src/database.py:724-814`), con filtri distinti `year`, `first_letter`, `quality` popolati dinamicamente da query `SELECT DISTINCT` sulla stessa sezione (righe 787-806); nessuna ricerca testuale, solo browsing filtrato.

**State Management:**
- Nessuno stato lato client persistente (no localStorage/sessionStorage): ogni pagina ricostruisce lo stato di ricerca/filtri in variabili JS locali (`currentPage`, `currentYear`, ecc.) perse al reload.
- Lo stato di import/enrichment in corso è tenuto in dict Python globali (`import_status`, `ratings_status`) e interrogato via polling da `admin.html` e `ratings.html`.

## Key Abstractions

**Riga di catalogo (`titles` + `title_ratings`):**
- Purpose: Un titolo forum arricchito con i metadati di rating in un `LEFT JOIN`; la tabella `title_ratings` è tenuta separata perché una riga lì significa "già cercato", indipendentemente dall'esito (`src/database.py:216-218`).
- Examples: `RATING_JOIN`, `RATING_COLUMNS`, `RATING_SCORE_SQL` in `src/database.py:890-900`.
- Pattern: query che uniscono sempre attraverso queste tre costanti condivise, per evitare divergenze fra le viste di ricerca/sezione/review.

**Pagina forum come sorgente di verità per import (`pages.txt`):**
- Purpose: File di configurazione testuale (`Section | URL | Page`) che elenca le pagine indice del forum da scrapare.
- Examples: `parser.parse_pages_file()` (`src/parser.py:438-477`), editabile dall'admin UI via `/api/pages` (`src/server.py:268-317`).
- Pattern: validato scrivendo su file temporaneo e riparsando prima di salvare (`src/server.py:293-307`).

**Sessione browser condivisa (`session.json`):**
- Purpose: Aggira la sfida JS di Cloudflare sul login: i cookie di un browser già loggato vengono spinti da un'estensione e riusati sia dal container web (per la verifica) sia dallo scheduler (per lo scraping) (`src/session_store.py:1-7`).
- Examples: `session_store.save/refresh/load` (`src/session_store.py:81-143`), scrittura atomica via file temporaneo + `os.replace` per evitare letture a metà da un altro container (righe 92-106).

## Entry Points

**`src/server.py` (`main()`, riga 843):**
- Location: `src/server.py:843-875`
- Triggers: `CMD ["python", "src/server.py"]` nel `Dockerfile` (container "web").
- Responsibilities: inizializza/migra il DB, avvia `app.run()` con host/porta da `config.py`.

**`src/scheduler.py` (`main()`, riga 155):**
- Location: `src/scheduler.py:155-196`
- Triggers: `command: ["python", "src/scheduler.py"]` nel container "scheduler" (`docker-compose.yml`).
- Responsibilities: loop infinito che ogni `POLL_SECONDS=60` rilegge lo schedule dalla tabella `settings`, decide se lanciare `run_import()` e/o `run_ratings()`.

**`src/scraper.py` (`main()`, riga 631) e `src/ratings.py` (`main()`, riga 500):**
- Location: eseguibili anche standalone da CLI per debug/manutenzione manuale.

## Architectural Constraints

- **Threading:** Flask gira in modalità single-process con `WSGIRequestHandler` custom per il logging (`src/server.py:52-58`); gli import e gli enrichment on-demand partono su `threading.Thread(daemon=True)` (es. `src/server.py:493-494`, `741`), mentre lo scraper usa un `ThreadPoolExecutor` con `POST_DETAIL_WORKERS` worker per i dettagli dei singoli post (`src/scraper.py:401`).
- **Global state:** `import_status` e `ratings_status` sono dict a livello di modulo in `src/server.py:62-72`, mutati dai thread di background senza lock — accettabile solo perché letti per polling non critico dall'admin UI.
- **Due processi, un solo DB:** web e scheduler non comunicano direttamente; ogni coordinamento (schedule, budget OMDb giornaliero, stato ultima importazione) passa dalla tabella `settings`/`import_history` in SQLite (`src/database.py:591-690`).
- **Nessuna migrazione con tool dedicato:** lo schema evolve con `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idempotenti dentro `database.init_db()` (`src/database.py:124-244`) e con migrazioni one-off gestite via flag in `settings` (`migrate_refresh_policy`, `src/database.py:615-661`).

## Anti-Patterns

### SQL costruito per concatenazione di stringhe

**What happens:** Le funzioni di ricerca (`search_titles`, `get_section_titles`, `get_rating_matches`) costruiscono `base_query` concatenando frammenti di `WHERE`/`ORDER BY` (`src/database.py:436-474`, `724-814`, `1071-1113`).
**Why it's wrong:** I valori sono comunque parametrizzati (`?`), quindi non c'è SQL injection diretta, ma la logica di costruzione query è duplicata tre volte con piccole differenze, rendendo facile introdurre un'incoerenza (es. dimenticare `deleted_at IS NULL` in una nuova query).
**Do this instead:** Se si aggiunge una nuova vista filtrata, riusare `RATING_JOIN`/`RATING_COLUMNS`/`RATING_SCORE_SQL` come già fatto, e centralizzare i filtri comuni (`deleted_at IS NULL`, `section = ?`) in un helper condiviso prima di introdurre nuove viste per la UI v2.

### Pagine HTML monolitiche senza layout condiviso

**What happens:** Ogni template (`admin.html`, `ratings.html`, `section_detail.html`, ecc.) ripete integralmente `<head>`, il blocco `<nav>` di navigazione e spesso interi blocchi CSS quasi identici (es. `.filter-btn` duplicato in `section_detail.html` e `missing_data.html`).
**Why it's wrong:** Un cambio alla navigazione o al tema richiede modifiche ripetute in 7 file; è la ragione esplicita per cui la UI v2 viene ricostruita da zero invece di essere modificata pagina per pagina.
**Do this instead:** Nella UI v2, introdurre un vero `base.html` con `{% block %}` e spostare il CSS ripetuto in `style.css`, mantenendo comunque zero build (solo template Jinja, nessun bundler).

## Error Handling

**Strategy:** Ogni endpoint `/api/*` cattura le eccezioni localmente e risponde con `jsonify({'error': ...})` e status code esplicito (400/401/404/409/422/500/502/503); non esiste un error handler globale Flask (`@app.errorhandler`).

**Patterns:**
- Validazione difensiva con fallback silenzioso ai default per i parametri di query non validi (`page`, `per_page`, `search_type`, `sort`, `min_rating` in `src/server.py:112-126`) invece di restituire 400.
- Lo scraper distingue esplicitamente 404 (pagina/post rimosso → soft delete, `src/database.py:366-374`) da altri errori HTTP, con retry ed exponential backoff su 429/503 (`src/scraper.py:240-264`).
- `RatingsError` (`src/ratings.py:61-62`) è l'unica eccezione di dominio custom: usata per interrompere subito il job quando una API key è rifiutata, invece di continuare a fallire in loop.

## Cross-Cutting Concerns

**Logging:** Logger Python distinti e non propaganti per dominio — `web` (`src/server.py:23-41`, file `logs/web.log`), `scraper` (`src/scraper.py:24-41`, `logs/scraper.log`), `ratings` (`src/ratings.py:24-32`, `logs/ratings.log`), e il logger root di `scheduler.py` (`logs/scheduler.log`). La pagina `/logs` legge questi file via `/api/logs` — **è la pagina esplicitamente candidata alla rimozione** a favore di Grafana (vedi sezione dedicata in STRUCTURE.md).

**Validation:** Interamente manuale nei view Flask (nessuna libreria tipo Marshmallow/Pydantic); whitelist inline per enum (`search_type`, `sort`, `status` delle ratings) e clamp numerici.

**Authentication:** Nessuna per l'app stessa. Verso il forum: sessione browser relayata con token condiviso HMAC-compare (`src/server.py:341-344`) o fallback a login utente/password (`src/scraper.py:139-199`).

---

*Architecture analysis: 2026-09-12*
