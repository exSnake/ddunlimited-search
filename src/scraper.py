"""Main scraper module for DDUnlimited Search."""

import logging
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

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

                    # Pre-load existing details from DB to avoid redundant HTTP requests.
                    # Each post gets a randomised next-refresh date based on post age so they
                    # don't all expire simultaneously and cause a 12-hour mega-run.
                    _now = datetime.now()
                    _existing = database.get_existing_details([t['url'] for t in titles])

                    def _refresh_interval(post_created_at) -> int:
                        """Randomised refresh interval (days) based on post age.

                        < 6 months  → 25–35 days  (content still evolving)
                        6m – 2 years → 75–105 days
                        > 2 years   → 150–210 days (stable, rarely changes)
                        """
                        created = None
                        if post_created_at:
                            try:
                                created = datetime.fromisoformat(str(post_created_at))
                            except (ValueError, TypeError):
                                pass

                        age_days = (_now - created).days if created else 365

                        if age_days < 180:
                            return random.randint(25, 35)
                        elif age_days < 730:
                            return random.randint(75, 105)
                        else:
                            return random.randint(150, 210)

                    _semaphore = threading.Semaphore(config.POST_DETAIL_WORKERS)

                    def _fetch_detail(title_data):
                        url = title_data['url']
                        existing = _existing.get(url)

                        # Skip HTTP fetch if next refresh date hasn't been reached yet
                        if existing and existing.get('details_next_refresh_at'):
                            try:
                                next_refresh = datetime.fromisoformat(existing['details_next_refresh_at'])
                            except (ValueError, TypeError):
                                next_refresh = None
                            if next_refresh and _now < next_refresh:
                                title_data['languages'] = existing['languages']
                                title_data['status'] = existing['status']
                                title_data['raw_info'] = existing['raw_info']
                                title_data['_details_skipped'] = True
                                logger.debug(f"Dettagli freschi fino a {next_refresh.date()}, skip: {title_data['title']}")
                                return title_data

                        with _semaphore:
                            time.sleep(config.REQUEST_DELAY)
                            detail_html = self.fetch_page(url)
                            if detail_html == 404:
                                deleted = database.delete_title(url)
                                if deleted:
                                    logger.info(f"Deleted 404 title: {title_data['title']}")
                                title_data['_deleted'] = True
                                return title_data
                            if detail_html:
                                detail = parser.parse_post_detail(detail_html)
                                if detail.get('quality'):
                                    title_data['quality'] = detail['quality']
                                if detail.get('metadata'):
                                    existing_meta = title_data.get('metadata') or ''
                                    combined = (existing_meta + ' | ' + detail['metadata']
                                                if existing_meta else detail['metadata'])
                                    title_data['metadata'] = ' | '.join(
                                        dict.fromkeys(combined.split(' | ')))
                                title_data['languages'] = detail.get('languages')
                                title_data['status'] = detail.get('status')
                                title_data['raw_info'] = detail.get('raw_info')
                                title_data['post_created_at'] = detail.get('post_created_at')
                                title_data['_details_scraped_at'] = _now
                                interval = _refresh_interval(detail.get('post_created_at'))
                                title_data['_details_next_refresh_at'] = _now + timedelta(days=interval)
                                logger.debug(f"Next refresh in {interval}d: {title_data['title']}")
                        return title_data

                    detail_total = len(titles)
                    detail_done = 0
                    inserted = 0
                    updated = 0
                    skipped_details = 0
                    with ThreadPoolExecutor(max_workers=config.POST_DETAIL_WORKERS) as executor:
                        futures = {executor.submit(_fetch_detail, t): t for t in titles}
                        for future in as_completed(futures):
                            title_data = future.result()
                            detail_done += 1

                            if title_data.get('_deleted'):
                                continue

                            details_were_skipped = title_data.get('_details_skipped', False)
                            if details_were_skipped:
                                skipped_details += 1

                            is_new = database.insert_title(
                                title=title_data['title'],
                                url=title_data['url'],
                                section=title_data['section'],
                                metadata=title_data.get('metadata'),
                                quality=title_data.get('quality'),
                                languages=title_data.get('languages'),
                                status=title_data.get('status'),
                                raw_info=title_data.get('raw_info'),
                                details_scraped_at=title_data.get('_details_scraped_at'),
                                details_next_refresh_at=title_data.get('_details_next_refresh_at'),
                                post_created_at=title_data.get('post_created_at'),
                                update_details=not details_were_skipped,
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
                                update_status(f"Dettagli: {detail_done}/{detail_total} "
                                              f"({inserted} nuovi, {updated} aggiornati, "
                                              f"{skipped_details} già freschi)...")

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
