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

# Scheduler (solo per Docker)
SCRAPE_INTERVAL_DAYS=3
SCRAPE_HOUR=2
SCRAPE_MINUTE=0
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

#### Statistiche
```
GET /api/stats
```

#### Sezioni
```
GET /api/sections
```

## 📁 Struttura del Progetto

```
ddunlimited-search/
├── src/                    # Codice sorgente
│   ├── __init__.py
│   ├── config.py          # Configurazione
│   ├── database.py        # Gestione database
│   ├── parser.py          # Parser HTML
│   ├── scraper.py         # Scraper principale
│   ├── scheduler.py       # Scheduler per reimportazione
│   ├── server.py          # Server Flask
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
