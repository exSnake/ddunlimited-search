#!/bin/bash
# Script per pubblicare l'immagine Docker multi-arch (amd64 + arm64) su Docker Hub
# Username di default: exsnake
# Gestisce versionamento automatico e pubblica sia su latest che sulla versione

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# File di versionamento
VERSION_FILE="VERSION"

# Funzione per leggere la versione corrente
get_current_version() {
    if [ -f "$VERSION_FILE" ]; then
        cat "$VERSION_FILE" | tr -d '[:space:]'
    else
        echo "1.0.0"
    fi
}

# Funzione per incrementare la versione
increment_version() {
    local version=$1
    local bump_type=$2
    
    IFS='.' read -ra VERSION_PARTS <<< "$version"
    local major=${VERSION_PARTS[0]}
    local minor=${VERSION_PARTS[1]}
    local patch=${VERSION_PARTS[2]}
    
    case $bump_type in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            echo -e "${RED}Errore: tipo di bump non valido: $bump_type${NC}"
            exit 1
            ;;
    esac
    
    echo "${major}.${minor}.${patch}"
}

# Funzione per validare il formato della versione
validate_version() {
    local version=$1
    if [[ ! $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo -e "${RED}Errore: formato versione non valido: $version${NC}"
        echo "Il formato deve essere: MAJOR.MINOR.PATCH (es. 1.2.3)"
        exit 1
    fi
}

echo -e "${GREEN}=== Pubblicazione Multi-Arch su Docker Hub ===${NC}"
echo ""

# Gestione versionamento
CURRENT_VERSION=$(get_current_version)
validate_version "$CURRENT_VERSION"

# Calcola le versioni future per il menu
PATCH_VERSION=$(increment_version "$CURRENT_VERSION" "patch")
MINOR_VERSION=$(increment_version "$CURRENT_VERSION" "minor")
MAJOR_VERSION=$(increment_version "$CURRENT_VERSION" "major")

echo -e "${BLUE}Versione corrente: ${CURRENT_VERSION}${NC}"
echo ""
echo "Seleziona il tipo di incremento versione:"
echo "  1) Patch (${CURRENT_VERSION} -> ${PATCH_VERSION}) - Bug fixes, piccole correzioni"
echo "  2) Minor (${CURRENT_VERSION} -> ${MINOR_VERSION}) - Nuove funzionalità, backward compatible"
echo "  3) Major (${CURRENT_VERSION} -> ${MAJOR_VERSION}) - Breaking changes, modifiche incompatibili"
echo "  4) Nessun incremento (usa la versione corrente: ${CURRENT_VERSION})"
echo ""
read -p "Scelta (1-4, default: 1): " VERSION_CHOICE
VERSION_CHOICE=${VERSION_CHOICE:-1}

case $VERSION_CHOICE in
    1)
        BUMP_TYPE="patch"
        NEW_VERSION=$(increment_version "$CURRENT_VERSION" "patch")
        ;;
    2)
        BUMP_TYPE="minor"
        NEW_VERSION=$(increment_version "$CURRENT_VERSION" "minor")
        ;;
    3)
        BUMP_TYPE="major"
        NEW_VERSION=$(increment_version "$CURRENT_VERSION" "major")
        ;;
    4)
        NEW_VERSION="$CURRENT_VERSION"
        echo -e "${YELLOW}Usando la versione corrente senza incremento${NC}"
        ;;
    *)
        echo -e "${RED}Scelta non valida${NC}"
        exit 1
        ;;
esac

if [ "$NEW_VERSION" != "$CURRENT_VERSION" ]; then
    echo -e "${GREEN}Nuova versione: ${CURRENT_VERSION} -> ${NEW_VERSION}${NC}"
    echo "$NEW_VERSION" > "$VERSION_FILE"
    echo -e "${GREEN}Versione aggiornata in ${VERSION_FILE}${NC}"
else
    echo -e "${YELLOW}Versione rimane: ${CURRENT_VERSION}${NC}"
fi

VERSION_TAG="$NEW_VERSION"
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

# Nome completo dell'immagine (saranno pubblicate due versioni: latest e versione)
IMAGE_NAME_LATEST="${DOCKER_USERNAME}/${REPO_NAME}:latest"
IMAGE_NAME_VERSION="${DOCKER_USERNAME}/${REPO_NAME}:${VERSION_TAG}"

echo ""
echo -e "${YELLOW}Configurazione:${NC}"
echo "  Username: $DOCKER_USERNAME"
echo "  Repository: $REPO_NAME"
echo "  Tag latest: latest"
echo "  Tag versione: ${VERSION_TAG}"
echo "  Immagine latest: $IMAGE_NAME_LATEST"
echo "  Immagine versione: $IMAGE_NAME_VERSION"
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
    docker buildx create --name "$BUILDER_NAME" --driver docker-container --use
else
    echo "Uso il builder esistente..."
    docker buildx use "$BUILDER_NAME" 2>/dev/null || {
        echo "Il builder esiste ma non è utilizzabile, lo ricreo..."
        docker buildx rm "$BUILDER_NAME" 2>/dev/null || true
        docker buildx create --name "$BUILDER_NAME" --driver docker-container --use
    }
fi

# Inizializza il builder
echo "Inizializzazione builder..."
docker buildx inspect --bootstrap

echo ""
echo -e "${GREEN}2. Buildo e pubblico l'immagine multi-arch...${NC}"
echo -e "${YELLOW}Questo processo può richiedere diversi minuti...${NC}"

# Builda e pubblica per entrambe le architetture con due tag (latest e versione)
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag "$IMAGE_NAME_LATEST" \
    --tag "$IMAGE_NAME_VERSION" \
    --push \
    .

echo ""
echo -e "${GREEN}✓ Immagine multi-arch pubblicata con successo!${NC}"
echo ""
echo "Le immagini sono disponibili su:"
echo "  https://hub.docker.com/r/${DOCKER_USERNAME}/${REPO_NAME}"
echo ""
echo "Tag pubblicati:"
echo "  - ${IMAGE_NAME_LATEST} (latest)"
echo "  - ${IMAGE_NAME_VERSION} (versione ${VERSION_TAG})"
echo ""
echo "Architetture supportate:"
echo "  - linux/amd64 (x86_64)"
echo "  - linux/arm64 (ARM64, Raspberry Pi 4+, Apple Silicon)"
echo ""
echo "Per usarla, aggiorna il docker-compose.yml con:"
echo "  image: ${IMAGE_NAME_LATEST}"
echo "  # oppure per una versione specifica:"
echo "  image: ${IMAGE_NAME_VERSION}"
echo "  # rimuovi o commenta la riga 'build: .'"
