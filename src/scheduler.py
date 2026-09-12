"""Scheduler for automatic reimportation."""

import logging
import os
import sys
import time
from datetime import datetime, timedelta

import config
import database
import ratings
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

# How often the schedule is re-evaluated. Short enough that a change made in
# the admin UI takes effect without restarting the container.
POLL_SECONDS = 60

# How long to wait before retrying once an attempt has already been made.
# Without it a scraper that cannot authenticate would hammer the forum on
# every poll.
RETRY_BACKOFF = timedelta(hours=1)

# The ratings pass has its own cadence: TMDB has a backlog to chew through
# after an import, and the OMDb daily budget refills every night.
RATINGS_INTERVAL = timedelta(hours=6)


def parse_timestamp(value) -> datetime | None:
    """Parse a timestamp as written by any past version of complete_import."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None

    for attempt in (
        lambda v: datetime.fromisoformat(v.replace('Z', '+00:00')).replace(tzinfo=None),
        lambda v: datetime.strptime(v, '%Y-%m-%d %H:%M:%S.%f'),
        lambda v: datetime.strptime(v, '%Y-%m-%d %H:%M:%S'),
    ):
        try:
            return attempt(value)
        except (ValueError, AttributeError):
            continue

    return None


def should_run_import(schedule: dict) -> tuple[bool, str]:
    """
    Decide whether an import is due.

    Returns:
        (should_run, reason) so the caller can log the reason only when it
        changes, instead of once per poll.
    """
    if not schedule['enabled']:
        return False, "Scheduled imports are disabled"

    now = datetime.now()
    last_attempt = database.get_last_import()
    attempted_at = parse_timestamp(last_attempt.get('started_at')) if last_attempt else None

    last_import = database.get_last_import(successful_only=True)
    last_completed = parse_timestamp(last_import.get('completed_at')) if last_import else None

    if not last_completed:
        if attempted_at and now - attempted_at < RETRY_BACKOFF:
            return False, "No successful import yet, waiting before the next attempt."
        return True, "No successful import found. Running first import."

    interval_days = schedule['interval_days']
    days_since_last = (now.date() - last_completed.date()).days
    if days_since_last < interval_days:
        return False, (f"Last successful import was {days_since_last} days ago. "
                       f"Waiting {interval_days - days_since_last} more days.")

    scheduled_time = now.replace(
        hour=schedule['hour'], minute=schedule['minute'], second=0, microsecond=0
    )

    if scheduled_time > now:
        return False, (f"Import is due, waiting for "
                       f"{schedule['hour']:02d}:{schedule['minute']:02d}.")

    # A one-hour window keeps a restart from re-running an import that already
    # ran earlier today.
    if (now - scheduled_time).total_seconds() / 3600 <= 1:
        # One attempt per window: without this a failing import would be retried
        # on every poll for the rest of the hour.
        if attempted_at and attempted_at >= scheduled_time:
            return False, "Already attempted an import in this window."

        return True, "Within scheduled time window. Running import."

    return False, (f"Scheduled time ({schedule['hour']:02d}:{schedule['minute']:02d}) "
                   f"passed. Waiting for next scheduled time.")


def run_import() -> bool:
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
        completed = scraper_instance.run()
    except Exception as e:
        logger.error(f"Error during scheduled import: {e}", exc_info=True)
        logger.error("=" * 60)
        logger.error("Scheduled import failed")
        logger.error("=" * 60)
        return False

    logger.info("=" * 60)
    if completed:
        logger.info("Scheduled import completed successfully")
    else:
        logger.error("Scheduled import did not complete. See scraper.log.")
    logger.info("=" * 60)
    return bool(completed)


def run_ratings() -> None:
    """Match the new titles and top up the IMDb votes."""
    if not config.RATINGS_ENABLED or not config.TMDB_API_KEY:
        return

    try:
        result = ratings.run_enrichment(limit=config.RATING_MAX_PER_RUN)
        logger.info(f"Ratings enrichment: {result}")
    except Exception as e:
        logger.error(f"Error during ratings enrichment: {e}", exc_info=True)


def main():
    """Main scheduler loop."""
    logger.info("DDUnlimited Search Scheduler starting...")

    database.init_db()
    database.migrate_refresh_policy()
    logger.info("Database initialized")

    schedule = database.get_schedule()
    logger.info(f"Scrape interval: {schedule['interval_days']} days")
    logger.info(f"Scheduled time: {schedule['hour']:02d}:{schedule['minute']:02d}")

    last_reason = None
    next_ratings_at = datetime.now()
    while True:
        try:
            schedule = database.get_schedule()
            due, reason = should_run_import(schedule)

            if reason != last_reason:
                logger.info(reason)
                last_reason = reason

            if due:
                run_import()
                last_reason = None
                next_ratings_at = datetime.now()

            if datetime.now() >= next_ratings_at:
                run_ratings()
                next_ratings_at = datetime.now() + RATINGS_INTERVAL

            time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)
            logger.info("Waiting 1 hour before retrying...")
            time.sleep(3600)


if __name__ == "__main__":
    main()
