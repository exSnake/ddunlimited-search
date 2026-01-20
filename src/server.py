"""Flask web server for DDUnlimited Search."""

from flask import Flask, jsonify, render_template, request

import config
import database

app = Flask(__name__)


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
        q: Search query (required)
        section: Filter by section (optional)
        page: Page number (default: 1)
        per_page: Results per page (default: 50)
        search_type: Type of search - "contains", "starts_with", "ends_with", "all_words" (default: "contains")
    """
    query = request.args.get('q', '').strip()
    section = request.args.get('section', '').strip() or None
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search_type = request.args.get('search_type', 'contains').strip()

    # Validate parameters
    if not query:
        return jsonify({'error': 'Query parameter "q" is required'}), 400

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
        search_type=search_type
    )

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page

    return jsonify({
        'query': query,
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


def main():
    """Main entry point."""
    # Initialize database
    database.init_db()

    print(f"Starting server at http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG
    )


if __name__ == "__main__":
    main()
