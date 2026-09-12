# Codebase Structure

**Analysis Date:** 2026-09-12

## Directory Layout

```
ddunlimited-search/
├── src/
│   ├── server.py            # Flask app: route HTML + JSON API
│   ├── scraper.py           # DDUnlimitedScraper: auth, fetch, parsing orchestration
│   ├── parser.py            # Parsing HTML (pagine indice + dettaglio post)
│   ├── ratings.py           # Matching TMDB + voti IMDb via OMDb
│   ├── scheduler.py         # Loop periodico import/enrichment (container "scheduler")
│   ├── database.py          # Schema SQLite, tutte le query
│   ├── session_store.py     # Persistenza cookie browser condivisi (session.json)
│   ├── config.py            # Lettura centralizzata delle env var
│   ├── templates/           # 7 pagine Jinja, nessuna inheritance (vedi sotto)
│   └── static/
│       └── style.css        # Unico foglio di stile condiviso (411 righe)
├── data/                    # Volume: ddunlimited.db + session.json (non committato)
├── logs/                    # Volume: web.log, scraper.log, scheduler.log, ratings.log
├── pages.txt                # Config testuale: sezioni forum da scrapare
├── .env.example             # Template variabili d'ambiente (nessun segreto)
├── Dockerfile                # Immagine unica, build su xhub (x86_64)
├── docker-compose.yml        # Due servizi: web (porta esposta) e scheduler (nessuna porta)
├── docker-entrypoint.sh      # Verifica struttura file all'avvio container, poi exec
├── run_scraper.sh            # Script di import manuale via cron/CLI
├── init.sh                   # Setup locale
├── push_to_dockerhub.sh       # Script di pubblicazione immagine (non usato in produzione)
├── requirements.txt           # requests, beautifulsoup4, flask, python-dotenv
└── .planning/                 # Documenti GSD (sketches, spike, codebase map)
```

## Directory Purposes

**`src/`:**
- Purpose: Tutto il codice applicativo, sia web che batch/scheduler.
- Contains: moduli Python piatti (nessun package annidato oltre `templates/`/`static/`), nessun `__init__.py` con logica (solo marker vuoto).
- Key files: `server.py` (entry point web), `scheduler.py` (entry point batch), `database.py` (unico punto di accesso a SQLite).

**`src/templates/`:**
- Purpose: 7 pagine HTML complete, renderizzate da Flask con Jinja solo per i dati iniettati lato server (liste sezioni, stats, nome sezione). Tutta l'interattività (ricerca, filtri, paginazione, polling stato import) è JavaScript vanilla inline nello stesso file.
- Contains: `<style>` inline per-pagina oltre al CSS condiviso, `<script>` inline con `fetch()` verso `/api/*`.
- Key files: vedi tabella "Route Flask" e "Template Jinja" sotto.

**`src/static/`:**
- Purpose: Unico asset servito da Flask via `url_for('static', filename=...)`.
- Contains: `style.css` — variabili di tema scure (`#1a1a2e`, `#16213e`, accent `#3498db`/`#0f4c75`), regole per header/nav/search-form/results-list/pagination condivise da tutte le pagine. Nessun JS esterno: ogni pagina porta il proprio `<script>` inline.
- Generated: No. Committed: Sì.

**`data/` e `logs/`:**
- Purpose: Volumi Docker montati da entrambi i container (`docker-compose.yml`); `data/ddunlimited.db` è l'unico stato condiviso fra web e scheduler, `data/session.json` la sessione browser condivisa.
- Generated: Sì (creati a runtime). Committed: No (in `.gitignore`).

## Key File Locations

**Entry Points:**
- `src/server.py:843` (`main()`): avvia il container "web" (`CMD` nel `Dockerfile`).
- `src/scheduler.py:155` (`main()`): avvia il container "scheduler" (`command` in `docker-compose.yml`).
- `src/scraper.py:631`, `src/ratings.py:500`: eseguibili anche standalone da CLI per import/enrichment manuale.

**Configuration:**
- `src/config.py`: unico punto di lettura delle env var (nessun default con segreti).
- `.env.example`: elenco delle variabili attese (non contiene valori reali).
- `pages.txt`: elenco `Sezione | URL | Pagina` delle pagine forum da importare, editabile anche da `/admin` via `/api/pages`.

**Core Logic:**
- `src/database.py`: schema, migrazioni idempotenti, tutte le query di ricerca/filtro/statistiche.
- `src/parser.py`: estrazione titoli da pagina indice (`parse_page`) e metadati da post singolo (`parse_post_detail`).
- `src/ratings.py`: pulizia titolo, ricerca/scoring TMDB, arricchimento voto IMDb via OMDb.

**Testing:**
- Non presente alcuna directory di test (`tests/`) né framework configurato nel repository.

## Route Flask — pagine HTML

| Route | Metodi | View | Template | Query dati |
|---|---|---|---|---|
| `/` | GET | `index()` `src/server.py:76` | `index.html` | `database.get_all_sections()`, `database.get_stats()` |
| `/sections` | GET | `sections_page()` `src/server.py:200` | `sections.html` | `database.get_all_sections()` |
| `/sections/<section>` | GET | `section_detail_page()` `src/server.py:207` | `section_detail.html` | valida sezione con `get_all_sections()`, poi `database.get_section_stats(section)` |
| `/sections/missing-data` | GET | `missing_data_page()` `src/server.py:219` | `missing_data.html` | `database.get_all_sections()` |
| `/ratings` | GET | `ratings_page()` `src/server.py:679` | `ratings.html` | `database.get_all_sections()` |
| `/admin` | GET | `admin_page()` `src/server.py:194` | `admin.html` | nessuna query server-side (tutto via fetch client-side) |
| `/logs` | GET | `logs_page()` `src/server.py:188` | `logs.html` | nessuna (legge i log via `/api/logs`) — **candidata alla rimozione a favore di Grafana** |

## Route Flask — API JSON

| Route | Metodi | View | Scopo |
|---|---|---|---|
| `/api/search` | GET | `api_search()` `src/server.py:84` | Ricerca titoli: `q`/`director`, `section`, `search_type` (contains/starts_with/ends_with/all_words), `min_rating`, `sort` (title/rating/year/year_asc), paginazione |
| `/api/sections` | GET | `api_sections()` `src/server.py:164` | Elenco sezioni distinte |
| `/api/sections/<section>` | GET | `api_section_titles()` `src/server.py:574` | Titoli di una sezione con filtri `year`, `first_letter`, `quality` + liste valori disponibili |
| `/api/stats` | GET | `api_stats()` `src/server.py:171` | Conteggi totali + info ultima importazione |
| `/api/missing-data` | GET | `api_missing_data()` `src/server.py:633` | Titoli con `director`/`year` NULL, paginati, filtro `section` |
| `/api/logs` | GET | `api_logs()` `src/server.py:226` | Contenuto di `logs/{scraper,scheduler,web}.log`, con `lines`/`offset` — **usata solo da `/logs`, da rimuovere insieme alla pagina** |
| `/api/pages` | GET, POST | `api_pages_get/post()` `src/server.py:269,284` | Legge/scrive `pages.txt`, valida il formato prima di salvare |
| `/api/session` | GET, POST, DELETE | `api_session_get/post/delete()` `src/server.py:321,329,397` | Stato sessione browser, push cookie dall'estensione (con token HMAC), cancellazione |
| `/api/schedule` | GET, POST | `api_schedule_get/post()` `src/server.py:404,414` | Lettura/scrittura schedule import (interval_days, hour, minute, enabled) |
| `/api/import/single` | POST | `api_import_single()` `src/server.py:442` | Import di una singola pagina in thread background |
| `/api/import/all` | POST | `api_import_all()` `src/server.py:509` | Import completo da `pages.txt` in thread background |
| `/api/import/status` | GET | `api_import_status()` `src/server.py:559` | Stato del thread di import in corso (polling da `admin.html`) |
| `/api/ratings/status` | GET | `api_ratings_status()` `src/server.py:686` | Config e contatori enrichment (`database.get_rating_stats()`) |
| `/api/ratings/enrich` | POST | `api_ratings_enrich()` `src/server.py:700` | Avvia enrichment in thread background (`ratings.run_enrichment`) |
| `/api/ratings/review` | GET | `api_ratings_review()` `src/server.py:746` | Elenco match da rivedere per stato (`low_confidence`/`unmatched`/`rejected`/`matched`/`manual`/`pending`) |
| `/api/ratings/match` | POST | `api_ratings_match()` `src/server.py:788` | Aggancio manuale a un id/URL TMDB |
| `/api/ratings/reject` | POST | `api_ratings_reject()` `src/server.py:820` | Segna un match come sbagliato |
| `/api/ratings/reset` | POST | `api_ratings_reset()` `src/server.py:832` | Rimette un titolo in coda per il prossimo match |

## Template Jinja

Nessun template usa `{% extends %}` o `{% include %}`: ogni file è un documento HTML completo e indipendente (nessun `base.html`). L'unico elemento davvero condiviso è `src/static/style.css`, linkato identicamente in ogni `<head>`. Il blocco `<nav>` (Ricerca / Sezioni / Voti / Amministrazione / Logs) è invece duplicato manualmente in ogni template.

| Template | Righe | Route che lo usa | Contenuto Jinja | JS inline |
|---|---|---|---|---|
| `index.html` | 473 | `/` | `{{ stats.* }}`, loop `{% for section in sections %}` per la `<select>` | Ricerca live con debounce, rendering risultati/poster/rating/chip lingua, paginazione, polling `/api/stats` per "ultima importazione" |
| `sections.html` | 89 | `/sections` | loop `{% for section in sections %}` per le card | Nessuno (solo link statici) |
| `section_detail.html` | 418 | `/sections/<section>` | `{{ section }}` nel titolo/heading | Fetch `/api/sections/<section>`, filtri dinamici anno/lettera/qualità, paginazione |
| `missing_data.html` | 382 | `/sections/missing-data` | loop sezioni per filtro | Fetch `/api/missing-data`, filtro per sezione, paginazione |
| `ratings.html` | 464 | `/ratings` | loop sezioni per filtro | Fetch `/api/ratings/status`, `/api/ratings/review`, azioni match/reject/reset, avvio enrichment |
| `admin.html` | 681 | `/admin` | nessuno (form statici) | Fetch `/api/pages`, `/api/session`, `/api/schedule`, `/api/import/*`, polling `/api/import/status` |
| `logs.html` | 292 | `/logs` | nessuno | Fetch `/api/logs`, tab per file di log, auto-scroll — **da eliminare insieme alla route e a `/api/logs` quando Grafana sostituisce questa pagina** |

## Naming Conventions

**Files:**
- Moduli Python: snake_case, un modulo per responsabilità (`database.py`, `session_store.py`), nessun sotto-package.
- Template: snake_case coerente col nome della route (`section_detail.html` per `/sections/<section>`).

**Directories:**
- Solo due directory sotto `src/`: `templates/` e `static/` (convenzione standard Flask, nessuna struttura per-feature).

**Funzioni/variabili Python:**
- snake_case per funzioni e variabili; PascalCase per l'unica classe rilevante (`DDUnlimitedScraper`, `TMDBClient`).
- Costanti SQL condivise in maiuscolo (`RATING_JOIN`, `RATING_COLUMNS`, `RATING_SCORE_SQL` in `src/database.py:890-900`).

**JS inline:**
- camelCase per funzioni/variabili (`performSearch`, `renderResults`, `currentPage`), stesso stile ripetuto identico in `index.html`, `section_detail.html`, `missing_data.html`.

## Where to Add New Code

**Nuova route/pagina:**
- View function in `src/server.py`, template dedicato in `src/templates/` con lo stesso pattern standalone (niente `base.html` ancora — vedi anti-pattern in ARCHITECTURE.md se si introduce la UI v2 con layout condiviso).

**Nuova query di ricerca/filtro:**
- Aggiungere la funzione in `src/database.py`, riusando `RATING_JOIN`/`RATING_COLUMNS`/`RATING_SCORE_SQL` se il risultato deve includere i voti.

**Nuovo campo estratto dal forum:**
- Logica di estrazione in `src/parser.py` (pattern regex già presenti per qualità, lingua, metadata); persistenza tramite `database.insert_title()`/`database.init_db()` (aggiungere colonna con `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, seguendo lo stile esistente).

**Nuovo provider esterno (es. altro catalogo voti):**
- Nuovo client in `src/ratings.py` sul modello di `TMDBClient`, con propria funzione `main()`/`run_*` richiamabile sia da `server.py` (thread on-demand) sia da `scheduler.py` (loop periodico).

**Asset statici per la UI v2:**
- `src/static/`: restare su CSS puro e JS vanilla per rispettare il vincolo zero-build del progetto; eventuali nuovi file JS condivisi vanno qui, non inline, per essere riusabili fra le pagine ricostruite.

## Special Directories

**`.planning/`:**
- Purpose: Documenti di pianificazione GSD — sketch della UI v2 (`sketches/001-004`), spike tecnici chiusi (`spikes/001-filebot-matching`), e questa mappa del codebase (`codebase/`).
- Generated: No (scritti da Claude/utente). Committed: Sì.

**`data/` e `logs/`:**
- Purpose: Volumi runtime montati in produzione (vedi `docker-compose.yml`), assenti nel repository.
- Generated: Sì. Committed: No.

---

*Structure analysis: 2026-09-12*
