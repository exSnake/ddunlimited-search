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

# I log si leggono in Grafana: Alloy raccoglie lo stdout dei container in Loki.
# La sidebar ci porta con un collegamento esterno, l'app non li serve piu'.
GRAFANA_LOGS_URL = os.getenv(
    "GRAFANA_LOGS_URL",
    "http://grafana.lan/d/ddunlimited-search/ddunlimited-search"
)

# Post detail scraping
SCRAPE_POST_DETAILS = os.getenv("SCRAPE_POST_DETAILS", "true").lower() == "true"
POST_DETAIL_WORKERS = int(os.getenv("POST_DETAIL_WORKERS", "3"))
# A topic is revisited once, this many days after it was created: a title can
# still be edited in the first days, and never after that.
POST_RECHECK_DAYS = int(os.getenv("POST_RECHECK_DAYS", "30"))

# External ratings (TMDB for the match, OMDb for the IMDb vote)
RATINGS_ENABLED = os.getenv("RATINGS_ENABLED", "true").lower() == "true"
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_LANGUAGE = os.getenv("TMDB_LANGUAGE", "it-IT")
TMDB_REQUEST_DELAY = float(os.getenv("TMDB_REQUEST_DELAY", "0.05"))
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")
# The free OMDb plan allows 1000 calls a day, so the pass stops short of it.
OMDB_DAILY_LIMIT = int(os.getenv("OMDB_DAILY_LIMIT", "900"))
# Below this score the match is not trusted and lands in the review page.
RATING_MIN_CONFIDENCE = float(os.getenv("RATING_MIN_CONFIDENCE", "0.75"))
# Titles read from the database in one go while matching.
RATING_BATCH_SIZE = int(os.getenv("RATING_BATCH_SIZE", "500"))
# Ceiling for a single scheduled pass, so a long backlog does not hold up an
# import for hours. The rest is picked up by the next pass.
RATING_MAX_PER_RUN = int(os.getenv("RATING_MAX_PER_RUN", "5000"))
