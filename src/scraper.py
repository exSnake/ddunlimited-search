"""Main scraper module for DDUnlimited Search."""

import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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
_log_level = getattr(logging, config.LOG_LEVEL, logging.INFO)
scraper_logger.setLevel(_log_level)
scraper_logger.handlers.clear()  # Remove any existing handlers

# File handler for scraper logs
scraper_file_handler = logging.FileHandler('logs/scraper.log', encoding='utf-8')
scraper_file_handler.setLevel(_log_level)
scraper_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Console handler (optional)
scraper_console_handler = logging.StreamHandler(sys.stdout)
scraper_console_handler.setLevel(_log_level)
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
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.warning(f"404 Not Found: {url}")
                return 404
            logger.error(f"Failed to fetch {url}: {e}")
            return None
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def scrape_page(self, url: str, section: str, max_retries: int = 3, status_callback=None, page_num: int = None, total_pages: int = None) -> tuple[int, int, int]:
        """
        Scrape a single page and save titles to database.

        Args:
            url: The page URL
            section: The section name
            max_retries: Maximum number of retry attempts (default: 3)
            status_callback: Optional callback function(status_message) to update status
            page_num: Current page number (optional, for status messages)
            total_pages: Total number of pages (optional, for status messages)

        Returns:
            Tuple of (titles_found, inserted, updated)
        """
        # Create prefix for status messages if page info is provided
        page_prefix = ""
        if page_num is not None and total_pages is not None:
            page_prefix = f"[{page_num}/{total_pages}] "
        
        def update_status(msg):
            # Add page prefix to all status messages
            prefixed_msg = page_prefix + msg
            if status_callback:
                status_callback(prefixed_msg)
            logger.info(prefixed_msg)
        
        logger.info(f"{page_prefix}Scraping page: {section} - {url} (max retries: {max_retries})")
        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                update_status(f"Tentativo {attempt}/{max_retries}...")
            logger.debug(f"Attempt {attempt}/{max_retries} for {url}")
            html = self.fetch_page(url)
            if html == 404:
                error_msg = f"Errore: pagina non trovata (404) - {url}"
                update_status(error_msg)
                logger.warning(f"{page_prefix}404 for list page {url}, skipping")
                return None
            if html:
                titles = parser.parse_page(html, section)
                update_status(f"Trovati {len(titles)} titoli, inserimento in corso...")
                logger.info(f"{page_prefix}Found {len(titles)} titles on page")

                # Optionally enrich each title by visiting its individual post page
                if config.SCRAPE_POST_DETAILS and titles:
                    update_status(f"Scaricamento dettagli post ({config.POST_DETAIL_WORKERS} paralleli)...")
                    logger.info(f"{page_prefix}Fetching post details for {len(titles)} titles "
                                f"({config.POST_DETAIL_WORKERS} workers)")
                    _semaphore = threading.Semaphore(config.POST_DETAIL_WORKERS)

                    def _fetch_detail(title_data):
                        with _semaphore:
                            time.sleep(config.REQUEST_DELAY)
                            detail_html = self.fetch_page(title_data['url'])
                            if detail_html == 404:
                                deleted = database.delete_title(title_data['url'])
                                if deleted:
                                    logger.info(f"Deleted 404 title: {title_data['title']}")
                                title_data['_deleted'] = True
                                return title_data
                            if detail_html:
                                detail = parser.parse_post_detail(detail_html)
                                if detail.get('quality'):
                                    title_data['quality'] = detail['quality']
                                if detail.get('metadata'):
                                    existing = title_data.get('metadata') or ''
                                    combined = (existing + ' | ' + detail['metadata']
                                                if existing else detail['metadata'])
                                    title_data['metadata'] = ' | '.join(
                                        dict.fromkeys(combined.split(' | ')))
                                title_data['languages'] = detail.get('languages')
                                title_data['status'] = detail.get('status')
                                title_data['raw_info'] = detail.get('raw_info')
                        return title_data

                    detail_total = len(titles)
                    detail_done = 0
                    inserted = 0
                    updated = 0
                    with ThreadPoolExecutor(max_workers=config.POST_DETAIL_WORKERS) as executor:
                        futures = {executor.submit(_fetch_detail, t): t for t in titles}
                        for future in as_completed(futures):
                            title_data = future.result()
                            detail_done += 1

                            if title_data.get('_deleted'):
                                continue

                            is_new = database.insert_title(
                                title=title_data['title'],
                                url=title_data['url'],
                                section=title_data['section'],
                                metadata=title_data.get('metadata'),
                                quality=title_data.get('quality'),
                                languages=title_data.get('languages'),
                                status=title_data.get('status'),
                                raw_info=title_data.get('raw_info')
                            )
                            if is_new:
                                inserted += 1
                                logger.debug(f"{page_prefix}[NUOVO] {title_data['title']} "
                                             f"[q={title_data.get('quality')} lang={title_data.get('languages')} "
                                             f"status={title_data.get('status')}]")
                            else:
                                updated += 1
                                logger.debug(f"{page_prefix}[GIA' PRESENTE] {title_data['title']} "
                                             f"[q={title_data.get('quality')} lang={title_data.get('languages')} "
                                             f"status={title_data.get('status')}]")

                            if detail_done % 10 == 0 or detail_done == detail_total:
                                update_status(f"Dettagli: {detail_done}/{detail_total} scaricati "
                                              f"({inserted} nuovi, {updated} aggiornati)...")

                total_processed = inserted + updated
                logger.info(f"{page_prefix}Inserted {inserted} new titles, updated {updated}")
                return (total_processed, inserted, updated)
            else:
                if attempt < max_retries:
                    # Exponential backoff: 1s, 2s, 4s...
                    wait_time = 2 ** (attempt - 1)
                    update_status(f"Errore nel download (tentativo {attempt}/{max_retries}), nuovo tentativo tra {wait_time}s...")
                    logger.warning(f"{page_prefix}Failed to fetch {url} (attempt {attempt}/{max_retries}). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    error_msg = f"Errore: impossibile scaricare la pagina dopo {max_retries} tentativi"
                    update_status(error_msg)
                    logger.error(f"{page_prefix}Failed to fetch {url} after {max_retries} attempts. Skipping.")

        return None

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
        if result is None:
            # scrape_page already set the error status, don't overwrite it
            logger.info(f"Single page import failed for {url}")
            return (0, 0, 0)
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

                result = self.scrape_page(
                    url,
                    section,
                    status_callback=status_callback,
                    page_num=i,
                    total_pages=len(pages)
                )
                if result is not None:
                    found, inserted, updated = result
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
