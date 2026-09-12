# Testing Patterns

**Analysis Date:** 2026-09-12

## Framework

**Nessuno.** Non esiste alcuna suite di test automatizzata in questo repository.

Verificato con:
- Nessuna directory `tests/` né file `test_*.py` / `*_test.py` in tutto il progetto
- Nessun file `conftest.py`, `pytest.ini`, `tox.ini`, `pyproject.toml`
- `requirements.txt` contiene solo dipendenze runtime (`requests`, `beautifulsoup4`, `flask`, `python-dotenv`) — nessuna dipendenza di test (niente `pytest`, `unittest2`, `responses`, `freezegun`, `pytest-flask`, ecc.)
- Nessuna GitHub Action / pipeline CI nel repository che esegua test
- Il `README.md`, sezione "Testare il server" (`README.md:280-284`), descrive solo l'avvio manuale del server e la verifica a occhio nel browser:
```bash
python src/server.py
# Apri http://localhost:5000
```
  Non è una suite di test, è una nota su come far partire l'app in locale.

## Cosa significa in pratica

- **Non inventare un framework di test esistente.** Se un piano di lavoro richiede test, va deciso da zero: quale runner (`pytest` è la scelta naturale per un progetto Flask/sqlite3), come isolare il DB (es. `sqlite3.connect(':memory:')` o un file temporaneo al posto di `config.DATABASE_PATH`), come mockare le chiamate esterne (TMDB/OMDb in `src/ratings.py`, il forum in `src/scraper.py`) — nessuno di questi pattern esiste oggi da cui prendere esempio
- **Superficie che si presterebbe a test unitari senza troppa infrastruttura**, se mai introdotti:
  - `src/database.py:34-121` `extract_director_and_year` — funzione pura, solo stringa in ingresso e tupla in uscita, nessun I/O
  - `src/parser.py` — `extract_quality`, `extract_metadata`, `parse_page`, `parse_post_detail` lavorano su HTML statico passato come argomento, adatte a test basati su fixture HTML salvate su disco
  - `src/ratings.py` — `score_candidate`, `clean_title`, `title_variants`, `parse_tmdb_reference` sono funzioni pure di stringa/scoring
- **Superficie che richiederebbe mock o un DB di test:**
  - Tutto `database.py` dipende da `config.DATABASE_PATH` e da una connessione SQLite reale; oggi non c'è un modo per iniettare un path di test diverso se non sovrascrivere la variabile d'ambiente `DATABASE_PATH` prima dell'import di `config`
  - `scraper.py` e `ratings.py` fanno chiamate HTTP reali con `requests`; andrebbero mockate (`unittest.mock`/`responses`) per non dipendere dal forum o dalle API esterne durante i test
- **Frontend:** zero test anche lato JavaScript (nessun Jest/Vitest/Playwright configurato, coerente con la scelta "zero build" del progetto). La verifica del comportamento di `index.html`/`admin.html`/ecc. è oggi solo manuale nel browser

## Raccomandazione per la UI v2

Dato che non esiste alcuna base di test da estendere, qualunque nuova suite andrebbe introdotta come scelta esplicita e documentata (framework, comando di esecuzione, dove vivono i file), non assunta implicitamente. Finché non viene presa questa decisione, il collaudo resta manuale: avvio server locale + verifica visiva, come oggi.

---

*Testing analysis: 2026-09-12*
