"""Database module for DDUnlimited Search."""

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, Tuple

import config


def get_connection() -> sqlite3.Connection:
    """Create a database connection."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def extract_director_and_year(title: str) -> Tuple[Optional[str], Optional[int], str]:
    """
    Extract director and year from title.
    Looks for patterns:
    - (Director, YYYY) or (Director, YYYY-YYYY)
    - (YYYY, Director) - inverted pattern
    - (Director YYYY) - without comma
    - (YYYY) - just year
    
    Returns:
        Tuple of (director, year, first_letter)
        - director: Director name or None
        - year: Year (first year if range) or None
        - first_letter: First letter of the title (normalized)
    """
    # Get first letter (normalize: remove leading special chars, get first alphanumeric)
    first_letter = None
    for char in title:
        if char.isalnum():
            first_letter = char.upper()
            break
    
    if not first_letter:
        first_letter = "#"
    
    # Try to extract director and year from parentheses
    # Pattern 1: (Director, YYYY) or (Director, YYYY-YYYY) - standard pattern
    # Allow spaces before/after comma and inside parentheses
    match = re.search(r'\(\s*([^,)]+?)\s*,\s*(\d{4})(?:-\d{4})?\s*\)', title)
    if match:
        part1 = match.group(1).strip()
        year_str = match.group(2)
        try:
            year = int(year_str)
            # Check if part1 is a year (4 digits) - if so, it's inverted pattern
            if re.match(r'^\d{4}$', part1):
                # This is actually pattern (YYYY, Director) - we'll catch it in next pattern
                pass
            else:
                # Normal pattern: (Director, YYYY)
                return part1, year, first_letter
        except ValueError:
            pass
    
    # Pattern 2: (YYYY, Director) - inverted pattern with comma
    match = re.search(r'\(\s*(\d{4})\s*,\s*([^,)]+?)\s*\)', title)
    if match:
        year_str = match.group(1)
        director = match.group(2).strip()
        try:
            year = int(year_str)
            return director, year, first_letter
        except ValueError:
            pass
    
    # Pattern 3: (Director YYYY) - without comma, year at end
    match = re.search(r'\(\s*([^,)]+?)\s+(\d{4})\s*\)', title)
    if match:
        director = match.group(1).strip()
        year_str = match.group(2)
        try:
            year = int(year_str)
            return director, year, first_letter
        except ValueError:
            pass
    
    # Pattern 4: (YYYY Director) - without comma, year at start
    match = re.search(r'\(\s*(\d{4})\s+([^,)]+?)\s*\)', title)
    if match:
        year_str = match.group(1)
        director = match.group(2).strip()
        try:
            year = int(year_str)
            return director, year, first_letter
        except ValueError:
            pass
    
    # Pattern 5: Just year: (YYYY)
    match = re.search(r'\(\s*(\d{4})\s*\)', title)
    if match:
        year_str = match.group(1)
        try:
            year = int(year_str)
            return None, year, first_letter
        except ValueError:
            pass
    
    return None, None, first_letter


def init_db():
    """Initialize the database schema."""
    # Create data directory if it doesn't exist
    import os
    db_dir = os.path.dirname(config.DATABASE_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS titles (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                section TEXT,
                metadata TEXT,
                quality TEXT,
                director TEXT,
                year INTEGER,
                title_first_letter TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Migrate existing database: add new columns if they don't exist
        cursor.execute("PRAGMA table_info(titles)")
        columns = [row[1] for row in cursor.fetchall()]
        
        columns_added = False
        if 'director' not in columns:
            cursor.execute("ALTER TABLE titles ADD COLUMN director TEXT")
            columns_added = True
        if 'year' not in columns:
            cursor.execute("ALTER TABLE titles ADD COLUMN year INTEGER")
            columns_added = True
        if 'title_first_letter' not in columns:
            cursor.execute("ALTER TABLE titles ADD COLUMN title_first_letter TEXT")
            columns_added = True
        if 'languages' not in columns:
            cursor.execute("ALTER TABLE titles ADD COLUMN languages TEXT")
            columns_added = True
        if 'deleted_at' not in columns:
            cursor.execute("ALTER TABLE titles ADD COLUMN deleted_at TIMESTAMP")
            columns_added = True
        if 'raw_info' not in columns:
            cursor.execute("ALTER TABLE titles ADD COLUMN raw_info TEXT")
            columns_added = True
        if 'details_scraped_at' not in columns:
            cursor.execute("ALTER TABLE titles ADD COLUMN details_scraped_at TIMESTAMP")
            columns_added = True
        if 'details_next_refresh_at' not in columns:
            cursor.execute("ALTER TABLE titles ADD COLUMN details_next_refresh_at TIMESTAMP")
            columns_added = True
        if 'post_created_at' not in columns:
            cursor.execute("ALTER TABLE titles ADD COLUMN post_created_at TIMESTAMP")
            columns_added = True

        # Commit column additions before creating indexes
        if columns_added:
            conn.commit()
        
        # Create indexes (only after columns exist)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_title ON titles(title)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_section ON titles(section)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_director ON titles(director)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_year ON titles(year)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_title_first_letter ON titles(title_first_letter)")
        
        # Table for tracking import history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS import_history (
                id INTEGER PRIMARY KEY,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                titles_found INTEGER DEFAULT 0,
                titles_inserted INTEGER DEFAULT 0,
                titles_updated INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running'
            )
        """)

        # Runtime settings editable from the admin UI. Web and scheduler run in
        # separate containers and only share the database, so it lives here.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP
            )
        """)

        # Ratings pulled from TMDB (and IMDb through OMDb). Kept apart from
        # titles: a row here means the title was looked up, whatever the outcome.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS title_ratings (
                title_id INTEGER PRIMARY KEY,
                media_type TEXT,
                tmdb_id INTEGER,
                imdb_id TEXT,
                tmdb_rating REAL,
                tmdb_votes INTEGER,
                imdb_rating REAL,
                imdb_votes INTEGER,
                poster_path TEXT,
                matched_title TEXT,
                matched_year INTEGER,
                confidence REAL,
                match_status TEXT NOT NULL DEFAULT 'unmatched',
                matched_at TIMESTAMP,
                imdb_checked_at TIMESTAMP,
                FOREIGN KEY (title_id) REFERENCES titles(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating_status ON title_ratings(match_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating_imdb_id ON title_ratings(imdb_id)")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rating_score
            ON title_ratings(COALESCE(imdb_rating, tmdb_rating))
        """)


def insert_title(title: str, url: str, section: str, metadata: str = None, quality: str = None,
                 languages: str = None, raw_info: str = None,
                 details_scraped_at: datetime = None, details_next_refresh_at: datetime = None,
                 post_created_at: datetime = None, update_details: bool = True) -> str:
    """Insert or update a title.

    Returns 'inserted', 'updated' or 'unchanged'. The content update is guarded
    so a row is only written when a field actually differs, which is what makes
    the reported counts mean something.

    Args:
        update_details: False when the details were not fetched, so the detail
                        columns and the revisit bookkeeping are left alone.
    """
    director, year, first_letter = extract_director_and_year(title)

    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO titles (title, url, section, metadata, quality, director, year,
                                    title_first_letter, languages, raw_info,
                                    details_scraped_at, details_next_refresh_at, post_created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, url, section, metadata, quality, director, year, first_letter,
                 languages, raw_info, details_scraped_at, details_next_refresh_at,
                 post_created_at)
            )
            return 'inserted'
        except sqlite3.IntegrityError:
            pass

        # A retitled post is a different film as far as the catalogues go, so its
        # match starts over. One corrected by hand is left alone.
        cursor.execute(
            """
            DELETE FROM title_ratings
            WHERE match_status != 'manual'
              AND title_id IN (SELECT id FROM titles WHERE url = ? AND title IS NOT ?)
            """,
            (url, title)
        )

        if update_details:
            cursor.execute(
                """
                UPDATE titles SET title = ?, section = ?, metadata = ?, quality = ?,
                                 director = ?, year = ?, title_first_letter = ?,
                                 languages = ?, raw_info = ?,
                                 post_created_at = COALESCE(post_created_at, ?)
                WHERE url = ?
                  AND (title IS NOT ? OR section IS NOT ? OR metadata IS NOT ?
                       OR quality IS NOT ? OR languages IS NOT ? OR raw_info IS NOT ?)
                """,
                (title, section, metadata, quality, director, year, first_letter,
                 languages, raw_info, post_created_at, url,
                 title, section, metadata, quality, languages, raw_info)
            )
            changed = cursor.rowcount > 0

            # Bookkeeping is written even when nothing changed, otherwise the
            # post would be fetched again on every run.
            cursor.execute(
                """
                UPDATE titles SET details_scraped_at = ?, details_next_refresh_at = ?
                WHERE url = ?
                """,
                (details_scraped_at, details_next_refresh_at, url)
            )
        else:
            cursor.execute(
                """
                UPDATE titles SET title = ?, section = ?, metadata = ?, quality = ?,
                                 director = ?, year = ?, title_first_letter = ?
                WHERE url = ?
                  AND (title IS NOT ? OR section IS NOT ? OR metadata IS NOT ? OR quality IS NOT ?)
                """,
                (title, section, metadata, quality, director, year, first_letter, url,
                 title, section, metadata, quality)
            )
            changed = cursor.rowcount > 0

        return 'updated' if changed else 'unchanged'


def get_existing_details(urls: list) -> dict:
    """
    For a list of URLs, return existing detail fields from the DB.
    Returns a dict keyed by URL: {languages, raw_info, details_scraped_at, deleted_at}.
    Only includes rows that actually exist in the DB.
    """
    if not urls:
        return {}
    placeholders = ','.join('?' * len(urls))
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT url, languages, raw_info, deleted_at,
                   details_scraped_at, details_next_refresh_at, post_created_at
            FROM titles
            WHERE url IN ({placeholders})
            """,
            urls
        )
        return {
            row['url']: {
                'languages': row['languages'],
                'raw_info': row['raw_info'],
                'deleted_at': row['deleted_at'],
                'details_scraped_at': row['details_scraped_at'],
                'details_next_refresh_at': row['details_next_refresh_at'],
                'post_created_at': row['post_created_at'],
            }
            for row in cursor.fetchall()
        }


def delete_title(url: str) -> bool:
    """Soft-delete a title by URL (sets deleted_at). Returns True if found and marked."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE titles SET deleted_at = CURRENT_TIMESTAMP WHERE url = ? AND deleted_at IS NULL",
            (url,)
        )
        return cursor.rowcount > 0


def _build_search_filter(
    query: str,
    section: Optional[str],
    search_type: str,
    director: Optional[str],
    include_deleted: bool,
    min_rating: Optional[float],
    sections: Optional[list] = None,
    qualities: Optional[list] = None,
) -> tuple[str, list]:
    """Build the shared FROM/WHERE clause for the search queries.

    Returns (base_query, params). A base query of "FROM titles WHERE 1=0" means
    no search criteria were given and the caller should return nothing.
    """
    title_conditions = []
    params = []

    if query:
        if search_type == "starts_with":
            title_conditions.append("title LIKE ?")
            params.append(f"{query}%")
        elif search_type == "ends_with":
            title_conditions.append("title LIKE ?")
            params.append(f"%{query}")
        elif search_type == "all_words":
            words = query.strip().split()
            if words:
                word_conditions = " AND ".join(["title LIKE ?"] * len(words))
                title_conditions.append(f"({word_conditions})")
                params.extend([f"%{word}%" for word in words])
        else:  # "contains" (default)
            title_conditions.append("title LIKE ?")
            params.append(f"%{query}%")

    if director:
        director = director.strip()
        if director:
            title_conditions.append("director LIKE ?")
            params.append(f"%{director}%")

    deleted_filter = "" if include_deleted else "deleted_at IS NULL AND "
    if title_conditions:
        base_query = (f"FROM titles {RATING_JOIN} WHERE "
                      + deleted_filter + " AND ".join(title_conditions))
    else:
        # No criteria: match nothing, but keep the join so the callers' rating
        # columns still resolve.
        return f"FROM titles {RATING_JOIN} WHERE 1=0", []

    if section:
        base_query += " AND section = ?"
        params.append(section)

    if sections:
        base_query += f" AND {SECTION_SQL} IN ({','.join('?' * len(sections))})"
        params.extend(sections)

    if qualities:
        base_query += f" AND {QUALITY_SQL} IN ({','.join('?' * len(qualities))})"
        params.extend(qualities)

    if min_rating is not None:
        base_query += f" AND {RATING_SCORE_SQL} >= ?"
        params.append(min_rating)

    return base_query, params


def search_titles(
    query: str,
    section: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    search_type: str = "contains",
    director: Optional[str] = None,
    include_deleted: bool = False,
    min_rating: Optional[float] = None,
    sort: str = "title"
) -> tuple[list[dict], int]:
    """
    Search titles by query string.
    
    Args:
        query: Search query string (searches in title)
        section: Filter by section (optional)
        page: Page number (default: 1)
        per_page: Results per page (default: 50)
        search_type: Type of search - "contains", "starts_with", "ends_with", "all_words" (default: "contains")
        director: Search by director name (optional, searches in director field)
        min_rating: Keep only titles rated at least this much (optional)
        sort: "title", "rating", "year" or "year_asc"
    
    Returns:
        A tuple of (results, total_count).
    """
    base_query, params = _build_search_filter(
        query, section, search_type, director, include_deleted, min_rating
    )

    with get_db() as conn:
        cursor = conn.cursor()

        # Get total count
        cursor.execute(f"SELECT COUNT(*) {base_query}", params)
        total = cursor.fetchone()[0]

        order_by = {
            'rating': f"{RATING_SCORE_SQL} DESC NULLS LAST, title",
            'year': "year DESC NULLS LAST, title",
            'year_asc': "year ASC NULLS LAST, title",
        }.get(sort, "title")

        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute(
            f"""
            SELECT titles.id, title, url, section, metadata, quality, director, year,
                   title_first_letter, created_at, deleted_at, {RATING_COLUMNS}
            {base_query}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )

        results = [dict(row) for row in cursor.fetchall()]
        return results, total


GROUP_KEY_SQL = "COALESCE('tmdb:' || r.tmdb_id, 'post:' || titles.id)"

# The quality column is written by three different code paths in parser.py, two
# of which keep the source casing, so '720p'/'720P' and '4K'/'2160P' both mean
# one thing. Fold them here until the stored values are migrated.
QUALITY_GROUPS = [
    ('4K', '4K / 2160p', ('4K', '2160P', 'UHD')),
    ('1080p', '1080p', ('1080P', '1080I')),
    ('720p', '720p', ('720P', '720I')),
    ('BluRay', 'BluRay', ('BLURAY', 'BDRIP', 'BRRIP')),
    ('WEB', 'WEB', ('WEB', 'WEB-DL', 'WEBDL', 'WEBRIP')),
    ('HDTV', 'HDTV', ('HDTV',)),
    ('DVD', 'DVD', ('DVD', 'DVDRIP')),
    ('SD', 'SD', ('SD',)),
    ('CAM', 'CAM', ('CAM', 'HDCAM', 'TS', 'TELESYNC')),
]

QUALITY_SQL = "CASE " + " ".join(
    "WHEN UPPER(quality) IN ({}) THEN '{}'".format(
        ",".join(f"'{v}'" for v in variants), key
    )
    for key, _, variants in QUALITY_GROUPS
) + " WHEN quality IS NULL OR quality = '' THEN NULL ELSE UPPER(quality) END"

# Nine sections, but five groups: the forum splits animation by quality and the
# panel should not.
SECTION_SQL = ("CASE WHEN section LIKE 'Animazione%' THEN 'Animazione' "
               "WHEN section LIKE 'Anime%' THEN 'Anime' ELSE section END")

SECTION_ORDER = ['Movie', 'Series', 'Documentari', 'Animazione', 'Anime']


def search_titles_grouped(
    query: str,
    section: Optional[str] = None,
    page: int = 1,
    per_page: int = 30,
    search_type: str = "contains",
    director: Optional[str] = None,
    include_deleted: bool = False,
    min_rating: Optional[float] = None,
    sort: str = "title",
    sections: Optional[list] = None,
    qualities: Optional[list] = None,
) -> tuple[list[dict], int]:
    """Search titles grouped by film rather than by post.

    Posts sharing a tmdb_id collapse into one group; a post without a match is a
    group of its own. Paging happens over groups, so a film with many posts is
    never split across two pages and the count means films, not posts.

    Returns (groups, total_groups). Each group is a dict with:
        key, tmdb_id, title, year, director, section, poster_path, rating,
        rating_source, matched_title, matched_year, confidence, match_status,
        posts (the underlying rows, as returned by search_titles).
    """
    base_query, params = _build_search_filter(
        query, section, search_type, director, include_deleted, min_rating,
        sections, qualities
    )

    if "1=0" in base_query:
        return [], 0

    group_order = {
        'rating': f"MAX({RATING_SCORE_SQL}) DESC NULLS LAST, sort_title",
        'year': "MAX(year) DESC NULLS LAST, sort_title",
        'year_asc': "MIN(year) ASC NULLS LAST, sort_title",
    }.get(sort, "sort_title")

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT COUNT(*) FROM (SELECT 1 {base_query} GROUP BY {GROUP_KEY_SQL})",
            params
        )
        total = cursor.fetchone()[0]

        offset = (page - 1) * per_page
        cursor.execute(
            f"""
            SELECT {GROUP_KEY_SQL} AS group_key, MIN(title) AS sort_title
            {base_query}
            GROUP BY group_key
            ORDER BY {group_order}
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        keys = [row["group_key"] for row in cursor.fetchall()]
        if not keys:
            return [], total

        placeholders = ",".join("?" * len(keys))
        cursor.execute(
            f"""
            SELECT titles.id, title, url, section, metadata, quality, languages,
                   director, year, title_first_letter, created_at, deleted_at,
                   {GROUP_KEY_SQL} AS group_key, {RATING_COLUMNS}
            {base_query} AND {GROUP_KEY_SQL} IN ({placeholders})
            ORDER BY title
            """,
            params + keys
        )

        grouped: dict[str, dict] = {key: None for key in keys}
        for row in cursor.fetchall():
            post = dict(row)
            key = post.pop("group_key")
            group = grouped.get(key)
            if group is None:
                group = _new_group(key, post)
                grouped[key] = group
            group["posts"].append(post)

        return [g for g in grouped.values() if g], total


def get_search_facets(
    query: str,
    section: Optional[str] = None,
    search_type: str = "contains",
    director: Optional[str] = None,
    include_deleted: bool = False,
    min_rating: Optional[float] = None,
    sections: Optional[list] = None,
    qualities: Optional[list] = None,
) -> dict:
    """Count films per section and per quality for the current search.

    Each facet is counted with every filter applied except its own, so the
    numbers answer "what would I get if I also picked this" rather than
    collapsing to the current selection.
    """
    def count_by(expr: str, **overrides) -> dict:
        kw = dict(sections=sections, qualities=qualities)
        kw.update(overrides)
        base_query, params = _build_search_filter(
            query, section, search_type, director, include_deleted, min_rating,
            kw['sections'], kw['qualities']
        )
        if "1=0" in base_query:
            return {}
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {expr} AS k, COUNT(DISTINCT {GROUP_KEY_SQL}) AS n "
                f"{base_query} GROUP BY k",
                params
            )
            return {row["k"]: row["n"] for row in cursor.fetchall() if row["k"]}

    section_counts = count_by(SECTION_SQL, sections=None)
    quality_counts = count_by(QUALITY_SQL, qualities=None)

    known = [s for s in SECTION_ORDER if s in section_counts]
    extra = sorted(k for k in section_counts if k not in SECTION_ORDER)
    section_facets = [
        {'key': k, 'label': k, 'count': section_counts[k]} for k in known + extra
    ]

    quality_facets = [
        {'key': key, 'label': label, 'count': quality_counts[key]}
        for key, label, _ in QUALITY_GROUPS if key in quality_counts
    ]
    seen = {q['key'] for q in quality_facets}
    quality_facets += [
        {'key': k, 'label': k, 'count': n}
        for k, n in sorted(quality_counts.items()) if k not in seen
    ]

    return {'sections': section_facets, 'qualities': quality_facets}


def _new_group(key: str, post: dict) -> dict:
    """Seed a result group from its first post."""
    has_imdb = post.get("imdb_rating") is not None
    return {
        "key": key,
        "tmdb_id": post.get("tmdb_id"),
        "title": post.get("matched_title") or post["title"],
        "year": post.get("matched_year") or post.get("year"),
        "director": post.get("director"),
        "section": post.get("section"),
        "poster_path": post.get("poster_path"),
        "rating": post.get("imdb_rating") if has_imdb else post.get("tmdb_rating"),
        "rating_source": "IMDb" if has_imdb else "TMDB",
        "matched_title": post.get("matched_title"),
        "matched_year": post.get("matched_year"),
        "confidence": post.get("confidence"),
        "match_status": post.get("match_status"),
        "posts": [],
    }


def get_all_sections() -> list[str]:
    """Get all unique sections from the database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT section FROM titles WHERE section IS NOT NULL AND deleted_at IS NULL ORDER BY section")
        return [row[0] for row in cursor.fetchall()]


def get_stats() -> dict:
    """Get database statistics."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM titles WHERE deleted_at IS NULL")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT section) FROM titles WHERE deleted_at IS NULL")
        sections = cursor.fetchone()[0]
        return {"total_titles": total, "total_sections": sections}


def start_import() -> int:
    """
    Record the start of an import.
    Returns the import_id.
    """
    from datetime import datetime
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO import_history (started_at, status)
            VALUES (?, 'running')
            """,
            (datetime.now(),)
        )
        return cursor.lastrowid


def complete_import(
    import_id: int,
    titles_found: int,
    titles_inserted: int,
    titles_updated: int,
    success: bool = True
):
    """
    Record the completion of an import.
    """
    from datetime import datetime
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE import_history
            SET completed_at = ?, titles_found = ?, titles_inserted = ?, 
                titles_updated = ?, status = ?
            WHERE id = ?
            """,
            (
                datetime.now(),
                titles_found,
                titles_inserted,
                titles_updated,
                'completed' if success else 'failed',
                import_id
            )
        )


def get_last_import(successful_only: bool = False) -> Optional[dict]:
    """
    Get the last import record.

    Args:
        successful_only: only consider imports that completed successfully.
            The scheduler uses this so a failed run does not push the next
            attempt a full interval away.

    Returns None if no imports found.
    """
    where = "WHERE status = 'completed'" if successful_only else ""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT id, started_at, completed_at, titles_found,
                   titles_inserted, titles_updated, status
            FROM import_history
            {where}
            ORDER BY started_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_recent_imports(limit: int = 10) -> list[dict]:
    """Get the most recent import records, newest first."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, started_at, completed_at, titles_found,
                   titles_inserted, titles_updated, status
            FROM import_history
            ORDER BY started_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_setting(key: str, default: str = None) -> Optional[str]:
    """Read a runtime setting, falling back to default when unset."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default


def set_setting(key: str, value) -> None:
    """Write a runtime setting."""
    from datetime import datetime
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                           updated_at = excluded.updated_at
            """,
            (key, str(value), datetime.now())
        )


def migrate_refresh_policy() -> dict:
    """One-off cleanup of rows written by versions before the revisit policy.

    Drops the alphabet navigation links that were stored as titles, and clears
    the revisit date of every post that has already been read, so old posts are
    never fetched again.
    """
    import config

    if get_setting('migrated_refresh_policy'):
        return {'skipped': True}

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM titles
            WHERE LENGTH(title) = 1 AND title GLOB '[#0-9A-Za-z]' AND metadata IS NULL
        """)
        removed = cursor.rowcount

        cursor.execute(
            """
            UPDATE titles
            SET details_next_refresh_at = CASE
                WHEN post_created_at IS NOT NULL
                 AND datetime(post_created_at, ?) > datetime('now')
                THEN datetime(post_created_at, ?)
                ELSE NULL
            END
            WHERE details_scraped_at IS NOT NULL
            """,
            (f'+{config.POST_RECHECK_DAYS} days', f'+{config.POST_RECHECK_DAYS} days')
        )
        rescheduled = cursor.rowcount

        cursor.execute("PRAGMA table_info(titles)")
        if any(row[1] == 'status' for row in cursor.fetchall()):
            try:
                cursor.execute("ALTER TABLE titles DROP COLUMN status")
            except sqlite3.OperationalError:
                # An older SQLite cannot drop a column; leaving it costs nothing
                # now that nothing writes to it.
                pass

    set_setting('migrated_refresh_policy', '1')
    return {'skipped': False, 'removed': removed, 'rescheduled': rescheduled}


def get_int_setting(key: str, default: int) -> int:
    """Read a runtime setting as int, falling back to default when unusable."""
    raw = get_setting(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_schedule() -> dict:
    """
    Read the import schedule, falling back to the environment.

    The web container writes these settings and the scheduler reads them, so
    both go through here to stay in step.
    """
    enabled = get_setting('scrape_enabled', os.getenv('SCRAPE_ENABLED', 'true'))
    return {
        'enabled': str(enabled).lower() not in ('false', '0', 'no'),
        'interval_days': get_int_setting(
            'scrape_interval_days', int(os.getenv('SCRAPE_INTERVAL_DAYS', '3'))
        ),
        'hour': get_int_setting('scrape_hour', int(os.getenv('SCRAPE_HOUR', '2'))),
        'minute': get_int_setting('scrape_minute', int(os.getenv('SCRAPE_MINUTE', '0'))),
    }


def migrate_existing_titles():
    """
    Migrate existing titles to populate director, year, and title_first_letter fields.
    Returns tuple of (updated_count, total_count).
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get all titles that need migration (where director is NULL or title_first_letter is NULL)
        cursor.execute("""
            SELECT id, title FROM titles 
            WHERE director IS NULL OR title_first_letter IS NULL
        """)
        titles = cursor.fetchall()
        
        updated = 0
        for row in titles:
            title_id, title = row
            director, year, first_letter = extract_director_and_year(title)
            
            cursor.execute("""
                UPDATE titles 
                SET director = ?, year = ?, title_first_letter = ?
                WHERE id = ?
            """, (director, year, first_letter, title_id))
            updated += 1
        
        conn.commit()
        return updated, len(titles)


def get_section_titles(
    section: str,
    page: int = 1,
    per_page: int = 50,
    year: Optional[int] = None,
    first_letter: Optional[str] = None,
    quality: Optional[str] = None
) -> tuple[list[dict], int, dict]:
    """
    Get titles for a specific section with optional filters.
    
    Args:
        section: Section name
        page: Page number (default: 1)
        per_page: Results per page (default: 50)
        year: Filter by year (optional)
        first_letter: Filter by first letter (optional, case-insensitive)
        quality: Filter by quality/resolution (optional)
    
    Returns:
        Tuple of (results, total_count, filters_info)
        - results: List of title dictionaries
        - total_count: Total number of results
        - filters_info: Dict with available years, letters, and qualities for this section
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Build base query
        base_query = "FROM titles WHERE deleted_at IS NULL AND section = ?"
        params = [section]
        
        if year:
            base_query += " AND year = ?"
            params.append(year)
        
        if first_letter:
            base_query += " AND UPPER(title_first_letter) = ?"
            params.append(first_letter.upper())
        
        if quality:
            base_query += " AND quality = ?"
            params.append(quality)
        
        # Get total count
        cursor.execute(f"SELECT COUNT(*) {base_query}", params)
        total = cursor.fetchone()[0]
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute(
            f"""
            SELECT id, title, url, section, metadata, quality, director, year, title_first_letter, created_at
            {base_query}
            ORDER BY title
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        
        results = [dict(row) for row in cursor.fetchall()]
        
        # Get available years and letters for this section
        cursor.execute("""
            SELECT DISTINCT year FROM titles
            WHERE deleted_at IS NULL AND section = ? AND year IS NOT NULL
            ORDER BY year DESC
        """, (section,))
        available_years = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT UPPER(title_first_letter) as letter FROM titles
            WHERE deleted_at IS NULL AND section = ? AND title_first_letter IS NOT NULL
            ORDER BY letter
        """, (section,))
        available_letters = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT quality FROM titles
            WHERE deleted_at IS NULL AND section = ? AND quality IS NOT NULL AND quality != ''
            ORDER BY quality
        """, (section,))
        available_qualities = [row[0] for row in cursor.fetchall()]
        
        filters_info = {
            'available_years': available_years,
            'available_letters': available_letters,
            'available_qualities': available_qualities
        }
        
        return results, total, filters_info


def get_section_stats(section: str) -> dict:
    """Get statistics for a specific section."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM titles WHERE deleted_at IS NULL AND section = ?", (section,))
        total = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(DISTINCT year) FROM titles
            WHERE deleted_at IS NULL AND section = ? AND year IS NOT NULL
        """, (section,))
        years_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(DISTINCT director) FROM titles
            WHERE deleted_at IS NULL AND section = ? AND director IS NOT NULL
        """, (section,))
        directors_count = cursor.fetchone()[0]
        
        return {
            'total_titles': total,
            'years_count': years_count,
            'directors_count': directors_count
        }


def get_titles_with_missing_data(
    page: int = 1,
    per_page: int = 50,
    section: Optional[str] = None
) -> tuple[list[dict], int]:
    """
    Get titles where director or year is NULL (for error checking).
    
    Args:
        page: Page number (default: 1)
        per_page: Results per page (default: 50)
        section: Filter by section (optional)
    
    Returns:
        Tuple of (results, total_count)
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Build base query
        base_query = "FROM titles WHERE (director IS NULL OR year IS NULL)"
        params = []
        
        if section:
            base_query += " AND section = ?"
            params.append(section)
        
        # Get total count
        cursor.execute(f"SELECT COUNT(*) {base_query}", params)
        total = cursor.fetchone()[0]
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute(
            f"""
            SELECT id, title, url, section, metadata, quality, director, year, title_first_letter, created_at
            {base_query}
            ORDER BY section, title
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        
        results = [dict(row) for row in cursor.fetchall()]
        return results, total


# Ratings live in their own table, so every read that shows them joins through
# these two fragments.
RATING_SCORE_SQL = "COALESCE(r.imdb_rating, r.tmdb_rating)"

RATING_JOIN = "LEFT JOIN title_ratings r ON r.title_id = titles.id"

RATING_COLUMNS = """
    r.media_type, r.tmdb_id, r.imdb_id, r.tmdb_rating, r.tmdb_votes,
    r.imdb_rating, r.imdb_votes, r.poster_path, r.matched_title,
    r.matched_year, r.confidence, r.match_status
"""


def get_titles_to_match(limit: int = 500, retry_unmatched: bool = False,
                       after_id: int = 0) -> list[dict]:
    """
    Titles that still need a lookup on the rating providers, by ascending id.

    Args:
        retry_unmatched: also return the titles a previous run failed to match.
                         Rejected ones are never returned.
        after_id: resume past this id, so consecutive batches move forward even
                  when the rows they just wrote still match the filter.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        if retry_unmatched:
            where = "(r.title_id IS NULL OR r.match_status = 'unmatched')"
        else:
            where = "r.title_id IS NULL"
        cursor.execute(
            f"""
            SELECT titles.id, titles.title, titles.section, titles.director, titles.year
            FROM titles {RATING_JOIN}
            WHERE titles.deleted_at IS NULL AND titles.id > ? AND {where}
            ORDER BY titles.id
            LIMIT ?
            """,
            (after_id, limit)
        )
        return [dict(row) for row in cursor.fetchall()]


def save_rating(title_id: int, match_status: str, **fields) -> None:
    """Write the outcome of a lookup, replacing any previous one."""
    columns = ['media_type', 'tmdb_id', 'imdb_id', 'tmdb_rating', 'tmdb_votes',
               'imdb_rating', 'imdb_votes', 'poster_path', 'matched_title',
               'matched_year', 'confidence']
    values = [fields.get(c) for c in columns]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            INSERT INTO title_ratings (title_id, {', '.join(columns)},
                                       match_status, matched_at)
            VALUES (?{', ?' * len(columns)}, ?, ?)
            ON CONFLICT(title_id) DO UPDATE SET
                {', '.join(f'{c} = excluded.{c}' for c in columns)},
                match_status = excluded.match_status,
                matched_at = excluded.matched_at,
                imdb_checked_at = NULL
            """,
            [title_id] + values + [match_status, datetime.now()]
        )


def reject_rating(title_id: int) -> None:
    """Mark a match as wrong so the job stops proposing it."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO title_ratings (title_id, match_status, matched_at)
            VALUES (?, 'rejected', ?)
            ON CONFLICT(title_id) DO UPDATE SET
                match_status = 'rejected',
                tmdb_id = NULL, imdb_id = NULL,
                tmdb_rating = NULL, tmdb_votes = NULL,
                imdb_rating = NULL, imdb_votes = NULL,
                poster_path = NULL, matched_title = NULL, matched_year = NULL,
                confidence = NULL, imdb_checked_at = NULL,
                matched_at = excluded.matched_at
            """,
            (title_id, datetime.now())
        )


def reset_rating(title_id: int) -> None:
    """Forget a lookup so the next run tries the title again."""
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM title_ratings WHERE title_id = ?", (title_id,))


def get_ratings_missing_imdb(limit: int) -> list[dict]:
    """Matched titles with an IMDb id whose IMDb vote was never fetched."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.title_id, r.imdb_id, titles.title
            FROM title_ratings r
            JOIN titles ON titles.id = r.title_id
            WHERE r.imdb_id IS NOT NULL
              AND r.imdb_checked_at IS NULL
              AND r.match_status IN ('matched', 'manual')
              AND titles.deleted_at IS NULL
            ORDER BY r.title_id
            LIMIT ?
            """,
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]


def save_imdb_rating(title_id: int, rating: Optional[float], votes: Optional[int]) -> None:
    """Store the IMDb vote. The timestamp is written even when there is none,
    so a title without a vote is not asked for again."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE title_ratings
            SET imdb_rating = ?, imdb_votes = ?, imdb_checked_at = ?
            WHERE title_id = ?
            """,
            (rating, votes, datetime.now(), title_id)
        )


def get_rating_stats() -> dict:
    """Counts for the admin page and the review page."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM titles WHERE deleted_at IS NULL")
        total = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT r.match_status, COUNT(*)
            FROM title_ratings r
            JOIN titles ON titles.id = r.title_id
            WHERE titles.deleted_at IS NULL
            GROUP BY r.match_status
            """
        )
        by_status = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT COUNT(*) FROM title_ratings r
            JOIN titles ON titles.id = r.title_id
            WHERE titles.deleted_at IS NULL AND r.imdb_rating IS NOT NULL
            """
        )
        with_imdb = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM title_ratings r
            JOIN titles ON titles.id = r.title_id
            WHERE titles.deleted_at IS NULL AND r.imdb_id IS NOT NULL
              AND r.imdb_checked_at IS NULL
              AND r.match_status IN ('matched', 'manual')
            """
        )
        pending_imdb = cursor.fetchone()[0]

        matched = by_status.get('matched', 0) + by_status.get('manual', 0)
        return {
            'total_titles': total,
            'matched': matched,
            'low_confidence': by_status.get('low_confidence', 0),
            'unmatched': by_status.get('unmatched', 0),
            'rejected': by_status.get('rejected', 0),
            'pending': total - sum(by_status.values()),
            'with_imdb': with_imdb,
            'pending_imdb': pending_imdb,
        }


def get_rating_matches(
    page: int = 1,
    per_page: int = 50,
    status: str = 'low_confidence',
    section: Optional[str] = None
) -> tuple[list[dict], int]:
    """
    Matches to eyeball, worst first.

    Args:
        status: one of the match_status values, or "pending" for the titles
                the job has not looked up yet.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        params = []
        if status == 'pending':
            base_query = f"FROM titles {RATING_JOIN} WHERE titles.deleted_at IS NULL AND r.title_id IS NULL"
        else:
            base_query = (f"FROM titles {RATING_JOIN} "
                          "WHERE titles.deleted_at IS NULL AND r.match_status = ?")
            params.append(status)

        if section:
            base_query += " AND titles.section = ?"
            params.append(section)

        cursor.execute(f"SELECT COUNT(*) {base_query}", params)
        total = cursor.fetchone()[0]

        offset = (page - 1) * per_page
        cursor.execute(
            f"""
            SELECT titles.id, titles.title, titles.url, titles.section,
                   titles.director, titles.year, {RATING_COLUMNS}
            {base_query}
            ORDER BY COALESCE(r.confidence, 0), titles.title
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        return [dict(row) for row in cursor.fetchall()], total


if __name__ == "__main__":
    # Initialize database when run directly
    init_db()
    print(f"Database initialized at {config.DATABASE_PATH}")
