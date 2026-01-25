"""Database module for DDUnlimited Search."""

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
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


def insert_title(title: str, url: str, section: str, metadata: str = None, quality: str = None) -> bool:
    """Insert a title into the database. Returns True if inserted, False if already exists."""
    # Extract director, year, and first letter
    director, year, first_letter = extract_director_and_year(title)
    
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO titles (title, url, section, metadata, quality, director, year, title_first_letter)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, url, section, metadata, quality, director, year, first_letter)
            )
            return True
        except sqlite3.IntegrityError:
            # URL already exists, update the record
            cursor.execute(
                """
                UPDATE titles SET title = ?, section = ?, metadata = ?, quality = ?, 
                                 director = ?, year = ?, title_first_letter = ?
                WHERE url = ?
                """,
                (title, section, metadata, quality, director, year, first_letter, url)
            )
            return False


def search_titles(
    query: str,
    section: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    search_type: str = "contains",
    director: Optional[str] = None
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
    
    Returns:
        A tuple of (results, total_count).
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Build query based on search type for title
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
                # Split query into words and create conditions for each word
                words = query.strip().split()
                if words:
                    word_conditions = " AND ".join(["title LIKE ?"] * len(words))
                    title_conditions.append(f"({word_conditions})")
                    params.extend([f"%{word}%" for word in words])
            else:  # "contains" (default)
                title_conditions.append("title LIKE ?")
                params.append(f"%{query}%")
        
        # Add director search if provided
        if director:
            director = director.strip()
            if director:
                title_conditions.append("director LIKE ?")
                params.append(f"%{director}%")
        
        # Build base query
        if title_conditions:
            base_query = "FROM titles WHERE " + " AND ".join(title_conditions)
        else:
            # If no search criteria, return empty results
            base_query = "FROM titles WHERE 1=0"
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
            ORDER BY title
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )

        results = [dict(row) for row in cursor.fetchall()]
        return results, total


def get_all_sections() -> list[str]:
    """Get all unique sections from the database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT section FROM titles WHERE section IS NOT NULL ORDER BY section")
        return [row[0] for row in cursor.fetchall()]


def get_stats() -> dict:
    """Get database statistics."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM titles")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT section) FROM titles")
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


def get_last_import() -> Optional[dict]:
    """
    Get the last import record.
    Returns None if no imports found.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, started_at, completed_at, titles_found, 
                   titles_inserted, titles_updated, status
            FROM import_history
            ORDER BY started_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


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
        base_query = "FROM titles WHERE section = ?"
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
            WHERE section = ? AND year IS NOT NULL 
            ORDER BY year DESC
        """, (section,))
        available_years = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT DISTINCT UPPER(title_first_letter) as letter FROM titles 
            WHERE section = ? AND title_first_letter IS NOT NULL 
            ORDER BY letter
        """, (section,))
        available_letters = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT DISTINCT quality FROM titles 
            WHERE section = ? AND quality IS NOT NULL AND quality != ''
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
        cursor.execute("SELECT COUNT(*) FROM titles WHERE section = ?", (section,))
        total = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(DISTINCT year) FROM titles 
            WHERE section = ? AND year IS NOT NULL
        """, (section,))
        years_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(DISTINCT director) FROM titles 
            WHERE section = ? AND director IS NOT NULL
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


if __name__ == "__main__":
    # Initialize database when run directly
    init_db()
    print(f"Database initialized at {config.DATABASE_PATH}")
