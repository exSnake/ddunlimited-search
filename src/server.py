"""Flask web server for DDUnlimited Search."""

import logging
import os
import sys
import threading
from flask import Flask, jsonify, render_template, request
from werkzeug.serving import WSGIRequestHandler

import config
import database
import parser
import scraper

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


@app.route('/')
def index():
    """Render the main search page."""
    sections = database.get_all_sections()
    stats = database.get_stats()
    return render_template('index.html', sections=sections, stats=stats)


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
    """
    query = request.args.get('q', '').strip()
    director = request.args.get('director', '').strip() or None
    section = request.args.get('section', '').strip() or None
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search_type = request.args.get('search_type', 'contains').strip()
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'

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

    # Perform search
    results, total = database.search_titles(
        query=query,
        section=section,
        page=page,
        per_page=per_page,
        search_type=search_type,
        director=director,
        include_deleted=include_deleted
    )

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page

    return jsonify({
        'query': query,
        'director': director,
        'section': section,
        'search_type': search_type,
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
                scraper_instance.run(status_callback=update_status)
                import_status['message'] = 'Importazione completa terminata con successo'
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


def main():
    """Main entry point."""
    # Initialize database
    database.init_db()
    
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
