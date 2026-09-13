"""Flask web server for DDUnlimited Search."""

import hmac
import logging
import os
import sys
import threading
from datetime import datetime
from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.serving import WSGIRequestHandler

import config
import database
import parser
import ratings
import scraper
import session_store

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging for Flask/web server
# Use a separate logger to avoid conflicts with scraper logger
web_logger = logging.getLogger('web')
web_logger.setLevel(logging.INFO)

# Remove any existing handlers
web_logger.handlers.clear()

# File handler for web server logs
web_file_handler = logging.FileHandler('logs/web.log', encoding='utf-8')
web_file_handler.setLevel(logging.INFO)
web_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Alloy collects the container's stdout into Loki, which is where the logs are
# read now: anything held back from here is invisible in Grafana.
web_console_handler = logging.StreamHandler(sys.stdout)
web_console_handler.setLevel(logging.INFO)
web_console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

web_logger.addHandler(web_file_handler)
web_logger.addHandler(web_console_handler)
web_logger.propagate = False  # Don't propagate to root logger

# Configure Flask's logger
flask_logger = logging.getLogger('werkzeug')
flask_logger.setLevel(logging.INFO)
flask_logger.handlers.clear()
flask_logger.addHandler(web_file_handler)
flask_logger.addHandler(web_console_handler)
flask_logger.propagate = False

# Custom request handler to log to our web logger
class CustomRequestHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        # One line per request, ours: werkzeug's own would repeat it with the
        # terminal colour codes still in the text, which Loki stores verbatim.
        web_logger.info(f'{self.address_string()} - - [{self.log_date_time_string()}] "{self.requestline}" {code} {size}')

app = Flask(__name__)

# Thread-safe flag for tracking import status
import_status = {
    'running': False,
    'type': None,  # 'single' or 'all'
    'message': None
}

# Same for the ratings enrichment, which runs on its own thread.
ratings_status = {
    'running': False,
    'message': None
}


@app.route('/v2')
def v2_moved():
    """The page lived here while it was being built."""
    return redirect(url_for('v2_search', **request.args), code=301)


V2_SEARCH_TYPES = [
    ('contains', 'Contiene'),
    ('starts_with', 'Inizia con'),
    ('ends_with', 'Finisce con'),
    ('all_words', 'Tutte le parole'),
]

V2_SORTS = [
    ('recent', 'Importati di recente'),
    ('title', 'Titolo'),
    ('rating', 'Voto'),
    ('year', 'Anno ↓'),
    ('year_asc', 'Anno ↑'),
]

V2_PER_PAGE = 30


@app.template_filter('langs')
def v2_langs(value: str) -> str:
    """Render the pipe-separated languages column as a compact release sigil."""
    parts = [p.strip().upper() for p in (value or '').split('|') if p.strip()]
    return '·'.join(parts[:3])


def _ago(value) -> str:
    """Human distance in Italian, coarse on purpose: the sidebar wants a feel."""
    if not value:
        return 'mai'
    try:
        when = datetime.fromisoformat(str(value).replace('Z', ''))
    except ValueError:
        return str(value)
    seconds = (datetime.now() - when).total_seconds()
    if seconds < 3600:
        return f'{int(seconds // 60)} minuti fa'
    if seconds < 86400:
        hours = int(seconds // 3600)
        return '1 ora fa' if hours == 1 else f'{hours} ore fa'
    days = int(seconds // 86400)
    return 'ieri' if days == 1 else f'{days} giorni fa'


def v2_shell() -> dict:
    """Sidebar context: the counts on the nav and the system status at the foot."""
    stats = database.get_stats()
    ratings_stats = database.get_rating_stats()
    last_import = database.get_last_import()
    session = session_store.status()
    _, missing = database.get_titles_with_missing_data(per_page=1)

    rated = ratings_stats['matched']
    session_state = session.get('state', 'missing')
    session_label = {
        'ok': 'Sessione attiva',
        'expiring': 'Sessione in scadenza',
        'expired': 'Sessione scaduta',
        'missing': 'Sessione assente',
    }.get(session_state, 'Sessione sconosciuta')

    return {
        'stats': stats,
        'nav_counts': {
            'sections': stats['total_sections'],
            'review': ratings_stats['low_confidence'],
            'missing': missing,
        },
        'status_lines': [
            {'label': session_label, 'ok': session_state == 'ok',
             'warn': session_state in ('expiring', 'expired')},
            {'label': f"Import: {_ago(last_import.get('completed_at') or last_import.get('started_at')) if last_import else 'mai'}",
             'ok': bool(last_import), 'warn': False},
            {'label': 'Plex non collegato', 'ok': False, 'warn': False},
        ],
        'ratings_progress': {
            'done': rated,
            'total': stats['total_titles'],
        },
        'grafana_logs_url': config.GRAFANA_LOGS_URL,
    }


@app.route('/')
def v2_search():
    """The search page. Renders server-side; the filter panel is a GET form."""
    q = request.args.get('q', '').strip()
    director = request.args.get('director', '').strip()
    search_type = request.args.get('search_type', 'contains').strip()
    sort = (request.args.get('sort') or '').strip()
    page = max(request.args.get('page', 1, type=int) or 1, 1)
    min_rating = request.args.get('min_rating', type=float)
    sections = [s for s in request.args.getlist('section') if s.strip()]
    qualities = [s for s in request.args.getlist('quality') if s.strip()]

    if search_type not in dict(V2_SEARCH_TYPES):
        search_type = 'contains'
    if min_rating is not None and not 0 < min_rating <= 10:
        min_rating = None

    searched = bool(q or director)
    filtered = bool(sections or qualities or min_rating is not None)
    # With nothing typed the page browses the catalogue newest first, so it
    # opens on what the last import brought in rather than on an empty frame.
    browsing = not searched
    if sort not in dict(V2_SORTS):
        sort = 'recent' if browsing else 'title'

    common = dict(query=q, search_type=search_type, director=director or None,
                  min_rating=min_rating, sections=sections, qualities=qualities,
                  allow_empty=browsing)
    groups, total = database.search_titles_grouped(
        page=page, per_page=V2_PER_PAGE, sort=sort, **common)

    if browsing and not filtered:
        facets = database.get_browse_facets()
        total_posts = facets['total_posts']
    else:
        facets = database.get_search_facets(**common)
        total_posts = facets['total_posts']

    params = [('q', q), ('director', director),
              ('search_type', search_type), ('sort', sort)]
    params += [('section', s) for s in sections]
    params += [('quality', s) for s in qualities]
    if min_rating is not None:
        params.append(('min_rating', min_rating))

    def url_without(name, value=None):
        rest = [(k, v) for k, v in params
                if v and not (k == name and (value is None or v == value))]
        return url_for('v2_search', **_multi(rest))

    chips = []
    for s in sections:
        chips.append({'label': s, 'remove_url': url_without('section', s)})
    for s in qualities:
        chips.append({'label': s, 'remove_url': url_without('quality', s)})
    if min_rating is not None:
        chips.append({'label': f'voto ≥ {min_rating:g}',
                      'remove_url': url_without('min_rating')})

    pages = max((total + V2_PER_PAGE - 1) // V2_PER_PAGE, 1)

    return render_template(
        'v2/search.html',
        q=q, director=director, search_type=search_type, sort=sort,
        min_rating=min_rating, page=page, pages=pages, groups=groups,
        total=total, total_posts=total_posts, browsing=browsing,
        sections=sections, qualities=qualities, facets=facets,
        active_chips=chips,
        search_types=V2_SEARCH_TYPES, sorts=V2_SORTS,
        search_type_label=dict(V2_SEARCH_TYPES)[search_type],
        sort_label=dict(V2_SORTS)[sort],
        next_search_type=_cycle(V2_SEARCH_TYPES, search_type),
        next_sort=_cycle(V2_SORTS, sort),
        page_url=lambda n: url_for(
            'v2_search', **_multi(params + [('page', n)])),
        **v2_shell(),
    )


def _cycle(options, current):
    """The value after `current`, wrapping.

    The mode and sort controls are single buttons that step to the next value
    on click: the button carries the next value, so no JavaScript is involved.
    """
    keys = [k for k, _ in options]
    return keys[(keys.index(current) + 1) % len(keys)] if current in keys else keys[0]


def _multi(pairs):
    """Collapse (key, value) pairs into url_for kwargs, keeping repeats as lists."""
    out = {}
    for k, v in pairs:
        if not v:
            continue
        if k in out:
            out[k] = (out[k] if isinstance(out[k], list) else [out[k]]) + [v]
        else:
            out[k] = v
    return out


@app.route('/api/search')
def api_search():
    """
    Search API endpoint.

    Query parameters:
        q: Search query (searches in title, optional if director is provided)
        director: Search by director name (optional)
        section: Filter by section (optional)
        page: Page number (default: 1)
        per_page: Results per page (default: 50)
        search_type: Type of search - "contains", "starts_with", "ends_with", "all_words" (default: "contains")
        min_rating: Minimum rating, 0 to 10 (optional)
        sort: "title" (default), "rating", "year" or "year_asc"
    """
    query = request.args.get('q', '').strip()
    director = request.args.get('director', '').strip() or None
    section = request.args.get('section', '').strip() or None
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search_type = request.args.get('search_type', 'contains').strip()
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    min_rating = request.args.get('min_rating', type=float)
    sort = request.args.get('sort', 'title').strip()

    # Validate parameters - at least one of query or director must be provided
    if not query and not director:
        return jsonify({'error': 'At least one of "q" (title) or "director" parameter is required'}), 400

    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 50

    # Validate search_type
    valid_search_types = ['contains', 'starts_with', 'ends_with', 'all_words']
    if search_type not in valid_search_types:
        search_type = 'contains'

    if sort not in ('title', 'rating', 'year', 'year_asc'):
        sort = 'title'

    if min_rating is not None and not 0 <= min_rating <= 10:
        min_rating = None

    # Perform search
    results, total = database.search_titles(
        query=query,
        section=section,
        page=page,
        per_page=per_page,
        search_type=search_type,
        director=director,
        include_deleted=include_deleted,
        min_rating=min_rating,
        sort=sort
    )

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page

    return jsonify({
        'query': query,
        'director': director,
        'section': section,
        'search_type': search_type,
        'min_rating': min_rating,
        'sort': sort,
        'results': results,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
        }
    })


@app.route('/api/sections')
def api_sections():
    """Get all available sections."""
    sections = database.get_all_sections()
    return jsonify({'sections': sections})


@app.route('/api/stats')
def api_stats():
    """Get database statistics."""
    stats = database.get_stats()
    last_import = database.get_last_import()
    if last_import:
        stats['last_import'] = {
            'started_at': last_import.get('started_at'),
            'completed_at': last_import.get('completed_at'),
            'status': last_import.get('status'),
            'titles_found': last_import.get('titles_found'),
            'titles_inserted': last_import.get('titles_inserted'),
            'titles_updated': last_import.get('titles_updated'),
        }
    return jsonify(stats)


@app.route('/admin')
def admin_page():
    """Render the admin page."""
    return render_template('v2/admin.html', **v2_shell())


@app.route('/sections')
def sections_page():
    """Render the sections page."""
    return render_template('v2/sections.html',
                           sections=database.get_section_counts(),
                           **v2_shell())


@app.route('/sections/<section>')
def section_detail_page(section):
    """Render the section detail page."""
    # Verify section exists
    all_sections = database.get_all_sections()
    if section not in all_sections:
        return "Section not found", 404
    
    stats = database.get_section_stats(section)
    return render_template('section_detail.html', section=section, stats=stats)


@app.route('/sections/missing-data')
def missing_data_page():
    """Titles the parser could not read a director or a year out of."""
    section = request.args.get('section', '').strip() or None
    page = max(request.args.get('page', 1, type=int) or 1, 1)
    include_tv = request.args.get('tv') == '1'

    rows, total = database.get_titles_with_missing_data(
        page=page, per_page=50, section=section, include_tv=include_tv)
    counts = database.get_missing_data_counts(include_tv=include_tv)

    tiles = [
        {'count': counts['both'], 'label': 'senza regista né anno',
         'sub': 'il caso peggiore: niente su cui abbinare'},
        {'count': counts['director_only'], 'label': 'senza regista',
         'sub': "l'anno da solo non basta a distinguere"},
        {'count': counts['year_only'], 'label': 'senza anno',
         'sub': 'il regista regge, ma i remake confondono'},
    ]

    return render_template(
        'v2/missing_data.html',
        rows=rows, total=total, page=page,
        pages=max((total + 49) // 50, 1),
        section=section, sections=database.get_all_sections(),
        tiles=tiles, include_tv=include_tv, tv_count=counts['tv'],
        **v2_shell())


@app.route('/api/pages', methods=['GET'])
def api_pages_get():
    """Get the contents of pages.txt."""
    try:
        if not os.path.exists(config.PAGES_FILE):
            return jsonify({'content': '', 'error': 'File not found'})
        
        with open(config.PAGES_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': f'Error reading pages.txt: {str(e)}'}), 500


@app.route('/api/pages', methods=['POST'])
def api_pages_post():
    """Update the contents of pages.txt."""
    try:
        data = request.get_json()
        if not data or 'content' not in data:
            return jsonify({'error': 'Missing "content" field'}), 400
        
        content = data['content']
        
        # Validate format by trying to parse it
        try:
            # Create a temporary file to validate
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            
            # Try to parse it
            pages = parser.parse_pages_file(tmp_path)
            os.unlink(tmp_path)
            
            # If parsing succeeds, save the file
            with open(config.PAGES_FILE, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return jsonify({
                'success': True,
                'message': f'File saved successfully. {len(pages)} pages found.'
            })
        except Exception as e:
            return jsonify({'error': f'Invalid format: {str(e)}'}), 400
    
    except Exception as e:
        return jsonify({'error': f'Error saving pages.txt: {str(e)}'}), 500


@app.route('/api/session', methods=['GET'])
def api_session_get():
    """Report the state of the stored browser session."""
    info = session_store.status()
    info['relay_configured'] = bool(config.SESSION_TOKEN)
    return jsonify(info)


@app.route('/api/session', methods=['POST'])
def api_session_post():
    """
    Accept forum cookies captured by the browser extension.

    The cookies are checked against a real forum page before being stored, so
    a guest session can never overwrite a working one.
    """
    if not config.SESSION_TOKEN:
        return jsonify({'error': 'Session relay is not configured'}), 503

    # Compared as bytes: compare_digest refuses non-ASCII str, and the header is
    # whatever the caller sent.
    token = request.headers.get('X-Session-Token', '').encode('utf-8', 'replace')
    if not hmac.compare_digest(token, config.SESSION_TOKEN.encode('utf-8')):
        web_logger.warning(f"Rejected session push from {request.remote_addr}: bad token")
        return jsonify({'error': 'Invalid token'}), 401

    data = request.get_json(silent=True) or {}
    cookies = session_store.normalize_cookies(data.get('cookies'))
    if not cookies:
        return jsonify({'error': 'Missing "cookies" field'}), 400

    # Without a reference page there is no way to tell a good session from a
    # guest one, and rejecting the push would blame the cookies for it.
    if not parser.parse_pages_file(config.PAGES_FILE):
        return jsonify({'error': 'No pages configured, cannot verify a session'}), 503

    # A stored session that still works is worth more than the pushed one: the
    # forum hands out a single autologin key per device, and replacing a session
    # the scraper owns with the browser's copy makes the two fight over it.
    keeper = scraper.DDUnlimitedScraper()
    if keeper.apply_session() and keeper.verify_session():
        session_store.refresh(keeper.current_cookies())
        return jsonify({'valid': True, 'kept': True,
                        'message': 'Stored session still works, kept it'})

    user_agent = data.get('userAgent')
    probe = scraper.DDUnlimitedScraper()
    probe.set_cookies(cookies)
    if user_agent:
        probe.session.headers['User-Agent'] = user_agent

    if not probe.verify_session():
        web_logger.info("Session push rejected: cookies do not reach forum content")
        return jsonify({
            'valid': False,
            'error': 'These cookies do not reach forum content'
        }), 422

    # Keep the jar as it stands after the check: verifying can itself rotate the
    # session id and the autologin key, and the pushed values are stale by then.
    record = session_store.save(
        {**cookies, **probe.current_cookies()},
        expires_at=data.get('expiresAt') or session_store.earliest_expiry(data.get('cookies')),
        source=data.get('source', 'browser-extension'),
        user_agent=user_agent
    )
    web_logger.info(f"Stored browser session from {request.remote_addr} "
                    f"({len(cookies)} cookies)")

    return jsonify({
        'valid': True,
        'updated_at': record['updated_at'],
        'expires_at': record['expires_at'],
    })


@app.route('/api/session', methods=['DELETE'])
def api_session_delete():
    """Forget the stored browser session."""
    session_store.clear()
    return jsonify({'success': True})


@app.route('/api/schedule', methods=['GET'])
def api_schedule_get():
    """Get the automatic import schedule."""
    return jsonify({
        **database.get_schedule(),
        'last_import': database.get_last_import(),
        'last_successful_import': database.get_last_import(successful_only=True),
    })


@app.route('/api/schedule', methods=['POST'])
def api_schedule_post():
    """Update the automatic import schedule."""
    data = request.get_json(silent=True) or {}

    ranges = {
        'interval_days': (1, 365, 'scrape_interval_days'),
        'hour': (0, 23, 'scrape_hour'),
        'minute': (0, 59, 'scrape_minute'),
    }

    for field, (low, high, key) in ranges.items():
        if field not in data:
            continue
        try:
            value = int(data[field])
        except (TypeError, ValueError):
            return jsonify({'error': f'"{field}" must be a number'}), 400
        if not low <= value <= high:
            return jsonify({'error': f'"{field}" must be between {low} and {high}'}), 400
        database.set_setting(key, value)

    if 'enabled' in data:
        database.set_setting('scrape_enabled', 'true' if data['enabled'] else 'false')

    return jsonify({'success': True})


@app.route('/api/import/single', methods=['POST'])
def api_import_single():
    """Import a single page."""
    global import_status
    
    if import_status['running']:
        return jsonify({'error': 'An import is already running'}), 409
    
    try:
        data = request.get_json()
        if not data or 'url' not in data or 'section' not in data:
            return jsonify({'error': 'Missing "url" or "section" field'}), 400
        
        url = data['url'].strip()
        section = data['section'].strip()
        
        if not url or not section:
            return jsonify({'error': 'URL and section cannot be empty'}), 400
        
        # Start import in background thread
        import_status['running'] = True
        import_status['type'] = 'single'
        import_status['message'] = f'Importing {section} - {url}'
        
        def run_single_import():
            global import_status
            import logging
            # Use the scraper logger which is already configured
            logger = logging.getLogger('scraper')
            
            def update_status(msg):
                """Update status and log"""
                import_status['message'] = msg
                logger.info(f"Status update: {msg}")
            
            try:
                logger.info(f"Thread started for single import: {section} - {url}")
                scraper_instance = scraper.DDUnlimitedScraper()
                found, inserted, updated = scraper_instance.scrape_single_page(
                    url, section, status_callback=update_status
                )
                message = f'Completato: {found} titoli trovati, {inserted} inseriti, {updated} aggiornati'
                logger.info(f"Single import completed: {message}")
                import_status['message'] = message
            except Exception as e:
                error_msg = f'Errore: {str(e)}'
                logger.error(f"Error in single import thread: {error_msg}", exc_info=True)
                import_status['message'] = error_msg
            finally:
                import_status['running'] = False
                logger.info("Single import thread finished")
        
        thread = threading.Thread(target=run_single_import, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Import started',
            'url': url,
            'section': section
        })
    
    except Exception as e:
        import_status['running'] = False
        return jsonify({'error': f'Error starting import: {str(e)}'}), 500


@app.route('/api/import/all', methods=['POST'])
def api_import_all():
    """Import all pages from pages.txt."""
    global import_status
    
    if import_status['running']:
        return jsonify({'error': 'An import is already running'}), 409
    
    try:
        # Start import in background thread
        import_status['running'] = True
        import_status['type'] = 'all'
        import_status['message'] = 'Starting full import...'
        
        def run_full_import():
            global import_status
            import logging
            logger = logging.getLogger('scraper')
            
            def update_status(msg):
                """Update status and log"""
                import_status['message'] = msg
                logger.info(f"Status update: {msg}")
            
            try:
                scraper_instance = scraper.DDUnlimitedScraper()
                if scraper_instance.run(status_callback=update_status):
                    import_status['message'] = 'Importazione completa terminata con successo'
                else:
                    import_status['message'] = "Importazione interrotta: vedi scraper.log"
            except Exception as e:
                error_msg = f'Errore: {str(e)}'
                logger.error(f"Error in full import thread: {error_msg}", exc_info=True)
                import_status['message'] = error_msg
            finally:
                import_status['running'] = False
        
        thread = threading.Thread(target=run_full_import, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Full import started'
        })
    
    except Exception as e:
        import_status['running'] = False
        return jsonify({'error': f'Error starting import: {str(e)}'}), 500


@app.route('/api/import/status')
def api_import_status():
    """
    Get the current import status.
    If import is not running and there's a message, it will be cleared after being read once.
    """
    global import_status
    status = import_status.copy()
    
    # If import is not running and there's a completed/error message,
    # we'll keep it for a while but mark it as "shown" to avoid flickering
    # The frontend will handle hiding it after a timeout
    return jsonify(status)


@app.route('/api/sections/<section>')
def api_section_titles(section):
    """
    Get titles for a specific section with optional filters.
    
    Query parameters:
        page: Page number (default: 1)
        per_page: Results per page (default: 50)
        year: Filter by year (optional)
        first_letter: Filter by first letter (optional)
        quality: Filter by quality/resolution (optional)
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    year = request.args.get('year', type=int)
    first_letter = request.args.get('first_letter', '').strip() or None
    quality = request.args.get('quality', '').strip() or None
    
    # Validate parameters
    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 50
    
    # Perform query
    results, total, filters_info = database.get_section_titles(
        section=section,
        page=page,
        per_page=per_page,
        year=year,
        first_letter=first_letter,
        quality=quality
    )
    
    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    
    return jsonify({
        'section': section,
        'results': results,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
        },
        'filters': {
            'year': year,
            'first_letter': first_letter,
            'quality': quality,
            'available_years': filters_info['available_years'],
            'available_letters': filters_info['available_letters'],
            'available_qualities': filters_info['available_qualities']
        }
    })


@app.route('/api/missing-data')
def api_missing_data():
    """
    Get titles where director or year is NULL.
    
    Query parameters:
        page: Page number (default: 1)
        per_page: Results per page (default: 50)
        section: Filter by section (optional)
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    section = request.args.get('section', '').strip() or None
    
    # Validate parameters
    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 50
    
    # Perform query
    results, total = database.get_titles_with_missing_data(
        page=page,
        per_page=per_page,
        section=section
    )
    
    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    
    return jsonify({
        'results': results,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
        },
        'filters': {
            'section': section
        }
    })


V2_REVIEW_TABS = [
    ('low_confidence', 'Da rivedere'),
    ('unmatched', 'Senza match'),
    ('rejected', 'Scartati'),
    ('manual', 'Corretti a mano'),
]

V2_REVIEW_PER_PAGE = 40


def _directors_clash(ours: str, theirs: str) -> bool:
    """True when the two sides name different people.

    Same normalisation the matcher uses for its director bonus: last token,
    lowercased and unaccented. A signal, not a verdict — it misreads names
    that are not latin and films credited to more than one director.
    """
    if not ours or not theirs:
        return False
    mine = ratings._person_key(ours)
    others = {ratings._person_key(name) for name in theirs.split(',')}
    return bool(mine) and bool(others) and mine not in others


@app.route('/ratings')
def ratings_page():
    """The review queue: forum on the left, TMDB on the right."""
    status = request.args.get('status', 'low_confidence').strip()
    if status not in dict(V2_REVIEW_TABS):
        status = 'low_confidence'
    page = max(request.args.get('page', 1, type=int) or 1, 1)

    rows, total = database.get_rating_matches(
        page=page, per_page=V2_REVIEW_PER_PAGE, status=status)
    for row in rows:
        row['clash'] = _directors_clash(row.get('director'),
                                        row.get('matched_director'))

    stats = database.get_rating_stats()
    counts = {'low_confidence': stats['low_confidence'],
              'unmatched': stats['unmatched'],
              'rejected': stats['rejected'],
              'manual': stats['matched']}

    return render_template(
        'v2/ratings.html',
        rows=rows, status=status, page=page,
        pages=max((total + V2_REVIEW_PER_PAGE - 1) // V2_REVIEW_PER_PAGE, 1),
        tabs=[(k, label, counts.get(k, 0)) for k, label in V2_REVIEW_TABS],
        missing_directors=database.count_ratings_missing_director(status),
        article_count=(database.count_low_confidence_with_trailing_article()
                       if status == 'low_confidence' else 0),
        **v2_shell())


@app.route('/api/ratings/status')
def api_ratings_status():
    """Configuration, progress and counts of the rating enrichment."""
    return jsonify({
        'running': ratings_status['running'],
        'message': ratings_status['message'],
        'enabled': config.RATINGS_ENABLED,
        'tmdb_key': bool(config.TMDB_API_KEY),
        'omdb_key': bool(config.OMDB_API_KEY),
        'omdb_daily_limit': config.OMDB_DAILY_LIMIT,
        'stats': database.get_rating_stats(),
    })


@app.route('/api/ratings/enrich', methods=['POST'])
def api_ratings_enrich():
    """Start an enrichment pass in the background."""
    global ratings_status

    if ratings_status['running']:
        return jsonify({'error': 'Un arricchimento e\' gia\' in corso'}), 409
    if not config.TMDB_API_KEY:
        return jsonify({'error': 'TMDB_API_KEY non configurata'}), 400

    data = request.get_json(silent=True) or {}
    limit = data.get('limit') or config.RATING_MAX_PER_RUN
    retry_unmatched = bool(data.get('retry_unmatched'))

    ratings_status['running'] = True
    ratings_status['message'] = 'Avvio arricchimento...'

    def run_enrichment():
        global ratings_status

        def update_status(msg):
            ratings_status['message'] = msg

        try:
            result = ratings.run_enrichment(
                limit=int(limit), retry_unmatched=retry_unmatched,
                status_callback=update_status
            )
            tmdb = result.get('tmdb', {})
            imdb = result.get('imdb', {})
            ratings_status['message'] = (
                f"Completato: {tmdb.get('matched', 0)} agganciati, "
                f"{tmdb.get('low_confidence', 0)} da rivedere, "
                f"{tmdb.get('unmatched', 0)} senza match, "
                f"{imdb.get('with_rating', 0)} voti IMDb"
            )
        except Exception as e:
            web_logger.error(f"Errore nell'arricchimento voti: {e}", exc_info=True)
            ratings_status['message'] = f'Errore: {e}'
        finally:
            ratings_status['running'] = False

    threading.Thread(target=run_enrichment, daemon=True).start()
    return jsonify({'success': True, 'message': 'Arricchimento avviato'})


@app.route('/api/ratings/review')
def api_ratings_review():
    """
    List matches to eyeball.

    Query parameters:
        status: low_confidence (default), unmatched, rejected, matched, manual, pending
        section: Filter by section (optional)
        page, per_page: Pagination
    """
    status = request.args.get('status', 'low_confidence').strip()
    section = request.args.get('section', '').strip() or None
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    valid = ('low_confidence', 'unmatched', 'rejected', 'matched', 'manual', 'pending')
    if status not in valid:
        status = 'low_confidence'
    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 50

    results, total = database.get_rating_matches(
        page=page, per_page=per_page, status=status, section=section
    )
    total_pages = (total + per_page - 1) // per_page

    return jsonify({
        'status': status,
        'results': results,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
        },
    })


@app.route('/api/ratings/match', methods=['POST'])
def api_ratings_match():
    """Pin a title to a TMDB entry given its url or id."""
    data = request.get_json(silent=True) or {}
    title_id = data.get('title_id')
    reference = str(data.get('reference', '')).strip()

    if not title_id or not reference:
        return jsonify({'error': 'Servono "title_id" e "reference"'}), 400
    if not config.TMDB_API_KEY:
        return jsonify({'error': 'TMDB_API_KEY non configurata'}), 400

    parsed = ratings.parse_tmdb_reference(reference)
    if not parsed:
        return jsonify({'error': 'Riferimento TMDB non riconosciuto'}), 400

    media_type, tmdb_id = parsed
    try:
        match = ratings.match_by_tmdb_id(media_type, tmdb_id)
    except ratings.RatingsError as e:
        return jsonify({'error': str(e)}), 502

    if not match:
        return jsonify({'error': f'Nessun {media_type} con id {tmdb_id} su TMDB'}), 404

    database.save_rating(int(title_id), 'manual', **match)
    if match.get('imdb_id'):
        ratings.refresh_imdb_vote(int(title_id), match['imdb_id'])

    return jsonify({'success': True, 'match': match})


@app.route('/api/ratings/confirm', methods=['POST'])
def api_ratings_confirm():
    """Accept the match already on file, without asking TMDB again."""
    data = request.get_json(silent=True) or {}
    title_id = data.get('title_id')
    if not title_id:
        return jsonify({'error': 'Serve "title_id"'}), 400

    if not database.confirm_rating(int(title_id)):
        return jsonify({'error': 'Nessun abbinamento da confermare'}), 404
    return jsonify({'success': True})


@app.route('/api/ratings/backfill-directors', methods=['POST'])
def api_ratings_backfill_directors():
    """Fill matched_director on matches made before the column existed."""
    if not config.TMDB_API_KEY:
        return jsonify({'error': 'TMDB_API_KEY non configurata'}), 400

    data = request.get_json(silent=True) or {}
    status = str(data.get('status', 'low_confidence')).strip()
    limit = min(max(int(data.get('limit', 400) or 400), 1), 2000)

    try:
        filled, seen = ratings.backfill_directors(status=status, limit=limit)
    except ratings.RatingsError as e:
        return jsonify({'error': str(e)}), 502

    return jsonify({'success': True, 'filled': filled, 'seen': seen})


@app.route('/api/ratings/rematch-article', methods=['POST'])
def api_ratings_rematch_article():
    """Score again the titles that moved the article to the end."""
    if not config.TMDB_API_KEY:
        return jsonify({'error': 'TMDB_API_KEY non configurata'}), 400

    data = request.get_json(silent=True) or {}
    limit = min(max(int(data.get('limit', 500) or 500), 1), 3000)
    try:
        counts = ratings.rematch_trailing_article(limit=limit)
    except ratings.RatingsError as e:
        return jsonify({'error': str(e)}), 502
    return jsonify({'success': True, **counts})


@app.route('/api/ratings/reject', methods=['POST'])
def api_ratings_reject():
    """Throw away a wrong match and stop proposing it."""
    data = request.get_json(silent=True) or {}
    title_id = data.get('title_id')
    if not title_id:
        return jsonify({'error': 'Serve "title_id"'}), 400

    database.reject_rating(int(title_id))
    return jsonify({'success': True})


@app.route('/api/ratings/reset', methods=['POST'])
def api_ratings_reset():
    """Put a title back in the queue for the next pass."""
    data = request.get_json(silent=True) or {}
    title_id = data.get('title_id')
    if not title_id:
        return jsonify({'error': 'Serve "title_id"'}), 400

    database.reset_rating(int(title_id))
    return jsonify({'success': True})


def main():
    """Main entry point."""
    # Initialize database
    database.init_db()
    database.migrate_refresh_policy()
    
    # Migrate existing titles (populate director, year, title_first_letter)
    # This is safe to run multiple times - it only updates NULL values
    try:
        updated, _ = database.migrate_existing_titles()
        if updated > 0:
            web_logger.info(f"Migrated {updated} titles with director/year/letter data")
            print(f"Migrated {updated} titles with director/year/letter data")
    except Exception as e:
        web_logger.warning(f"Migration warning: {e}")
        print(f"Migration warning: {e}")

    web_logger.info(f"Starting server at http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    print(f"Starting server at http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    print("Web server logs: logs/web.log")
    print("Scraper logs: logs/scraper.log")
    print("Scheduler logs: logs/scheduler.log")
    
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
        request_handler=CustomRequestHandler
    )


if __name__ == "__main__":
    main()
