"""Configuration module for DDUnlimited Search."""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Forum credentials
USERNAME = os.getenv("DDU_USERNAME", "")
PASSWORD = os.getenv("DDU_PASSWORD", "")

# Base URL
BASE_URL = "https://ddunlimited.net"
LOGIN_URL = f"{BASE_URL}/ucp.php?mode=login"

# Database
# Default: data/ddunlimited.db for local development, can be overridden via DATABASE_PATH env var
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/ddunlimited.db")

# Browser session relay
# Cookies captured from a logged-in browser, stored next to the database so
# both the web and scheduler containers can read them.
SESSION_FILE = os.getenv(
    "SESSION_FILE",
    os.path.join(os.path.dirname(DATABASE_PATH) or ".", "session.json")
)
# Shared secret the browser extension must send to push a session. Empty
# disables the endpoint.
SESSION_TOKEN = os.getenv("SESSION_TOKEN", "")

# Scraper settings
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.5"))  # seconds between requests
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))  # request timeout in seconds

# Flask settings
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"

# Pages file
PAGES_FILE = os.getenv("PAGES_FILE", "pages.txt")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Post detail scraping
SCRAPE_POST_DETAILS = os.getenv("SCRAPE_POST_DETAILS", "true").lower() == "true"
POST_DETAIL_WORKERS = int(os.getenv("POST_DETAIL_WORKERS", "3"))
