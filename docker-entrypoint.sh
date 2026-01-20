#!/bin/bash
# Docker entrypoint script with file verification

set -e

echo "=== DDUnlimited Search - Container Startup ==="
echo ""

# Show current directory
echo "Working directory: $(pwd)"
echo ""

# Check and list application files
echo "=== Checking application structure ==="
if [ -d "/app/src" ]; then
    echo "✓ /app/src directory exists"
    echo ""
    echo "Contents of /app/src:"
    ls -lah /app/src/ | head -20
    echo ""
    
    # Check for key files
    echo "=== Checking key files ==="
    [ -f "/app/src/server.py" ] && echo "✓ server.py found" || echo "✗ server.py NOT FOUND"
    [ -f "/app/src/scheduler.py" ] && echo "✓ scheduler.py found" || echo "✗ scheduler.py NOT FOUND"
    [ -f "/app/src/scraper.py" ] && echo "✓ scraper.py found" || echo "✗ scraper.py NOT FOUND"
    [ -f "/app/src/database.py" ] && echo "✓ database.py found" || echo "✗ database.py NOT FOUND"
    [ -f "/app/src/config.py" ] && echo "✓ config.py found" || echo "✗ config.py NOT FOUND"
    [ -d "/app/src/templates" ] && echo "✓ templates/ directory found" || echo "✗ templates/ NOT FOUND"
    [ -d "/app/src/static" ] && echo "✓ static/ directory found" || echo "✗ static/ NOT FOUND"
else
    echo "✗ /app/src directory NOT FOUND"
    echo ""
    echo "Contents of /app:"
    ls -lah /app/ | head -20
fi

echo ""
echo "=== Checking data and logs directories ==="
[ -d "/app/data" ] && echo "✓ /app/data directory exists" || echo "✗ /app/data NOT FOUND"
[ -d "/app/logs" ] && echo "✓ /app/logs directory exists" || echo "✗ /app/logs NOT FOUND"
echo ""

echo "=== Environment variables ==="
echo "PYTHONPATH: ${PYTHONPATH:-not set}"
echo "DATABASE_PATH: ${DATABASE_PATH:-not set}"
echo "PAGES_FILE: ${PAGES_FILE:-not set}"
echo ""

echo "=== Starting application ==="
echo "Command: $@"
echo ""

# Execute the command passed as arguments
exec "$@"
