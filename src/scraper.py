"""Main scraper module for DDUnlimited Search."""

import logging
import sys
import time

import requests

import config
import database
import parser

# Create logs directory if it doesn't exist
import os
os.makedirs('logs', exist_ok=True)

# Configure logging for scraper only
# Don't use basicConfig to avoid interfering with other loggers
scraper_logger = logging.getLogger('scraper')
scraper_logger.setLevel(logging.INFO)
scraper_logger.handlers.clear()  # Remove any existing handlers

# File handler for scraper logs
scraper_file_handler = logging.FileHandler('logs/scraper.log', encoding='utf-8')
scraper_file_handler.setLevel(logging.INFO)
scraper_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Console handler (optional)
scraper_console_handler = logging.StreamHandler(sys.stdout)
scraper_console_handler.setLevel(logging.INFO)
scraper_console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

scraper_logger.addHandler(scraper_file_handler)
scraper_logger.addHandler(scraper_console_handler)
scraper_logger.propagate = False  # Don't propagate to root logger

logger = scraper_logger


class DDUnlimitedScraper:
    """Scraper for DDUnlimited forum."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.logged_in = False

    def login(self) -> bool:
        """
        Login to the forum.

        Returns:
            True if login successful, False otherwise
        """
        if not config.USERNAME or not config.PASSWORD:
            logger.error("Username or password not configured. Check .env file.")
            return False

        logger.info(f"Attempting login as {config.USERNAME}...")

        try:
            # First, get the login page to extract any tokens
            login_page = self.session.get(
                config.LOGIN_URL,
                timeout=config.REQUEST_TIMEOUT
            )
            login_page.raise_for_status()

            # Prepare login data
            login_data = {
                'username': config.USERNAME,
                'password': config.PASSWORD,
                'login': 'Login',
                'redirect': './index.php',
            }

            # Perform login
            response = self.session.post(
                config.LOGIN_URL,
                data=login_data,
                timeout=config.REQUEST_TIMEOUT,
                allow_redirects=True
            )
            response.raise_for_status()

            # Check if login was successful
            # phpBB typically redirects and sets cookies on successful login
            if 'logout' in response.text.lower() or 'sid=' in response.url:
                logger.info("Login successful!")
                self.logged_in = True
                return True
            elif 'login' in response.url.lower() and 'error' in response.text.lower():
                logger.error("Login failed: Invalid credentials")
                return False
            else:
                # Check for session cookie
                if any('phpbb' in cookie.name.lower() for cookie in self.session.cookies):
                    logger.info("Login appears successful (session cookie found)")
                    self.logged_in = True
                    return True

                logger.warning("Login status uncertain, proceeding anyway...")
                self.logged_in = True
                return True

        except requests.RequestException as e:
            logger.error(f"Login request failed: {e}")
            return False

    def fetch_page(self, url: str) -> str | None:
        """
        Fetch a page content.

        Args:
            url: The URL to fetch

        Returns:
            HTML content or None on error
        """
        try:
            response = self.session.get(
                url,
                timeout=config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def scrape_page(self, url: str, section: str, max_retries: int = 3, status_callback=None) -> tuple[int, int, int]:
        """
        Scrape a single page and save titles to database.

        Args:
            url: The page URL
            section: The section name
            max_retries: Maximum number of retry attempts (default: 3)
            status_callback: Optional callback function(status_message) to update status

        Returns:
            Tuple of (titles_found, inserted, updated)
        """
        def update_status(msg):
            if status_callback:
                status_callback(msg)
            logger.info(msg)
        
        logger.info(f"Scraping page: {section} - {url} (max retries: {max_retries})")
        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                update_status(f"Tentativo {attempt}/{max_retries}...")
            logger.debug(f"Attempt {attempt}/{max_retries} for {url}")
            html = self.fetch_page(url)
            if html:
                update_status("Parsing della pagina in corso...")
                titles = parser.parse_page(html, section)
                update_status(f"Trovati {len(titles)} titoli, inserimento in corso...")
                logger.info(f"Found {len(titles)} titles on page")

                inserted = 0
                updated = 0
                total = len(titles)
                for idx, title_data in enumerate(titles, 1):
                    is_new = database.insert_title(
                        title=title_data['title'],
                        url=title_data['url'],
                        section=title_data['section'],
                        metadata=title_data.get('metadata'),
                        quality=title_data.get('quality')
                    )
                    if is_new:
                        inserted += 1
                    else:
                        updated += 1
                    
                    # Update status every 10 titles or at the end
                    if idx % 10 == 0 or idx == total:
                        update_status(f"Inserimento: {idx}/{total} titoli processati ({inserted} nuovi, {updated} aggiornati)...")

                logger.info(f"Inserted {inserted} new titles, updated {updated}")
                return (len(titles), inserted, updated)
            else:
                if attempt < max_retries:
                    # Exponential backoff: 1s, 2s, 4s...
                    wait_time = 2 ** (attempt - 1)
                    update_status(f"Errore nel download (tentativo {attempt}/{max_retries}), nuovo tentativo tra {wait_time}s...")
                    logger.warning(f"Failed to fetch {url} (attempt {attempt}/{max_retries}). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    error_msg = f"Errore: impossibile scaricare la pagina dopo {max_retries} tentativi"
                    update_status(error_msg)
                    logger.error(f"Failed to fetch {url} after {max_retries} attempts. Skipping.")
        
        return (0, 0, 0)

    def scrape_single_page(self, url: str, section: str, status_callback=None) -> tuple[int, int, int]:
        """
        Scrape a single page (for manual import).
        This method handles login if needed and scrapes just one page.

        Args:
            url: The page URL
            section: The section name
            status_callback: Optional callback function(status_message) to update status

        Returns:
            Tuple of (titles_found, inserted, updated)
        """
        def update_status(msg):
            if status_callback:
                status_callback(msg)
            logger.info(msg)
        
        update_status(f"Starting single page import: {section} - {url}")
        
        # Initialize database
        update_status("Inizializzazione database...")
        database.init_db()
        logger.info("Database initialized for single page import")
        
        # Ensure we're logged in
        if not self.logged_in:
            update_status("Accesso in corso...")
            logger.info("Not logged in, attempting login...")
            if not self.login():
                error_msg = "Errore: accesso fallito"
                update_status(error_msg)
                logger.error("Failed to login. Cannot scrape page.")
                return (0, 0, 0)
            update_status("Accesso completato")
        else:
            logger.info("Already logged in, proceeding with scrape")
        
        update_status("Scaricamento pagina in corso...")
        logger.info(f"Scraping page: {url}")
        result = self.scrape_page(url, section, status_callback=status_callback)
        message = f'Completato: {result[0]} titoli trovati, {result[1]} inseriti, {result[2]} aggiornati'
        update_status(message)
        logger.info(f"Single page import completed: {result[0]} titles found, {result[1]} inserted, {result[2]} updated")
        return result

    def run(self, status_callback=None):
        """
        Run the scraper.
        
        Args:
            status_callback: Optional callback function(status_message) to update status
        """
        def update_status(msg):
            if status_callback:
                status_callback(msg)
            logger.info(msg)
        
        update_status("Avvio scraper...")
        logger.info("Starting DDUnlimited scraper...")

        # Initialize database
        update_status("Inizializzazione database...")
        database.init_db()
        logger.info("Database initialized")

        # Start import tracking
        import_id = database.start_import()
        logger.info(f"Import session started (ID: {import_id})")

        try:
            # Login
            update_status("Accesso in corso...")
            if not self.login():
                error_msg = "Errore: accesso fallito"
                update_status(error_msg)
                logger.error("Failed to login. Exiting.")
                database.complete_import(import_id, 0, 0, 0, success=False)
                return
            update_status("Accesso completato")

            # Load pages from file
            update_status("Caricamento pagine da pages.txt...")
            pages = parser.parse_pages_file(config.PAGES_FILE)
            if not pages:
                error_msg = f"Errore: nessuna pagina trovata in {config.PAGES_FILE}"
                update_status(error_msg)
                logger.error(f"No pages to scrape. Check {config.PAGES_FILE}")
                database.complete_import(import_id, 0, 0, 0, success=False)
                return

            update_status(f"Caricate {len(pages)} pagine da importare")
            logger.info(f"Loaded {len(pages)} pages to scrape")

            # Scrape each page
            total_titles = 0
            total_inserted = 0
            total_updated = 0
            for i, page_info in enumerate(pages, 1):
                section = page_info['section']
                url = page_info['url']

                update_status(f"[{i}/{len(pages)}] Importazione: {section}...")
                logger.info(f"[{i}/{len(pages)}] Scraping: {section} - {url}")

                found, inserted, updated = self.scrape_page(url, section, status_callback=status_callback)
                total_titles += found
                total_inserted += inserted
                total_updated += updated

                # Rate limiting
                if i < len(pages):
                    logger.info(f"Waiting {config.REQUEST_DELAY}s before next request...")
                    time.sleep(config.REQUEST_DELAY)

            # Complete import tracking
            database.complete_import(import_id, total_titles, total_inserted, total_updated, success=True)

            # Final stats
            stats = database.get_stats()
            final_msg = f"Importazione completata: {total_titles} titoli trovati, {total_inserted} inseriti, {total_updated} aggiornati"
            update_status(final_msg)
            logger.info(f"Scraping complete!")
            logger.info(f"Total titles found: {total_titles}")
            logger.info(f"New titles inserted: {total_inserted}")
            logger.info(f"Titles updated: {total_updated}")
            logger.info(f"Total titles in database: {stats['total_titles']}")
            logger.info(f"Total sections: {stats['total_sections']}")
        except Exception as e:
            error_msg = f"Errore durante l'importazione: {str(e)}"
            update_status(error_msg)
            logger.error(f"Error during scraping: {e}", exc_info=True)
            database.complete_import(import_id, 0, 0, 0, success=False)
            raise


def main():
    """Main entry point."""
    scraper = DDUnlimitedScraper()
    scraper.run()


if __name__ == "__main__":
    main()
