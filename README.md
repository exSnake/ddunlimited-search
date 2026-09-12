# DDUnlimited Search

Un sistema di ricerca e scraping per il forum DDUnlimited, che permette di cercare tra i titoli delle discussioni con diverse modalità di ricerca avanzate.

## 🚀 Funzionalità

- **Ricerca avanzata** con 4 modalità:
  - **Contiene**: ricerca classica (contiene la query)
  - **Inizia con**: trova titoli che iniziano con la query
  - **Finisce con**: trova titoli che finiscono con la query
  - **Contiene tutte le parole**: trova titoli che contengono tutte le parole (in qualsiasi ordine)

- **Filtro per sezione**: cerca in una sezione specifica o in tutte le sezioni

- **Interfaccia web moderna**: UI responsive e intuitiva

- **Voti esterni**: locandina e voto IMDb (o TMDB) accanto a ogni risultato, con filtro
  per voto minimo e ordinamento per voto

- **Reimportazione automatica**: scheduler configurabile per aggiornare i dati periodicamente

- **Docker ready**: deploy facile con Docker e Docker Compose

## 📋 Requisiti

- Python 3.11+
- Docker e Docker Compose (per deploy containerizzato)
- Credenziali per il forum DDUnlimited

## 🛠️ Installazione

### Opzione 1: Docker (Consigliato)

Vedi [README_DOCKER.md](README_DOCKER.md) per le istruzioni complete.

**Quick start:**
```bash
# Clona il repository
git clone https://github.com/exSnake/ddunlimited-search.git
cd ddunlimited-search

# Configura le variabili d'ambiente
cp .env.example .env
# Modifica .env con le tue credenziali

# Crea le directory necessarie
./init.sh

# Avvia i container
docker-compose up -d
```

L'applicazione sarà disponibile su `http://localhost:5000`

### Opzione 2: Installazione locale

1. **Clona il repository:**
   ```bash
   git clone https://github.com/exSnake/ddunlimited-search.git
   cd ddunlimited-search
   ```

2. **Crea un ambiente virtuale:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Su Windows: venv\Scripts\activate
   ```

3. **Installa le dipendenze:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configura le variabili d'ambiente:**
   ```bash
   cp .env.example .env
   # Modifica .env con le tue credenziali DDUnlimited
   ```

5. **Crea le directory necessarie:**
   ```bash
   mkdir -p data logs
   ```

6. **Esegui lo scraper per popolare il database:**
   ```bash
   python src/scraper.py
   ```

7. **Avvia il server web:**
   ```bash
   python src/server.py
   ```

## ⚙️ Configurazione

### Variabili d'ambiente (.env)

```env
# Credenziali DDUnlimited
DDU_USERNAME=tuo_username
DDU_PASSWORD=tua_password

# Database
DATABASE_PATH=data/ddunlimited.db

# Scraper
REQUEST_DELAY=1.5
REQUEST_TIMEOUT=30
PAGES_FILE=pages.txt

# Flask
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
FLASK_DEBUG=False

# Relay della sessione browser
SESSION_TOKEN=un_segreto_a_caso

# Scheduler (valori di default, la pagina Amministrazione ha la precedenza)
SCRAPE_ENABLED=true
SCRAPE_INTERVAL_DAYS=3
SCRAPE_HOUR=2
SCRAPE_MINUTE=0

# Voti esterni
RATINGS_ENABLED=true
TMDB_API_KEY=la_tua_chiave_tmdb
OMDB_API_KEY=la_tua_chiave_omdb
```

### Sessione browser

Il login del forum e' dietro un challenge Cloudflare, quindi lo scraper non puo'
autenticarsi da solo: riusa i cookie di un browser gia' collegato.

L'estensione [EDD2k](https://github.com/exSnake/edd2k) li invia con il suo
*session relay*: nelle impostazioni del popup vanno indicati il dominio
(`ddunlimited.net`), l'endpoint (`http://<host>/api/session`) e lo stesso valore
di `SESSION_TOKEN`. Da li' in poi i cookie si rinnovano da soli ogni volta che
navighi il forum.

I cookie ricevuti vengono provati su una pagina reale prima di essere salvati,
quindi una sessione da ospite non puo' sovrascriverne una valida. Lo stato si
vede nella pagina Amministrazione.

### Voti IMDb e TMDB

I titoli del forum vengono abbinati alle schede di [TMDB](https://www.themoviedb.org),
che restituisce anche l'id IMDb; il voto IMDb vero e proprio arriva poi da
[OMDb](https://www.omdbapi.com). Servono due chiavi, entrambe gratuite:

- **TMDB**: `TMDB_API_KEY`, da https://www.themoviedb.org/settings/api. Senza questa
  chiave non viene fatto alcun abbinamento.
- **OMDb**: `OMDB_API_KEY`, da https://www.omdbapi.com/apikey.aspx. E' facoltativa:
  senza, la UI mostra il voto TMDB. Il piano gratuito consente 1000 chiamate al
  giorno, quindi i voti IMDb si popolano un po' per volta (`OMDB_DAILY_LIMIT`).

L'abbinamento parte dal titolo ripulito (via le parentesi, i suffissi tipo
`- Stagione 1` o `- FilmTV`, gli apostrofi al posto degli accenti) e viene pesato
con anno e regista gia' estratti dal titolo. Sotto `RATING_MIN_CONFIDENCE` il
risultato non viene dato per buono e finisce nella pagina **Voti**, dove si puo'
correggerlo incollando la URL TMDB giusta, scartarlo o rimetterlo in coda.

Lo scheduler ripassa ogni 6 ore e dopo ogni import. Per farlo girare a mano:

```bash
python src/ratings.py                    # solo i titoli mai cercati
python src/ratings.py --retry-unmatched  # riprova anche quelli senza match
```

### File pages.txt

Il file `pages.txt` contiene l'elenco delle pagine da scaricare. Formato:
```
Sezione 1|https://ddunlimited.net/viewforum.php?f=123
Sezione 2|https://ddunlimited.net/viewforum.php?f=456
```

## 📖 Utilizzo

### Interfaccia Web

1. Apri il browser su `http://localhost:5000`
2. Inserisci la query di ricerca
3. Seleziona il tipo di ricerca (Contiene, Inizia con, ecc.)
4. Opzionalmente filtra per sezione
5. Clicca su "Cerca"

### API

#### Ricerca
```
GET /api/search?q=query&search_type=contains&section=&page=1
```

Parametri:
- `q` (richiesto): Query di ricerca
- `search_type` (opzionale): `contains`, `starts_with`, `ends_with`, `all_words` (default: `contains`)
- `section` (opzionale): Nome della sezione
- `page` (opzionale): Numero di pagina (default: 1)
- `per_page` (opzionale): Risultati per pagina (default: 50, max: 100)
- `min_rating` (opzionale): Voto minimo, da 0 a 10
- `sort` (opzionale): `title` (default), `rating`, `year`, `year_asc`

#### Statistiche
```
GET /api/stats
```

#### Sezioni
```
GET /api/sections
```

#### Voti
```
GET  /api/ratings/status               # configurazione, avanzamento e conteggi
POST /api/ratings/enrich               # avvia una passata di abbinamento
GET  /api/ratings/review?status=...    # abbinamenti da rivedere
POST /api/ratings/match                # {title_id, reference} aggancia a una scheda TMDB
POST /api/ratings/reject               # {title_id} scarta l'abbinamento
POST /api/ratings/reset                # {title_id} rimette il titolo in coda
```

## 📁 Struttura del Progetto

```
ddunlimited-search/
├── src/                    # Codice sorgente
│   ├── __init__.py
│   ├── config.py          # Configurazione
│   ├── database.py        # Gestione database
│   ├── parser.py          # Parser HTML
│   ├── ratings.py         # Abbinamento a TMDB e voti IMDb
│   ├── scraper.py         # Scraper principale
│   ├── scheduler.py       # Scheduler per reimportazione
│   ├── server.py          # Server Flask
│   ├── session_store.py   # Cookie di sessione inviati dal browser
│   ├── static/            # File statici (CSS, JS)
│   └── templates/         # Template HTML
├── data/                  # Database (non committato)
├── logs/                  # Log (non committato)
├── docker-compose.yml     # Configurazione Docker Compose
├── Dockerfile             # Immagine Docker
├── docker-entrypoint.sh   # Entrypoint per debug
├── pages.txt             # Elenco pagine da scaricare
├── requirements.txt      # Dipendenze Python
└── README.md            # Questo file
```

## 🐳 Docker

Per informazioni dettagliate sul deploy Docker, vedi [README_DOCKER.md](README_DOCKER.md).

### Immagine Docker Hub

L'immagine è disponibile su Docker Hub:
```
exsnake/ddunlimited-search:latest
```

Supporta architetture:
- `linux/amd64` (x86_64)
- `linux/arm64` (Raspberry Pi 4+, Apple Silicon)

## 🔧 Sviluppo

### Eseguire lo scraper manualmente

```bash
python src/scraper.py
```

### Eseguire lo scheduler manualmente

```bash
python src/scheduler.py
```

### Testare il server

```bash
python src/server.py
# Apri http://localhost:5000
```

## 📝 Note

- Il database viene creato automaticamente alla prima esecuzione
- I log vengono salvati in `logs/`
- Il database è in SQLite, salvato in `data/ddunlimited.db`
- Lo scheduler (solo in Docker) esegue automaticamente le reimportazioni

## 🤝 Contribuire

1. Fai un fork del progetto
2. Crea un branch per la tua feature (`git checkout -b feature/AmazingFeature`)
3. Committa le modifiche (`git commit -m 'Add some AmazingFeature'`)
4. Pusha sul branch (`git push origin feature/AmazingFeature`)
5. Apri una Pull Request

## 📄 Licenza

Questo progetto è per uso personale.

## 🔗 Link

- Repository: https://github.com/exSnake/ddunlimited-search
- Docker Hub: https://hub.docker.com/r/exsnake/ddunlimited-search

## 👤 Autore

exSnake

---

**Nota**: Questo progetto è solo per uso personale e non è affiliato con DDUnlimited.
