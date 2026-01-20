# DDUnlimited Search - Docker Setup

## Prerequisiti

- Docker
- Docker Compose

## Pubblicazione su Docker Hub

### Immagine Multi-Arch (amd64 + arm64) - Consigliato

Per pubblicare un'immagine che funziona sia su x86_64 che su ARM64 (Raspberry Pi, Apple Silicon):

1. **Login su Docker Hub:**
   ```bash
   docker login
   ```

2. **Usa lo script per pubblicare:**
   ```bash
   ./push_to_dockerhub.sh
   ```

   Questo script:
   - Usa "exsnake" come username di default (puoi cambiarlo se necessario)
   - Crea automaticamente un builder multi-arch
   - Builda l'immagine per entrambe le architetture (amd64 + arm64)
   - Pubblica tutto su Docker Hub

3. **Aggiorna docker-compose.yml per usare l'immagine da Docker Hub:**
   ```yaml
   services:
     web:
       image: TUO_USERNAME/ddunlimited-search:latest
       # build: .  # commenta questa riga
   ```

**Nota:** L'immagine multi-arch funziona automaticamente su:
- Linux x86_64 (amd64)
- Linux ARM64 (Raspberry Pi 4+, Apple Silicon M1/M2)
- Docker selezionerà automaticamente l'architettura corretta

## Configurazione

1. Copia il file di esempio delle variabili d'ambiente:
   ```bash
   cp env.example .env
   ```

2. Modifica il file `.env` con le tue credenziali:
   ```env
   DDU_USERNAME=tuo_username
   DDU_PASSWORD=tua_password
   FLASK_PORT=5000
   SCRAPE_INTERVAL_DAYS=3
   SCRAPE_HOUR=2
   SCRAPE_MINUTE=0
   ```

### Variabili d'ambiente

- `DDU_USERNAME`: Username per il forum DDUnlimited
- `DDU_PASSWORD`: Password per il forum DDUnlimited
- `FLASK_PORT`: Porta per il server web (default: 5000)
- `SCRAPE_INTERVAL_DAYS`: Giorni di attesa tra le importazioni (default: 3)
- `SCRAPE_HOUR`: Ora del giorno per eseguire l'importazione (formato 24h, default: 2 = 2:00 AM)
- `SCRAPE_MINUTE`: Minuto dell'ora per eseguire l'importazione (default: 0)

## Avvio

1. Crea le directory necessarie:
   ```bash
   mkdir -p data logs
   ```

2. Verifica che pages.txt esista
Assicurati che il file `pages.txt` esista nella directory principale. Questo file contiene l'elenco delle pagine da scaricare.

3. Avvia i container:
   ```bash
   docker-compose up -d
   ```

   Se usi l'immagine da Docker Hub, scaricala prima:
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

4. Visualizza i log:
   ```bash
   # Log del server web
   docker-compose logs -f web
   
   # Log dello scheduler
   docker-compose logs -f scheduler
   ```

## Utilizzo

- **Server Web**: Accessibile su `http://localhost:5000` (o la porta configurata)
- **Scheduler**: Esegue automaticamente l'importazione ogni N giorni all'ora configurata

### Note per Raspberry Pi (ARM64)

Se stai usando un Raspberry Pi o un sistema ARM64:

- **Con immagine multi-arch**: Se l'immagine è stata pubblicata con `push_to_dockerhub.sh`, funzionerà automaticamente. Docker selezionerà automaticamente la versione ARM64.
- **Build locale**: Se l'immagine su Docker Hub è solo per amd64, il `docker-compose.yml` è configurato per buildare localmente, quindi funzionerà automaticamente. La prima volta potrebbe richiedere alcuni minuti per buildare l'immagine.

Per verificare l'architettura del tuo sistema:
```bash
uname -m
# Output: aarch64 (ARM64) o x86_64 (amd64)
```

## Comandi utili

```bash
# Fermare i container
docker-compose down

# Riavviare i container
docker-compose restart

# Eseguire manualmente lo scraper
docker-compose exec scheduler python src/scraper.py

# Visualizzare lo stato dell'ultima importazione
docker-compose exec web python -c "import sys; sys.path.insert(0, '/app/src'); import database; print(database.get_last_import())"
```

## Struttura dei dati

I dati vengono salvati nella directory `./data`:
- `ddunlimited.db`: Database SQLite con tutti i titoli

I log vengono salvati nella directory `./logs`:
- `scraper.log`: Log dello scraper
- `scheduler.log`: Log dello scheduler

## Note

- Il database viene condiviso tra i container web e scheduler
- Lo scheduler controlla automaticamente se è necessario eseguire un'importazione basandosi sull'ultima importazione completata
- Se l'ultima importazione non è completata, lo scheduler eseguirà immediatamente una nuova importazione
- L'importazione viene eseguita solo se sono passati almeno `SCRAPE_INTERVAL_DAYS` giorni dall'ultima importazione completata
