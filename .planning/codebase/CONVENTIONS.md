# Coding Conventions

**Analysis Date:** 2026-09-12

## Naming Patterns

**File Python (`src/*.py`):**
- Un modulo per responsabilità, nome minuscolo senza underscore composti lunghi: `server.py`, `database.py`, `parser.py`, `ratings.py`, `scraper.py`, `scheduler.py`, `session_store.py`, `config.py`
- Import sempre assoluti dentro `src/` (niente package `src.`, i moduli si importano come top-level: `import config`, `import database`) — questo funziona perché l'entry point aggiunge `src/` al path/lavora da dentro quella directory

**Funzioni Python:**
- `snake_case` ovunque, verbo iniziale descrittivo: `get_all_sections`, `insert_title`, `save_rating`, `extract_director_and_year`
- Funzioni "getter" che leggono dal DB iniziano quasi sempre con `get_`; le funzioni che scrivono con `save_`/`set_`/`insert_`/`delete_`
- Handler Flask nominati `<risorsa>_page` per le view HTML (`index`, `admin_page`, `ratings_page`) e `api_<risorsa>[_<verbo>]` per le route JSON (`api_search`, `api_ratings_enrich`), vedi `src/server.py`

**Variabili:**
- `snake_case`; costanti di modulo in `UPPER_CASE` anche quando sono stringhe SQL riusate, es. `RATING_JOIN`, `RATING_COLUMNS`, `RATING_SCORE_SQL` in `src/database.py:892-900`
- Nessuna Hungarian notation, nessun prefisso privato con underscore salvo poche funzioni interne (`_person_key`, `_omdb_budget_left` in `src/ratings.py`)

**Tipi/dataclass:**
- Non ci sono `class` per modelli dati: le righe DB restano `sqlite3.Row` convertite a `dict` all'uscita delle funzioni di `database.py` (`[dict(row) for row in cursor.fetchall()]`)
- Le uniche classi sono comportamentali: `DDUnlimitedScraper` in `src/scraper.py`, `TMDBClient` in `src/ratings.py`, l'eccezione `RatingsError` in `src/ratings.py:61`

## Code Style

**Formattazione:**
- Nessun formatter configurato (niente Black, niente `pyproject.toml`, niente `.editorconfig`). Lo stile è quello lasciato a mano: indentazione a 4 spazi, righe spesso oltre 100 caratteri quando servono per query SQL o f-string di log
- Docstring in stile Google/triple-quote con `Args:`/`Returns:` quando la funzione ha più di un paio di parametri (esempio in `src/database.py:246-259`, `search_titles` in `src/database.py:377-403`)

**Linting:**
- Nessun linter configurato: non esistono `.flake8`, `ruff.toml`, `pyproject.toml` con sezione `[tool.ruff]`, né hook di pre-commit. `requirements.txt` contiene solo dipendenze runtime (`requests`, `beautifulsoup4`, `flask`, `python-dotenv`), nessuna dipendenza di sviluppo
- Se si introduce un linter per la UI v2, va aggiunto da zero (config + comando + eventualmente CI), non c'è nulla da cui ripartire

## Import Organization

**Ordine osservato (es. `src/server.py:1-16`, `src/database.py:1-10`):**
1. Standard library (`os`, `re`, `sqlite3`, `hmac`, `logging`, `sys`, `threading`, `contextlib`, `datetime`)
2. Librerie terze (`flask`, `werkzeug`, `requests`, `dotenv`)
3. Moduli locali del progetto, in ordine alfabetico: `config`, `database`, `parser`, `ratings`, `scraper`, `session_store`

**Alias di percorso:**
- Nessuno. Non c'è un pattern `src/` come package installabile; i file si eseguono e si importano relativamente alla working directory `src/`

**Import locali dentro le funzioni:**
- Pratica tollerata per evitare dipendenze circolari o import pesanti usati raramente, es. `from datetime import datetime` ripetuto dentro `start_import`, `complete_import`, `set_setting` in `src/database.py` anche se `datetime` è già importato in testa al file — incoerenza minore da non replicare: importare una sola volta in testa al modulo

## Error Handling

**Pattern dominante — try/except ampio con logging e messaggio utente in italiano:**
```python
except Exception as e:
    error_msg = f'Errore: {str(e)}'
    logger.error(f"Error in single import thread: {error_msg}", exc_info=True)
    import_status['message'] = error_msg
```
(`src/server.py:485-488`)

**Eccezioni custom minime:**
- Una sola eccezione di dominio, `RatingsError` (`src/ratings.py:61`), usata per segnalare problemi con le chiavi API TMDB/OMDb o risposte HTTP anomale; viene propagata fino a `server.py` e tradotta in `jsonify({'error': ...}), 502` (`src/server.py:806-807`)
- Il resto del codice usa eccezioni standard di libreria (`sqlite3.IntegrityError`, `requests.RequestException`, `requests.HTTPError`, `ValueError`/`TypeError` per parsing)

**Route Flask:**
- Ogni endpoint valida i parametri a mano (range, tipo, whitelist di valori ammessi) prima di interrogare `database.py`, mai un livello di validazione dichiarativo (niente Marshmallow/Pydantic). Esempio tipico in `src/server.py:591-595`:
```python
if page < 1:
    page = 1
if per_page < 1 or per_page > 100:
    per_page = 50
```
- Gli errori applicativi tornano sempre `jsonify({'error': '...'}), <status>` con messaggi in italiano quando sono rivolti all'utente dell'admin UI, in inglese quando sono più tecnici/interni — l'incoerenza di lingua nei messaggi di errore è preesistente, non un pattern da estendere volutamente

**Database:**
- `src/database.py:20-31`, il context manager `get_db()` fa `commit()` a fine blocco e `rollback()` + re-raise su qualunque eccezione: ogni funzione di `database.py` apre la propria connessione con `with get_db() as conn:`, non esiste un livello di transazione condiviso fra più chiamate

## Logging

**Framework:** modulo `logging` standard, mai `print()` per informazioni di esercizio (i pochi `print()` rimasti sono solo nei branch `if __name__ == "__main__":` per output a terminale, es. `src/database.py:1119`, `src/server.py:855-863`)

**Un logger per modulo, configurato manualmente invece che con `logging.config`:**
```python
web_logger = logging.getLogger('web')
web_logger.setLevel(logging.INFO)
web_logger.handlers.clear()
web_file_handler = logging.FileHandler('logs/web.log', encoding='utf-8')
web_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
web_logger.addHandler(web_file_handler)
web_logger.propagate = False
```
(`src/server.py:23-41`, pattern quasi identico ripetuto in `src/scraper.py:22-41` e `src/ratings.py:24-32`, ognuno scrive nel proprio file in `logs/<nome>.log`)

- Eccezione: `src/scheduler.py:18-26` usa `logging.basicConfig(...)` invece del pattern manuale — incoerenza nota, non un secondo idioma da seguire
- Livello globale controllato da `config.LOG_LEVEL` (env var `LOG_LEVEL`, default `INFO`)
- I messaggi di log sono quasi sempre f-string con contesto (id, url, conteggi), mai logging strutturato/JSON

## Comments

**Quando commentare:**
- Commenti brevi (1-4 righe) per spiegare **perché** una scelta non ovvia è stata fatta, mai per raccontare un fix o una cronologia. Esempio (`src/database.py:280-282`):
```python
# A retitled post is a different film as far as the catalogues go, so its
# match starts over. One corrected by hand is left alone.
```
- Commenti in inglese nel codice sorgente (anche se i messaggi utente/log rivolti all'admin sono spesso in italiano) — per la UI v2 seguire questa stessa separazione: commenti sempre in inglese, testo visibile all'utente in italiano

**Docstring:**
- Ogni funzione pubblica di `database.py`, `ratings.py`, `session_store.py` ha una docstring a una riga o con `Args:`/`Returns:`; le route Flask hanno una docstring breve che a volte include anche i query params accettati (es. `src/server.py:83-97`)
- Nessun uso di type-hints nei docstring stile Sphinx, i tipi vivono nelle annotazioni di funzione

## Function Design

**Dimensione:** le funzioni di `database.py` restano tipicamente sotto le 40 righe; le route Flask con logica di validazione possono arrivare a 60-80 righe (es. `api_search`, `api_import_single`) perché includono validazione inline + chiamata + thread di background, senza estrarre gli step in funzioni più piccole

**Parametri:**
- Funzioni con più di 3-4 parametri li dichiarano quasi tutti keyword-friendly con default espliciti, es. `search_titles(query, section=None, page=1, per_page=50, search_type="contains", ...)` in `src/database.py:377-387`
- Uso di `**fields`/`**kwargs` per i pochi casi con insieme di colonne variabile, es. `save_rating(title_id, match_status, **fields)` in `src/database.py:933`

**Return values:**
- Funzioni di lettura multipla ritornano quasi sempre una tupla `(risultati, totale)` o `(risultati, totale, info_filtri)`, mai un oggetto/dataclass dedicato — vedi `search_titles`, `get_section_titles`, `get_titles_with_missing_data` in `src/database.py`
- Funzioni di scrittura ritornano stringhe di stato invece di enum, es. `insert_title` ritorna `'inserted' | 'updated' | 'unchanged'` (`src/database.py:246-330`)

## Type Hints

- Usati in modo sistematico sulle firme di `database.py`, `ratings.py`, `session_store.py`, `scheduler.py`, `parser.py` (`Optional[str]`, `list[dict]`, `tuple[list[dict], int]`, sintassi `str | None` più recente in `scheduler.py`/`parser.py` mischiata a `Optional[str]` più vecchia altrove — nessuna scelta netta fra le due sintassi, entrambe compaiono nella stessa codebase)
- Non tipizzato: `server.py` (le route Flask non hanno quasi mai annotazioni di ritorno, coerente con lo stile Flask idiomatico) e gran parte di `scraper.py`
- Nessun `mypy`/type checker configurato: i type hints sono documentazione, non verificati automaticamente

## Module Design

**Exports:**
- Nessun `__all__`, nessun barrel file. `src/__init__.py` è vuoto/minimale (il pacchetto non espone un'API pubblica esplicita)
- I moduli si importano per intero (`import database`, poi `database.search_titles(...)`) invece di importare singole funzioni — pattern da mantenere per coerenza

**Costanti condivise:**
- Frammenti SQL riusati vengono tenuti come costanti di modulo vicino alle funzioni che li usano, non centralizzati in un file `queries.py` separato (vedi `RATING_JOIN`/`RATING_COLUMNS`/`RATING_SCORE_SQL` in fondo a `src/database.py`)

---

## Frontend: CSS

**Organizzazione attuale:**
- Un solo foglio di stile globale, `src/static/style.css` (412 righe), caricato da **tutte** le pagine con `<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">` (vedi ogni file in `src/templates/*.html`)
- Ogni pagina (`admin.html`, `logs.html`, `sections.html`, `section_detail.html`, `ratings.html`, `missing_data.html`) aggiunge poi un blocco `<style>` **inline nel `<head>`** con le regole specifiche di quella pagina (es. `.admin-container`, `.admin-section` in `src/templates/admin.html:8-...`, `.panel`/`.counters` in `src/templates/ratings.html:8-...`, `.logs-container`/`.log-tab` in `src/templates/logs.html:8-...`)
- `index.html` è l'unica pagina che non ha un blocco `<style>` proprio: usa solo `style.css` più un paio di stili inline su singoli tag (`style="margin-top: 10px;"` in `src/templates/index.html:15-19`)

**Naming:**
- Classi in `kebab-case` semantico legato al contenuto, non BEM e non utility-first: `.result-item`, `.item-meta`, `.search-row-extra`, `.checkbox-label`, `.deleted-badge`. Modificatori applicati come classe aggiuntiva sullo stesso elemento invece che con sintassi BEM `--modifier`, es. `class="result-item${item.deleted_at ? ' result-deleted' : ''}"` in `src/templates/index.html:267`

**Custom properties / design token:**
- **Nessuna** variabile CSS (`:root { --colore: ... }` non esiste nel progetto). I colori sono valori esadecimali ripetuti letteralmente in decine di punti: `#1a1a2e` (sfondo pagina), `#16213e` (sfondo pannelli/card), `#0f4c75` (blu bottoni), `#333` (bordi) ricorrono identici sia in `style.css` sia nei blocchi `<style>` di `admin.html`, `ratings.html`, `section_detail.html`, `sections.html`
- **Incoerenza da conoscere prima della v2:** `src/templates/logs.html` usa una palette diversa e più chiara per `.log-tab` (`background: #f0f0f0`, hover `#e0e0e0`, stato attivo `#4CAF50`) che stona con il tema scuro usato ovunque altrove — è un'eccezione isolata, non un secondo tema intenzionale
- Nessun preprocessore (Sass/Less/PostCSS), nessuna build step: il CSS scritto è esattamente quello servito

**Cosa significa per la UI v2:**
- Se si tiene lo stile "vanilla senza build", introdurre almeno delle custom property (`:root { --bg, --panel, --accent, ... }`) risolverebbe la duplicazione di colori senza aggiungere alcun tool
- Se si passa a template con blocchi condivisi (vedi sezione Template sotto), i blocchi `<style>` per-pagina andrebbero probabilmente consolidati in un secondo file statico o in un blocco Jinja `{% block extra_style %}` ereditato, invece di essere duplicati pagina per pagina

## Frontend: JavaScript

**Organizzazione:**
- Nessun file `.js` esterno: **tutto il JavaScript vive inline** in un tag `<script>` alla fine del `<body>` di ogni pagina che ne ha bisogno (`index.html:96-471`, `admin.html:344-...`, `ratings.html:225-...`, `logs.html:168-...`, `missing_data.html:235-...`, `section_detail.html:212-...`)
- Nessun modulo ES (`type="module"`), nessun bundler, nessuna dipendenza esterna (niente jQuery, niente framework): solo DOM API native (`document.getElementById`, `fetch`, template literal per costruire HTML)
- Variabili/funzioni dichiarate con `const`/`let` a livello di script, nessun namespace/IIFE che le isoli: ogni pagina è un contesto globale a sé (non c'è conflitto solo perché ogni pagina carica un solo script)

**Pattern di interazione:**
- **Event listener espliciti** per gli input persistenti (`addEventListener('input', ...)`, `addEventListener('change', ...)`, `addEventListener('submit', ...)`), con **debounce manuale** via `setTimeout`/`clearTimeout` sulla ricerca testuale (`src/templates/index.html:120-130`)
- **Attributi inline `onclick="..."`** per gli elementi generati dinamicamente via `innerHTML` (bottoni di paginazione, azioni sulle righe): `<button onclick="goToPage(${pagination.page - 1})">Precedente</button>` (`src/templates/index.html:292`) — non è event delegation, è binding diretto nell'HTML generato lato client, perché le funzioni (`goToPage`) sono definite nello scope globale dello stesso script
- Nessuna vera "delegation" (`addEventListener` su un contenitore che ispeziona `event.target`) è usata nel progetto: quando serve reagire a elementi creati dinamicamente si preferisce l'`onclick` inline

**Fetch verso le API:**
```javascript
async function performSearch() {
    const params = new URLSearchParams({ page: currentPage, search_type: searchType, ... });
    const response = await fetch(`/api/search?${params}`);
    const data = await response.json();
    if (data.error) { ... }
    renderResults(data);
}
```
(`src/templates/index.html:192-239`) — `try/catch` attorno al `fetch`, errore di rete mostrato con un messaggio generico ("Errore di connessione"), errore applicativo letto dal campo `data.error` della risposta JSON (coerente con `jsonify({'error': ...})` lato server)

**Costruzione dell'HTML:**
- Rendering via **template literal + `innerHTML`**, mai `document.createElement` per strutture complesse: `resultsDiv.innerHTML = html` dopo aver concatenato stringhe in un ciclo `for` (`src/templates/index.html:257-285`)
- **Escaping incoerente:** esiste una funzione `escapeHtml()` (`src/templates/index.html:425-430`, usa `textContent` per sfuggire e poi rimpiazza le virgolette) applicata a titolo e tooltip, ma **non** a tutti i campi interpolati (es. `section`, `quality`, `item.status` in `buildChips`/`renderResults` non passano da `escapeHtml`). Questo è tollerabile oggi perché quei campi arrivano dallo scraper e non da input utente diretto, ma è un pattern da correggere nella v2 se si vogliono evitare regressioni di XSS quando si aggiungono campi editabili
- Costanti di mapping dichiarate vicino alla funzione che le usa (`FLAG_MAP`, `AUDIO_CODECS`, `VIDEO_CODECS`, `LANG_CODES` in `src/templates/index.html:314-323`) invece che in un file dati condiviso

**Cosa significa per la UI v2:**
- Se si introducono più pagine con logica JS condivisa (es. `escapeHtml`, `buildPoster`, il fetch pattern), vale la pena estrarle in un file `src/static/app.js` condiviso con `<script src="...">` invece di duplicarle per-pagina come oggi — è l'unico modo per restare "zero build" ma evitare la duplicazione già presente fra le pagine

## Template Jinja

**Struttura:**
- **Nessuna ereditarietà**: zero `{% extends %}`, zero `{% block %}`, zero `{% include %}` in tutto `src/templates/`. Ogni file è un documento HTML autonomo e completo (`<!DOCTYPE html>` → `</html>`), che duplica head, nav, footer
- Navigazione (`<nav>` con i link a `/`, `/sections`, `/ratings`, `/admin`, `/logs`) ripetuta a mano in ogni pagina con markup quasi identico (confronta `src/templates/index.html:15-21` con l'equivalente in `admin.html`/`ratings.html`)

**Naming dei file:**
- `snake_case.html`, un file per route/pagina: `index.html` (ricerca), `sections.html` (elenco sezioni), `section_detail.html` (dettaglio sezione), `missing_data.html`, `ratings.html`, `admin.html`, `logs.html` — nome del file allineato al nome della funzione vista in `server.py` (es. `sections_page()` → `sections.html`)

**Uso di Jinja:**
- Solo costrutti base: `{% for %}`, `{{ variabile }}`, interpolazione diretta di variabili passate da `render_template(...)`; nessun filtro custom, nessuna macro (`{% macro %}`)
- Il rendering dinamico (liste di risultati, paginazione) è delegato interamente al JavaScript via fetch alle API JSON: Jinja si occupa solo dello scheletro statico della pagina (nav, form, contenitori vuoti `<div id="results">`) più poche liste piccole renderizzate lato server (es. opzioni `<select>` delle sezioni)

**Cosa significa per la UI v2:**
- Se la v2 rifà il frontend restando su Jinja "zero build", introdurre un `base.html` con `{% block %}` per head/nav/footer eliminerebbe la duplicazione di markup oggi presente in 7 file — è una decisione esplicita da prendere (mantenere l'idioma "pagina autonoma" oppure passare a ereditarietà), non qualcosa che va dedotto implicitamente

---

*Convention analysis: 2026-09-12*
