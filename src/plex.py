"""Read the Plex library: which films are there, and at what resolution.

Plex tags every film with the identifiers of the sources it matched against
(`tmdb://584`, `imdb://tt0322259`), the same ids title_ratings already holds,
so linking the library to the catalogue is a join and not a matching problem.
"""

import logging

import requests

import config
import database

logger = logging.getLogger(__name__)

# Plex reports the resolution of a file, not where the release came from; the
# forum's sigle collapse onto the same four steps.
RESOLUTION_CLASS = {
    '4k': '4K', '2160': '4K',
    '1080': '1080p',
    '720': '720p',
    'sd': 'SD', '480': 'SD', '576': 'SD',
}
RESOLUTION_RANK = {'SD': 0, '720p': 1, '1080p': 2, '4K': 3}

PAGE_SIZE = 500
TIMEOUT = 30


def is_configured() -> bool:
    return bool(config.PLEX_URL and config.PLEX_TOKEN)


def _get(path: str, **params) -> dict:
    response = requests.get(
        config.PLEX_URL.rstrip('/') + path,
        params=params,
        headers={'X-Plex-Token': config.PLEX_TOKEN, 'Accept': 'application/json'},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json().get('MediaContainer', {})


def movie_sections() -> list[tuple[str, str]]:
    """(key, name) of every library section that holds films."""
    return [(d['key'], d.get('title', ''))
            for d in _get('/library/sections').get('Directory', [])
            if d.get('type') == 'movie']


def _guid(item: dict, scheme: str) -> str | None:
    for guid in item.get('Guid', []):
        value = guid.get('id', '')
        if value.startswith(scheme):
            return value[len(scheme):]
    return None


def _best_copy(item: dict) -> tuple[str | None, str | None]:
    """(raw resolution, class) of the highest-resolution file Plex holds."""
    best = (None, None)
    for media in item.get('Media', []):
        raw = str(media.get('videoResolution', '')).lower()
        cls = RESOLUTION_CLASS.get(raw)
        if cls and (best[1] is None or RESOLUTION_RANK[cls] > RESOLUTION_RANK[best[1]]):
            best = (raw, cls)
    return best


def _film(item: dict, section: str) -> dict:
    tmdb = _guid(item, 'tmdb://')
    resolution, quality = _best_copy(item)
    return {
        'rating_key': int(item['ratingKey']),
        'title': item.get('title'),
        'year': item.get('year'),
        'tmdb_id': int(tmdb) if tmdb and tmdb.isdigit() else None,
        'imdb_id': _guid(item, 'imdb://'),
        'resolution': resolution,
        'quality': quality,
        'section': section,
    }


def fetch_films() -> list[dict]:
    """Every film in every movie section, one request per page of 500."""
    films = []
    for key, name in movie_sections():
        start = 0
        while True:
            page = _get(f'/library/sections/{key}/all', type=1, includeGuids=1,
                        **{'X-Plex-Container-Start': start,
                           'X-Plex-Container-Size': PAGE_SIZE})
            items = page.get('Metadata', [])
            films.extend(_film(item, name) for item in items)
            start += len(items)
            if not items or start >= int(page.get('totalSize') or 0):
                break
    return films


def refresh() -> dict:
    """Re-read the library and replace what the database holds."""
    films = fetch_films()
    stored = database.replace_plex_items(films)
    logger.info(f"Plex: {len(films)} film letti, {stored} con id TMDB")
    return {'films': len(films), 'with_tmdb': stored}
