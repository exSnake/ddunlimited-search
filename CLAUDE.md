# DDUnlimited Search

Ricerca sui titoli del forum DDUnlimited: 67.714 titoli in SQLite, arricchiti con
locandine e voti TMDB e con il voto IMDb via OMDb. Flask con template Jinja, **zero
build**: niente npm, niente framework frontend.

## Routing

- **Decisioni di design della UI v2** (direzione visiva, pattern CSS, tono e linguaggio)
  → `Skill("sketch-findings-ddunlimited-search")`

## Dove sta cosa

- `src/` — `server.py` (Flask), `scraper.py`, `parser.py`, `ratings.py` (abbinamento
  TMDB e voti IMDb), `scheduler.py`, `database.py`, `session_store.py`
- `.planning/sketches/` — i quattro sketch della UI v2, con varianti navigabili
- `.planning/spikes/` — valutazioni tecniche chiuse

## Produzione

Gira su **xhub** da `~/source/homelab-infra/hosts/xhub/ddunlimited-search`, due container
(web e scheduler) sulla stessa immagine. L'immagine si builda **su xhub** perché è x86_64
e il Mac è arm64; non passa da Docker Hub. Il riavvio dei container lo lancia l'utente.
