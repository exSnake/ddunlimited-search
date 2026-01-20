#!/bin/bash
# Script per pubblicare l'immagine Docker multi-arch (amd64 + arm64) su Docker Hub
# Username di default: exsnake

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Pubblicazione Multi-Arch su Docker Hub ===${NC}"
echo ""

# Controlla se buildx è disponibile
if ! docker buildx version >/dev/null 2>&1; then
    echo -e "${RED}Errore: docker buildx non è disponibile${NC}"
    echo "Installa Docker Buildx o aggiorna Docker alla versione più recente"
    exit 1
fi

# Controlla se l'utente è loggato
if ! docker info 2>/dev/null | grep -q "Username" && [ ! -f ~/.docker/config.json ]; then
    echo -e "${YELLOW}ATTENZIONE: Non sei loggato su Docker Hub${NC}"
    echo "Esegui: docker login"
    echo ""
    read -p "Vuoi fare login ora? (s/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        docker login
        echo ""
    else
        echo -e "${RED}Login richiesto per continuare${NC}"
        exit 1
    fi
fi

# Chiedi il nome utente Docker Hub (default: exsnake)
read -p "Inserisci il tuo username Docker Hub (default: exsnake): " DOCKER_USERNAME
DOCKER_USERNAME=${DOCKER_USERNAME:-exsnake}

# Rimuovi spazi e caratteri speciali
DOCKER_USERNAME=$(echo "$DOCKER_USERNAME" | tr -d '[:space:]')

# Docker Hub richiede username in minuscolo
DOCKER_USERNAME=$(echo "$DOCKER_USERNAME" | tr '[:upper:]' '[:lower:]')
echo -e "${GREEN}Username: $DOCKER_USERNAME${NC}"

# Chiedi il nome del repository (default: ddunlimited-search)
read -p "Inserisci il nome del repository (default: ddunlimited-search): " REPO_NAME
REPO_NAME=${REPO_NAME:-ddunlimited-search}

# Chiedi il tag (default: latest)
read -p "Inserisci il tag (default: latest): " TAG
TAG=${TAG:-latest}

# Nome completo dell'immagine
IMAGE_NAME="${DOCKER_USERNAME}/${REPO_NAME}:${TAG}"

echo ""
echo -e "${YELLOW}Configurazione:${NC}"
echo "  Username: $DOCKER_USERNAME"
echo "  Repository: $REPO_NAME"
echo "  Tag: $TAG"
echo "  Immagine completa: $IMAGE_NAME"
echo "  Architetture: linux/amd64, linux/arm64"
echo ""

read -p "Confermi la pubblicazione? (s/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo -e "${YELLOW}Operazione annullata${NC}"
    exit 0
fi

echo ""
echo -e "${GREEN}1. Creo/uso il builder multi-arch...${NC}"

# Crea un builder multi-arch se non esiste
BUILDER_NAME="multiarch-builder"
if ! docker buildx ls | grep -q "$BUILDER_NAME"; then
    echo "Creo il builder multi-arch..."
    docker buildx create --name "$BUILDER_NAME" --use --bootstrap
else
    echo "Uso il builder esistente..."
    docker buildx use "$BUILDER_NAME"
fi

# Inizializza il builder
docker buildx inspect --bootstrap

echo ""
echo -e "${GREEN}2. Buildo e pubblico l'immagine multi-arch...${NC}"
echo -e "${YELLOW}Questo processo può richiedere diversi minuti...${NC}"

# Builda e pubblica per entrambe le architetture
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag "$IMAGE_NAME" \
    --push \
    .

echo ""
echo -e "${GREEN}✓ Immagine multi-arch pubblicata con successo!${NC}"
echo ""
echo "L'immagine è disponibile su:"
echo "  https://hub.docker.com/r/${DOCKER_USERNAME}/${REPO_NAME}"
echo ""
echo "Architetture supportate:"
echo "  - linux/amd64 (x86_64)"
echo "  - linux/arm64 (ARM64, Raspberry Pi 4+, Apple Silicon)"
echo ""
echo "Per usarla, aggiorna il docker-compose.yml con:"
echo "  image: ${IMAGE_NAME}"
echo "  # rimuovi o commenta la riga 'build: .'"
