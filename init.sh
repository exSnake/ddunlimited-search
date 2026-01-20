#!/bin/bash
# Script di inizializzazione per creare le directory necessarie

echo "Creazione directory necessarie..."
mkdir -p data logs

echo "Directory create:"
echo "  - data/ (per il database)"
echo "  - logs/ (per i log)"

if [ ! -f .env ]; then
    echo ""
    echo "ATTENZIONE: File .env non trovato!"
    echo "Copia env.example in .env e configura le tue credenziali:"
    echo "  cp env.example .env"
    echo "  nano .env"
fi

echo ""
echo "Per avviare i container Docker:"
echo "  docker-compose up -d"
echo ""
echo "Per visualizzare i log:"
echo "  docker-compose logs -f"
