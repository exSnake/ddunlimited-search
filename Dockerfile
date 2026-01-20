FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data

# Make scripts executable
RUN chmod +x /app/run_scraper.sh /app/docker-entrypoint.sh

# Add src to PYTHONPATH
ENV PYTHONPATH=/app/src:${PYTHONPATH}

# Expose Flask port
EXPOSE 5000

# Set entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default command (can be overridden in docker-compose)
CMD ["python", "src/server.py"]
