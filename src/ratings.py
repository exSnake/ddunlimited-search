"""External ratings for DDUnlimited Search.

Titles are matched against TMDB, which also hands back the IMDb id; the IMDb
vote itself is then pulled from OMDb, whose free plan is rationed by day.
"""

import logging
import os
import re
import sys
import time
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from typing import Optional

import requests

import config
import database

os.makedirs('logs', exist_ok=True)

logger = logging.getLogger('ratings')
logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
logger.handlers.clear()
_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
for _handler in (logging.FileHandler('logs/ratings.log', encoding='utf-8'),
                 logging.StreamHandler(sys.stdout)):
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
logger.propagate = False

TMDB_BASE = "https://api.themoviedb.org/3"
OMDB_BASE = "https://www.omdbapi.com/"

RATE_LIMIT_MAX_RETRIES = 3
RATE_LIMIT_BACKOFF_BASE = 5

# Everything the forum appends to a title and no catalogue knows about.
NOISE_SUFFIX_RE = re.compile(
    r'\s*[-–]\s*('
    r'stagion[ei]\b.*|season\b.*|serie\s+completa\b.*|miniserie\b.*|'
    r'filmtv\b.*|completa\b.*|collection\b.*|saga\b.*|trilogia\b.*|'
    r'ep\.?\s*\d+.*|episodi\b.*'
    r')$',
    re.IGNORECASE
)

SEASON_RE = re.compile(r'\b(stagione|season|serie\s+completa|miniserie|episodi)\b', re.IGNORECASE)

# The forum writes accented capitals with a trailing apostrophe (PAPA', PERCHE').
TRAILING_APOSTROPHE_RE = re.compile(r"(?<=[A-Za-z])'(?=\s|$)")
ACCENTED_VOWEL_RE = re.compile(r"([AEIOUaeiou])'(?=\s|$)")
ACCENTED_VOWELS = {'A': 'À', 'E': 'È', 'I': 'Ì', 'O': 'Ò', 'U': 'Ù',
                   'a': 'à', 'e': 'è', 'i': 'ì', 'o': 'ò', 'u': 'ù'}

TV_SECTION_RE = re.compile(r'serie|anime(?!\w)', re.IGNORECASE)


class RatingsError(Exception):
    """Raised when a provider is unusable, so the job stops instead of looping."""


def strip_accents(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')


def normalize_for_compare(text: str) -> str:
    """Lowercase, unaccented, punctuation-free form used to compare two titles."""
    text = strip_accents(text.lower())
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return ' '.join(text.split())


def restore_accents(text: str) -> str:
    """Turn the forum's PAPA' into PAPÀ, leaving a real apostrophe alone."""
    return ACCENTED_VOWEL_RE.sub(lambda m: ACCENTED_VOWELS[m.group(1)], text)


def clean_title(title: str) -> str:
    """Strip from a forum title everything a catalogue would not recognise."""
    cleaned = re.sub(r'\[[^\]]*\]', ' ', title)
    cleaned = re.sub(r'\([^)]*\)', ' ', cleaned)
    cleaned = NOISE_SUFFIX_RE.sub('', cleaned)
    cleaned = cleaned.strip(' -–,;:.')
    return ' '.join(cleaned.split())


def title_variants(title: str) -> list[str]:
    """Query strings to try, in decreasing order of fidelity to the original."""
    variants = []

    def add(value):
        value = ' '.join(value.split()).strip(' -–,;:.')
        if value and value not in variants:
            variants.append(value)

    base = clean_title(title)
    add(base)

    add(restore_accents(base))
    add(TRAILING_APOSTROPHE_RE.sub('', base))

    # Last resort: titles whose subtitle sits after a dash we do not recognise.
    if ' - ' in base:
        add(base.rsplit(' - ', 1)[0])

    return variants


def media_types_for(section: Optional[str], title: str) -> list[str]:
    """The TMDB endpoints to try for a title, best guess first."""
    if SEASON_RE.search(title):
        return ['tv', 'movie']
    if section and TV_SECTION_RE.search(section):
        return ['tv', 'movie']
    return ['movie', 'tv']


def _person_key(name: str) -> str:
    """Surname of a director, which is all the two sides reliably share."""
    parts = normalize_for_compare(name).split()
    return parts[-1] if parts else ''


class TMDBClient:
    """Minimal TMDB client: search, then details for the winner."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else config.TMDB_API_KEY
        if not self.api_key:
            raise RatingsError("TMDB_API_KEY non configurata")

        self.session = requests.Session()
        # v4 tokens go in the header, v3 keys in the query string.
        if self.api_key.startswith('eyJ'):
            self.session.headers['Authorization'] = f'Bearer {self.api_key}'
            self._key_param = None
        else:
            self._key_param = self.api_key
        self.session.headers['Accept'] = 'application/json'
        self.calls = 0

    def _get(self, path: str, **params) -> Optional[dict]:
        if self._key_param:
            params['api_key'] = self._key_param
        params.setdefault('language', config.TMDB_LANGUAGE)

        for attempt in range(RATE_LIMIT_MAX_RETRIES):
            time.sleep(config.TMDB_REQUEST_DELAY)
            self.calls += 1
            try:
                response = self.session.get(
                    f"{TMDB_BASE}{path}", params=params, timeout=config.REQUEST_TIMEOUT
                )
            except requests.RequestException as exc:
                logger.warning(f"TMDB {path}: {exc}")
                time.sleep(RATE_LIMIT_BACKOFF_BASE * (attempt + 1))
                continue

            if response.status_code == 429:
                wait = float(response.headers.get('Retry-After', RATE_LIMIT_BACKOFF_BASE))
                logger.info(f"TMDB rate limit, attendo {wait}s")
                time.sleep(wait)
                continue
            if response.status_code in (401, 403):
                raise RatingsError("TMDB ha rifiutato la chiave API")
            if response.status_code == 404:
                return None
            if not response.ok:
                logger.warning(f"TMDB {path}: HTTP {response.status_code}")
                return None
            return response.json()

        return None

    def search(self, media_type: str, query: str) -> list[dict]:
        data = self._get(f"/search/{media_type}", query=query, include_adult='false')
        return (data or {}).get('results', [])[:10]

    def details(self, media_type: str, tmdb_id: int) -> Optional[dict]:
        extra = 'external_ids,credits' if media_type == 'tv' else 'credits'
        return self._get(f"/{media_type}/{tmdb_id}", append_to_response=extra)


def candidate_fields(media_type: str, candidate: dict) -> tuple[str, str, Optional[int]]:
    """(title, original title, year) out of a search result of either kind."""
    if media_type == 'tv':
        name = candidate.get('name') or ''
        original = candidate.get('original_name') or ''
        released = candidate.get('first_air_date') or ''
    else:
        name = candidate.get('title') or ''
        original = candidate.get('original_title') or ''
        released = candidate.get('release_date') or ''

    year = int(released[:4]) if released[:4].isdigit() else None
    return name, original, year


def score_candidate(query: str, year: Optional[int], media_type: str, candidate: dict) -> float:
    """How much a search result looks like the title we are holding, 0 to 1."""
    name, original, cand_year = candidate_fields(media_type, candidate)
    wanted = normalize_for_compare(query)

    ratio = max(
        SequenceMatcher(None, wanted, normalize_for_compare(name)).ratio() if name else 0.0,
        SequenceMatcher(None, wanted, normalize_for_compare(original)).ratio() if original else 0.0,
    )

    score = ratio * 0.8
    if year and cand_year:
        delta = abs(year - cand_year)
        if delta == 0:
            score += 0.2
        elif delta == 1:
            score += 0.1
        else:
            score -= 0.25
    return max(0.0, min(1.0, score))


def directors_of(media_type: str, details: dict) -> list[str]:
    if media_type == 'tv':
        names = [p.get('name', '') for p in details.get('created_by', [])]
    else:
        names = [c.get('name', '') for c in details.get('credits', {}).get('crew', [])
                 if c.get('job') == 'Director']
    return [n for n in names if n]


def apply_director_bonus(score: float, our_director: Optional[str],
                         media_type: str, details: dict) -> float:
    """Nudge the score with the director, the one field the title already carries."""
    if not our_director:
        return score

    theirs = {_person_key(name) for name in directors_of(media_type, details)}
    if not theirs:
        return score

    return min(1.0, score + 0.15) if _person_key(our_director) in theirs else max(0.0, score - 0.15)


def build_match(media_type: str, details: dict, confidence: float) -> dict:
    """Flatten TMDB details into the columns of title_ratings."""
    if media_type == 'tv':
        name = details.get('name')
        released = details.get('first_air_date') or ''
        imdb_id = (details.get('external_ids') or {}).get('imdb_id')
    else:
        name = details.get('title')
        released = details.get('release_date') or ''
        imdb_id = details.get('imdb_id')

    votes = details.get('vote_count') or 0
    return {
        'media_type': media_type,
        'tmdb_id': details.get('id'),
        'imdb_id': imdb_id or None,
        'tmdb_rating': details.get('vote_average') if votes else None,
        'tmdb_votes': votes or None,
        'poster_path': details.get('poster_path'),
        'matched_title': name,
        'matched_year': int(released[:4]) if released[:4].isdigit() else None,
        'confidence': round(confidence, 3),
    }


def match_title(client: TMDBClient, row: dict) -> Optional[dict]:
    """Look a single title up on TMDB. None when nothing scored high enough."""
    best = None
    best_score = 0.0
    best_type = None

    for media_type in media_types_for(row.get('section'), row['title']):
        for query in title_variants(row['title']):
            for candidate in client.search(media_type, query):
                score = score_candidate(query, row.get('year'), media_type, candidate)
                if score > best_score:
                    best, best_score, best_type = candidate, score, media_type

            # A confident hit makes the remaining variants pointless.
            if best_score >= 0.9:
                break
        if best_score >= 0.9:
            break

    if not best or best_score < 0.4:
        return None

    details = client.details(best_type, best['id'])
    if not details:
        return None

    confidence = apply_director_bonus(best_score, row.get('director'), best_type, details)
    return build_match(best_type, details, confidence)


def match_by_tmdb_id(media_type: str, tmdb_id: int) -> Optional[dict]:
    """Fetch one known TMDB entry, for a match corrected by hand."""
    client = TMDBClient()
    details = client.details(media_type, tmdb_id)
    if not details:
        return None
    return build_match(media_type, details, 1.0)


def parse_tmdb_reference(reference: str) -> Optional[tuple[str, int]]:
    """Read a TMDB url or a bare id out of what was typed in the review page."""
    reference = reference.strip()

    match = re.search(r'themoviedb\.org/(movie|tv)/(\d+)', reference)
    if match:
        return match.group(1), int(match.group(2))

    match = re.fullmatch(r'(movie|tv)[/:\s-]+(\d+)', reference, re.IGNORECASE)
    if match:
        return match.group(1).lower(), int(match.group(2))

    if reference.isdigit():
        return 'movie', int(reference)

    return None


def _omdb_budget_left() -> int:
    """Calls still allowed today under the free plan."""
    today = date.today().isoformat()
    if database.get_setting('omdb_calls_date') != today:
        return config.OMDB_DAILY_LIMIT
    return max(0, config.OMDB_DAILY_LIMIT - database.get_int_setting('omdb_calls_count', 0))


def _record_omdb_calls(count: int) -> None:
    today = date.today().isoformat()
    if database.get_setting('omdb_calls_date') != today:
        database.set_setting('omdb_calls_date', today)
        database.set_setting('omdb_calls_count', count)
    else:
        database.set_setting(
            'omdb_calls_count', database.get_int_setting('omdb_calls_count', 0) + count
        )


def fetch_omdb_rating(session: requests.Session, imdb_id: str) -> tuple[Optional[float], Optional[int]]:
    """The IMDb vote for one title. (None, None) when IMDb has no rating yet."""
    response = session.get(
        OMDB_BASE,
        params={'apikey': config.OMDB_API_KEY, 'i': imdb_id},
        timeout=config.REQUEST_TIMEOUT,
    )
    if response.status_code == 401:
        raise RatingsError("OMDb ha rifiutato la chiave API")
    if not response.ok:
        logger.warning(f"OMDb {imdb_id}: HTTP {response.status_code}")
        return None, None

    data = response.json()
    if data.get('Response') != 'True':
        logger.debug(f"OMDb {imdb_id}: {data.get('Error')}")
        return None, None

    rating = data.get('imdbRating')
    votes = data.get('imdbVotes', '').replace(',', '')
    return (
        float(rating) if rating and rating != 'N/A' else None,
        int(votes) if votes.isdigit() else None,
    )


def refresh_imdb_vote(title_id: int, imdb_id: str) -> bool:
    """Fetch one IMDb vote now, for a match just corrected by hand."""
    if not config.OMDB_API_KEY or _omdb_budget_left() <= 0:
        return False

    rating, votes = fetch_omdb_rating(requests.Session(), imdb_id)
    database.save_imdb_rating(title_id, rating, votes)
    _record_omdb_calls(1)
    return rating is not None


def match_pending(limit: Optional[int] = None, retry_unmatched: bool = False,
                  after_id: int = 0, status_callback=None) -> dict:
    """Match against TMDB the titles that still need a lookup."""
    limit = limit or config.RATING_BATCH_SIZE
    rows = database.get_titles_to_match(limit=limit, retry_unmatched=retry_unmatched,
                                        after_id=after_id)
    if not rows:
        return {'processed': 0, 'matched': 0, 'low_confidence': 0, 'unmatched': 0,
                'last_id': after_id}

    client = TMDBClient()
    counts = {'processed': 0, 'matched': 0, 'low_confidence': 0, 'unmatched': 0,
              'last_id': rows[-1]['id']}

    for row in rows:
        try:
            match = match_title(client, row)
        except RatingsError:
            raise
        except Exception as exc:
            logger.error(f"Errore sul titolo {row['id']} ({row['title']}): {exc}", exc_info=True)
            match = None

        if match:
            status = 'matched' if match['confidence'] >= config.RATING_MIN_CONFIDENCE else 'low_confidence'
            database.save_rating(row['id'], status, **match)
        else:
            status = 'unmatched'
            database.save_rating(row['id'], status)

        counts[status] += 1
        counts['processed'] += 1

        if status_callback and counts['processed'] % 25 == 0:
            status_callback(f"TMDB: {counts['processed']}/{len(rows)} titoli, "
                            f"{counts['matched']} agganciati")

    logger.info(f"Match TMDB: {counts} ({client.calls} richieste)")
    return counts


def fetch_imdb_votes(limit: Optional[int] = None, status_callback=None) -> dict:
    """Spend part of today's OMDb budget on the matches without an IMDb vote."""
    if not config.OMDB_API_KEY:
        return {'processed': 0, 'with_rating': 0, 'budget_left': 0, 'skipped': 'no_key'}

    budget = _omdb_budget_left()
    if limit:
        budget = min(budget, limit)
    if budget <= 0:
        return {'processed': 0, 'with_rating': 0, 'budget_left': 0, 'skipped': 'budget'}

    rows = database.get_ratings_missing_imdb(budget)
    session = requests.Session()
    processed = 0
    with_rating = 0

    try:
        for row in rows:
            rating, votes = fetch_omdb_rating(session, row['imdb_id'])
            database.save_imdb_rating(row['title_id'], rating, votes)
            processed += 1
            if rating is not None:
                with_rating += 1
            if status_callback and processed % 25 == 0:
                status_callback(f"OMDb: {processed}/{len(rows)} voti IMDb")
    finally:
        _record_omdb_calls(processed)

    logger.info(f"Voti IMDb: {processed} richieste, {with_rating} con voto")
    return {'processed': processed, 'with_rating': with_rating,
            'budget_left': _omdb_budget_left()}


def run_enrichment(limit: Optional[int] = None, retry_unmatched: bool = False,
                   status_callback=None) -> dict:
    """
    The whole pass: match on TMDB in batches, then top up the IMDb votes.

    Args:
        limit: how many titles at most. None drains the whole queue.
    """
    if not config.RATINGS_ENABLED:
        return {'skipped': 'disabled'}
    if not config.TMDB_API_KEY:
        return {'skipped': 'no_tmdb_key'}

    totals = {'processed': 0, 'matched': 0, 'low_confidence': 0, 'unmatched': 0}

    def batch_status(message):
        if status_callback:
            status_callback(f"{message}, {totals['processed']} completati in tutto")

    remaining = limit
    after_id = 0

    while remaining is None or remaining > 0:
        size = config.RATING_BATCH_SIZE
        if remaining is not None:
            size = min(size, remaining)

        counts = match_pending(limit=size, retry_unmatched=retry_unmatched,
                               after_id=after_id, status_callback=batch_status)
        after_id = counts['last_id']
        for key in totals:
            totals[key] += counts[key]
        if remaining is not None:
            remaining -= counts['processed']
        if counts['processed'] < size:
            break

    imdb = fetch_imdb_votes(status_callback=status_callback)
    return {'tmdb': totals, 'imdb': imdb}


def main():
    """Run one enrichment pass from the command line."""
    database.init_db()
    retry = '--retry-unmatched' in sys.argv
    result = run_enrichment(retry_unmatched=retry, status_callback=lambda msg: logger.info(msg))
    logger.info(f"Risultato: {result}")


if __name__ == "__main__":
    main()
