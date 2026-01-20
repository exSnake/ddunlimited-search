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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/scraper.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


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

    def scrape_page(self, url: str, section: str) -> tuple[int, int, int]:
        """
        Scrape a single page and save titles to database.

        Args:
            url: The page URL
            section: The section name

        Returns:
            Tuple of (titles_found, inserted, updated)
        """
        html = self.fetch_page(url)
        if not html:
            return (0, 0, 0)

        titles = parser.parse_page(html, section)
        logger.info(f"Found {len(titles)} titles on page")

        inserted = 0
        updated = 0
        for title_data in titles:
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

        logger.info(f"Inserted {inserted} new titles, updated {updated}")
        return (len(titles), inserted, updated)

    def run(self):
        """Run the scraper."""
        logger.info("Starting DDUnlimited scraper...")

        # Initialize database
        database.init_db()
        logger.info("Database initialized")

        # Start import tracking
        import_id = database.start_import()
        logger.info(f"Import session started (ID: {import_id})")

        try:
            # Login
            if not self.login():
                logger.error("Failed to login. Exiting.")
                database.complete_import(import_id, 0, 0, 0, success=False)
                return

            # Load pages from file
            pages = parser.parse_pages_file(config.PAGES_FILE)
            if not pages:
                logger.error(f"No pages to scrape. Check {config.PAGES_FILE}")
                database.complete_import(import_id, 0, 0, 0, success=False)
                return

            logger.info(f"Loaded {len(pages)} pages to scrape")

            # Scrape each page
            total_titles = 0
            total_inserted = 0
            total_updated = 0
            for i, page_info in enumerate(pages, 1):
                section = page_info['section']
                url = page_info['url']

                logger.info(f"[{i}/{len(pages)}] Scraping: {section} - {url}")

                found, inserted, updated = self.scrape_page(url, section)
                total_titles += found
                total_inserted += inserted
                total_updated += updated

                # Rate limiting
                if i < len(pages):
                    logger.debug(f"Waiting {config.REQUEST_DELAY}s before next request...")
                    time.sleep(config.REQUEST_DELAY)

            # Complete import tracking
            database.complete_import(import_id, total_titles, total_inserted, total_updated, success=True)

            # Final stats
            stats = database.get_stats()
            logger.info(f"Scraping complete!")
            logger.info(f"Total titles found: {total_titles}")
            logger.info(f"New titles inserted: {total_inserted}")
            logger.info(f"Titles updated: {total_updated}")
            logger.info(f"Total titles in database: {stats['total_titles']}")
            logger.info(f"Total sections: {stats['total_sections']}")
        except Exception as e:
            logger.error(f"Error during scraping: {e}", exc_info=True)
            database.complete_import(import_id, 0, 0, 0, success=False)
            raise


def main():
    """Main entry point."""
    scraper = DDUnlimitedScraper()
    scraper.run()


if __name__ == "__main__":
    main()
