"""Forum session cookies pushed in from the browser.

Cloudflare fronts the login endpoint with a JS challenge, so the scraper
cannot authenticate on its own. It reuses a session captured from a browser
that is already logged in, kept in a JSON file on the volume both the web
and scheduler containers mount.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Optional

import config


def _path() -> str:
    return config.SESSION_FILE


def normalize_cookies(raw) -> dict:
    """
    Accept either a name -> value mapping or a list of cookie objects as
    returned by chrome.cookies.getAll(), and return a flat mapping.
    """
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if k}

    if isinstance(raw, list):
        cookies = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get('name')
            if name:
                cookies[str(name)] = str(item.get('value', ''))
        return cookies

    return {}


# Cloudflare reissues these on every visit, so their short lifetime says
# nothing about how long the forum session lasts.
_TRANSIENT_COOKIES = {'__cf_bm', 'cf_clearance', '__cfruid', '__cflb'}


def _as_naive(value: str) -> Optional[datetime]:
    """Parse an ISO timestamp as local wall time, dropping any offset."""
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        return None

    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone().replace(tzinfo=None)


def earliest_expiry(raw) -> Optional[str]:
    """Return the soonest expiry among cookie objects, as an ISO string."""
    if not isinstance(raw, list):
        return None

    stamps = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get('name') in _TRANSIENT_COOKIES:
            continue
        value = item.get('expirationDate')
        if value:
            try:
                stamps.append(datetime.fromtimestamp(float(value)))
            except (TypeError, ValueError, OSError):
                continue

    return min(stamps).isoformat() if stamps else None


def save(cookies: dict, expires_at: str = None, source: str = 'unknown',
         user_agent: str = None) -> dict:
    """Persist a verified session and return the stored record."""
    record = {
        'cookies': cookies,
        'updated_at': datetime.now().isoformat(),
        'expires_at': expires_at,
        'source': source,
        'user_agent': user_agent,
    }

    directory = os.path.dirname(_path())
    if directory:
        os.makedirs(directory, exist_ok=True)

    # Write through a temporary file so the scheduler never reads a half-written
    # session while the web container is saving one. The name has to be unique
    # across containers, which rules out the pid: they each have their own.
    handle, tmp = tempfile.mkstemp(dir=directory or '.', prefix='.session-', suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2)
        os.replace(tmp, _path())
    except Exception:
        os.unlink(tmp)
        raise

    return record


def refresh(cookies: dict) -> Optional[dict]:
    """
    Update the stored cookies, keeping the rest of the record.

    phpBB rotates the session id and the autologin key as it uses them, so the
    values that come back from a request are the ones worth keeping.
    """
    record = load()
    if not record:
        return None

    merged = {**record['cookies'], **cookies}
    if merged == record['cookies']:
        return record

    return save(merged, expires_at=record.get('expires_at'),
                source=record.get('source', 'unknown'),
                user_agent=record.get('user_agent'))


def load() -> Optional[dict]:
    """Read the stored session, or None when absent or unreadable."""
    try:
        with open(_path(), 'r', encoding='utf-8') as handle:
            record = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    if not isinstance(record, dict) or not record.get('cookies'):
        return None

    return record


def clear() -> None:
    """Remove the stored session."""
    try:
        os.remove(_path())
    except FileNotFoundError:
        pass


def status() -> dict:
    """Describe the stored session for the admin UI."""
    record = load()
    if not record:
        return {'present': False, 'state': 'missing'}

    info = {
        'present': True,
        'state': 'ok',
        'updated_at': record.get('updated_at'),
        'expires_at': record.get('expires_at'),
        'source': record.get('source'),
        'user_agent': record.get('user_agent'),
        'cookie_names': sorted(record.get('cookies', {}).keys()),
    }

    expiry = _as_naive(record.get('expires_at') or '')
    if expiry:
        now = datetime.now()
        if expiry <= now:
            info['state'] = 'expired'
        elif expiry - now < timedelta(days=3):
            info['state'] = 'expiring'
        info['days_left'] = max((expiry - now).days, 0)

    return info
