"""Flask web server for DDUnlimited Search."""

import hmac
import logging
import os
import sys
import threading
from flask import Flask, jsonify, render_template, request, url_for
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

# Console handler (optional, can be removed if you don't want web logs on console)
web_console_handler = logging.StreamHandler(sys.stdout)
web_console_handler.setLevel(logging.WARNING)  # Only warnings and errors on console
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
        if code != 200:  # Only log non-200 responses to console
            super().log_request(code, size)
        # Always log to file
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


@app.route('/')
def index():
    """Render the main search page."""
    sections = database.get_all_sections()
    stats = database.get_stats()
    return render_template('index.html', sections=sections, stats=stats)


V2_SEARCH_TYPES = [
    ('contains', 'Contiene'),
    ('starts_with', 'Inizia con'),
    ('ends_with', 'Finisce con'),
    ('all_words', 'Tutte le parole'),
]

V2_SORTS = [
    ('title', 'Titolo'),
    ('rating', 'Voto'),
    ('year', 'Anno, dal più recente'),
    ('year_asc', 'Anno, dal più vecchio'),
]

V2_PER_PAGE = 30


@app.template_filter('langs')
def v2_langs(value: str) -> str:
    """Render the pipe-separated languages column as a compact release sigil."""
    parts = [p.strip().upper() for p in (value or '').split('|') if p.strip()]
    return '·'.join(parts[:3])


@app.route('/v2')
def v2_search():
    """Search page, v2. Renders server-side; the filter panel is a GET form."""
    q = request.args.get('q', '').strip()
    director = request.args.get('director', '').strip()
    search_type = request.args.get('search_type', 'contains').strip()
    sort = request.args.get('sort', 'title').strip()
    page = max(request.args.get('page', 1, type=int) or 1, 1)
    min_rating = request.args.get('min_rating', type=float)
    sections = [s for s in request.args.getlist('section') if s.strip()]
    qualities = [s for s in request.args.getlist('quality') if s.strip()]

    if search_type not in dict(V2_SEARCH_TYPES):
        search_type = 'contains'
    if sort not in dict(V2_SORTS):
        sort = 'title'
    if min_rating is not None and not 0 < min_rating <= 10:
        min_rating = None

    searched = bool(q or director)
    groups, total, total_posts, facets = [], 0, 0, {'sections': [], 'qualities': []}
    if searched:
        common = dict(query=q, search_type=search_type, director=director or None,
                      min_rating=min_rating, sections=sections, qualities=qualities)
        groups, total = database.search_titles_grouped(
            page=page, per_page=V2_PER_PAGE, sort=sort, **common)
        total_posts = sum(len(g['posts']) for g in groups)
        facets = database.get_search_facets(**common)

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
    if search_type != 'contains':
        chips.append({'label': dict(V2_SEARCH_TYPES)[search_type].lower(),
                      'remove_url': url_without('search_type')})
    if sort != 'title':
        chips.append({'label': dict(V2_SORTS)[sort].lower(),
                      'remove_url': url_without('sort')})

    pages = max((total + V2_PER_PAGE - 1) // V2_PER_PAGE, 1)

    return render_template(
        'v2/search.html',
        q=q, director=director, search_type=search_type, sort=sort,
        min_rating=min_rating, page=page, pages=pages, groups=groups,
        total=total, total_posts=total_posts, searched=searched,
        sections=sections, qualities=qualities, facets=facets,
        stats=database.get_stats(), search_types=V2_SEARCH_TYPES,
        sorts=V2_SORTS, active_chips=chips,
        page_url=lambda n: url_for(
            'v2_search', **_multi(params + [('page', n)])),
    )


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


@app.route('/logs')
def logs_page():
    """Render the logs page."""
    return render_template('logs.html')


@app.route('/admin')
def admin_page():
    """Render the admin page."""
    return render_template('admin.html')


@app.route('/sections')
def sections_page():
    """Render the sections page."""
    sections = database.get_all_sections()
    return render_template('sections.html', sections=sections)


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
    """Render the page for titles with missing director/year data."""
    sections = database.get_all_sections()
    return render_template('missing_data.html', sections=sections)


@app.route('/api/logs')
def api_logs():
    """
    Get log file contents.
    
    Query parameters:
        file: 'scraper', 'scheduler', or 'web' (default: 'scraper')
        lines: Number of lines to return from the end (default: 500)
    """
    log_file = request.args.get('file', 'scraper').strip()
    lines = request.args.get('lines', 500, type=int)
    offset = request.args.get('offset', 0, type=int)  # lines to skip from the end

    if log_file not in ['scraper', 'scheduler', 'web']:
        return jsonify({'error': 'Invalid log file. Use "scraper", "scheduler", or "web"'}), 400

    log_path = f'logs/{log_file}.log'

    try:
        if not os.path.exists(log_path):
            return jsonify({'content': '', 'file': log_file, 'total_lines': 0})

        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        total = len(all_lines)
        # offset=0 → last N lines; offset=N → skip last N, take previous N
        end = total - offset if offset < total else 0
        start = max(0, end - lines)
        content_lines = all_lines[start:end]
        content = ''.join(content_lines)

        return jsonify({
            'content': content,
            'file': log_file,
            'total_lines': total,
            'start_line': start + 1,
            'end_line': end,
        })
    except Exception as e:
        return jsonify({'error': f'Error reading log file: {str(e)}'}), 500


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


@app.route('/ratings')
def ratings_page():
    """Render the page to review the matches against TMDB."""
    sections = database.get_all_sections()
    return render_template('ratings.html', sections=sections)


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
