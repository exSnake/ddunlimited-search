"""Scheduler for automatic reimportation."""

import logging
import os
import sys
import time
from datetime import datetime, timedelta

import config
import database
import scraper

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/scheduler.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def should_run_import() -> bool:
    """
    Check if import should run based on last import time and schedule.
    Returns True if import should run.
    """
    interval_days = int(os.getenv('SCRAPE_INTERVAL_DAYS', '3'))
    scrape_hour = int(os.getenv('SCRAPE_HOUR', '2'))
    scrape_minute = int(os.getenv('SCRAPE_MINUTE', '0'))

    last_import = database.get_last_import()
    
    if not last_import:
        logger.info("No previous import found. Running first import.")
        return True

    last_completed = last_import.get('completed_at')
    if not last_completed:
        logger.info("Last import did not complete. Running import.")
        return True

    # Parse the completed_at timestamp
    if isinstance(last_completed, str):
        try:
            # Try ISO format first
            if 'T' in last_completed:
                last_completed = datetime.fromisoformat(last_completed.replace('Z', '+00:00'))
                if last_completed.tzinfo:
                    last_completed = last_completed.replace(tzinfo=None)
            else:
                # Try SQLite datetime format
                last_completed = datetime.strptime(last_completed, '%Y-%m-%d %H:%M:%S.%f')
        except (ValueError, AttributeError):
            try:
                last_completed = datetime.strptime(last_completed, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                logger.warning(f"Could not parse timestamp: {last_completed}. Running import.")
                return True
    
    # Check if enough days have passed
    if isinstance(last_completed, datetime):
        days_since_last = (datetime.now() - last_completed).days
    else:
        logger.warning(f"Unexpected timestamp type: {type(last_completed)}. Running import.")
        return True
    if days_since_last < interval_days:
        logger.info(f"Last import was {days_since_last} days ago. "
                   f"Waiting {interval_days - days_since_last} more days.")
        return False

    # Check if we're at the scheduled time (within a 1-hour window)
    now = datetime.now()
    scheduled_time = now.replace(hour=scrape_hour, minute=scrape_minute, second=0, microsecond=0)
    
    # If scheduled time is in the past today, check if we're within 1 hour after it
    if scheduled_time < now:
        time_diff = (now - scheduled_time).total_seconds() / 3600
        if time_diff <= 1:
            logger.info(f"Within scheduled time window. Running import.")
            return True
        else:
            # Scheduled time passed, wait for next day
            logger.info(f"Scheduled time ({scrape_hour:02d}:{scrape_minute:02d}) passed. "
                       f"Waiting for next scheduled time.")
            return False
    else:
        # Scheduled time is in the future today
        logger.info(f"Scheduled time is {scrape_hour:02d}:{scrape_minute:02d}. "
                   f"Current time is {now.hour:02d}:{now.minute:02d}. Waiting.")
        return False


def wait_until_scheduled_time():
    """Wait until the scheduled time."""
    scrape_hour = int(os.getenv('SCRAPE_HOUR', '2'))
    scrape_minute = int(os.getenv('SCRAPE_MINUTE', '0'))
    
    now = datetime.now()
    scheduled_time = now.replace(hour=scrape_hour, minute=scrape_minute, second=0, microsecond=0)
    
    # If scheduled time is in the past, schedule for tomorrow
    if scheduled_time < now:
        scheduled_time += timedelta(days=1)
    
    wait_seconds = (scheduled_time - now).total_seconds()
    logger.info(f"Waiting until {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')} "
               f"({wait_seconds/3600:.1f} hours)")
    
    time.sleep(wait_seconds)


def run_import():
    """
    Run the scraper import.
    
    Note: Retry logic (3 attempts per page) is handled automatically
    by the scraper.scrape_page() method with exponential backoff.
    """
    logger.info("=" * 60)
    logger.info("Starting scheduled import")
    logger.info("=" * 60)
    
    try:
        scraper_instance = scraper.DDUnlimitedScraper()
        scraper_instance.run()
        logger.info("=" * 60)
        logger.info("Scheduled import completed successfully")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Error during scheduled import: {e}", exc_info=True)
        logger.error("=" * 60)
        logger.error("Scheduled import failed")
        logger.error("=" * 60)


def main():
    """Main scheduler loop."""
    logger.info("DDUnlimited Search Scheduler starting...")
    logger.info(f"Scrape interval: {os.getenv('SCRAPE_INTERVAL_DAYS', '3')} days")
    logger.info(f"Scheduled time: {os.getenv('SCRAPE_HOUR', '2')}:{os.getenv('SCRAPE_MINUTE', '0')}")
    
    # Initialize database
    database.init_db()
    logger.info("Database initialized")
    
    # Run initial import if needed
    if should_run_import():
        run_import()
    
    # Main loop
    while True:
        try:
            # Wait until scheduled time
            wait_until_scheduled_time()
            
            # Check if we should run import
            if should_run_import():
                run_import()
            else:
                logger.info("Skipping import - conditions not met")
                
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)
            logger.info("Waiting 1 hour before retrying...")
            time.sleep(3600)


if __name__ == "__main__":
    main()
