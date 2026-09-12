# Technology Stack

**Analysis Date:** 2026-09-12

## Languages

**Primary:**
- Python 3.11+ (dichiarato in `README.md`; `Dockerfile:1` usa `python:3.11-slim`) — tutta la logica applicativa in `src/`
- Interprete locale di sviluppo: Python 3.14.3 (non vincolante, l'immagine di produzione resta 3.11-slim)

**Secondario:**
- HTML/Jinja2 nei template (`src/templates/*.html`)
- CSS vanilla, un unico file (`src/static/style.css`)
- JavaScript vanilla inline nei template (nessun bundler, nessun modulo separato)
- Bash per lo start dei container (`docker-entrypoint.sh`, `run_scraper.sh`)

**Zero build, esplicito nel README di progetto:** niente npm, niente framework frontend, niente React/Tailwind. La UI è Flask + Jinja + CSS/JS scritti a mano.

## Runtime

**Ambiente:**
- Python 3.11-slim (immagine Docker, `Dockerfile:1`)
- `PYTHONPATH=/app/src` impostato nell'immagine (`Dockerfile`)

**Gestore pacchetti:**
- pip, dipendenze elencate in `requirements.txt` con vincoli `>=` (nessun upper bound)
- Nessun lockfile (niente `requirements.lock`, `Pipfile.lock`, `poetry.lock`): le build sono riproducibili solo per versione minima, non per versione esatta

## Frameworks

**Core:**
- Flask >= 3.0.0 (`requirements.txt`) — app web in `src/server.py`
- Jinja2 (incluso in Flask) — template server-side in `src/templates/`
- Werkzeug (`werkzeug.serving.WSGIRequestHandler`, sottoclassato in `src/server.py:52-57` per instradare il log delle richieste HTTP sul logger applicativo invece che su stdout)

**Testing:**
- Nessun framework di test presente nel repository (nessun file `test_*.py`, nessuna directory `tests/`, nessuna dipendenza pytest in `requirements.txt`)

**Build/Dev:**
- Nessun tool di build: zero npm, zero bundler JS/CSS
- `python-dotenv` >= 1.0.0 per caricare `.env` in sviluppo (`src/config.py:5-6`)

## Key Dependencies

**Critiche:**
- `flask` >= 3.0.0 — server HTTP e routing (`src/server.py`)
- `requests` >= 2.31.0 — client HTTP verso il forum, TMDB e OMDb (`src/scraper.py`, `src/ratings.py`)
- `beautifulsoup4` >= 4.12.0 — parsing HTML delle pagine del forum (`src/parser.py`)
- `python-dotenv` >= 1.0.0 — caricamento configurazione da `.env` (`src/config.py`)

**Infrastruttura:**
- `sqlite3` (libreria standard Python, non in requirements.txt) — unico storage persistente, file su disco (`src/database.py`)
- `cron` installato via apt nell'immagine Docker (`Dockerfile:7-9`) ma non risulta usato attivamente nel codice Python: la schedulazione degli import è gestita interamente dal loop Python in `src/scheduler.py`, non da crontab

## Configuration

**Environment:**
- Caricamento via `python-dotenv` da file `.env` (`src/config.py:6`), con default hardcoded per ogni variabile in `src/config.py`
- Riferimento completo delle variabili supportate e dei loro default: `.env.example`
- Alcune impostazioni (schedulazione import) sono sovrascrivibili a runtime dalla UI admin e salvate nella tabella SQLite `settings` — vedi `database.get_schedule()` in `src/database.py:675-690`; i valori in `settings` hanno priorità sulle variabili d'ambiente
- **Segreti presenti:** `.env.example` esiste (solo placeholder), il vero `.env` non è tracciato — contiene credenziali forum (`DDU_USERNAME`/`DDU_PASSWORD`), `SESSION_TOKEN`, `TMDB_API_KEY`, `OMDB_API_KEY`. Contenuto non letto/riportato in questo audit.

**Build:**
- Nessun file di build frontend (niente `package.json`, `tsconfig.json`, `vite.config.*`, ecc.)
- `Dockerfile` (root del repo) è l'unico artefatto di build

## Platform Requirements

**Sviluppo:**
- Python 3.11+ locale, oppure Docker + Docker Compose (`docker-compose.yml`)
- File `pages.txt` con l'elenco delle sezioni/URL del forum da scrapare (formato descritto in testa al file stesso)

**Produzione:**
- Host **xhub** (definito in `~/source/homelab-infra/hosts/xhub/ddunlimited-search`, repo separato)
- Due container sulla stessa immagine Docker:
  - `web` — `python src/server.py` (comando di default del `Dockerfile`), espone la porta 5000
  - `scheduler` — `python src/scheduler.py` (comando esplicito in `docker-compose.yml`)
- L'immagine si builda **direttamente su xhub** perché l'host è x86_64 e la macchina di sviluppo (Mac) è arm64; non passa da Docker Hub né da build cross-arch
- Volumi condivisi tra i due container: `./data` (database SQLite + `session.json`), `./pages.txt`, `./logs` — è il meccanismo con cui web e scheduler si scambiano stato senza un servizio dati esterno
- Il riavvio dei container in produzione è un'azione manuale dell'utente, non automatizzata da CI/CD

---

*Stack analysis: 2026-09-12*
