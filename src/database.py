"""Database module for DDUnlimited Search."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_title ON titles(title)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_section ON titles(section)")
        
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
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO titles (title, url, section, metadata, quality)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, url, section, metadata, quality)
            )
            return True
        except sqlite3.IntegrityError:
            # URL already exists, update the record
            cursor.execute(
                """
                UPDATE titles SET title = ?, section = ?, metadata = ?, quality = ?
                WHERE url = ?
                """,
                (title, section, metadata, quality, url)
            )
            return False


def search_titles(
    query: str,
    section: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    search_type: str = "contains"
) -> tuple[list[dict], int]:
    """
    Search titles by query string.
    
    Args:
        query: Search query string
        section: Filter by section (optional)
        page: Page number (default: 1)
        per_page: Results per page (default: 50)
        search_type: Type of search - "contains", "starts_with", "ends_with", "all_words" (default: "contains")
    
    Returns:
        A tuple of (results, total_count).
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Build query based on search type
        if search_type == "starts_with":
            base_query = "FROM titles WHERE title LIKE ?"
            params = [f"{query}%"]
        elif search_type == "ends_with":
            base_query = "FROM titles WHERE title LIKE ?"
            params = [f"%{query}"]
        elif search_type == "all_words":
            # Split query into words and create conditions for each word
            words = query.strip().split()
            if not words:
                base_query = "FROM titles WHERE 1=0"
                params = []
            else:
                conditions = " AND ".join(["title LIKE ?"] * len(words))
                base_query = f"FROM titles WHERE {conditions}"
                params = [f"%{word}%" for word in words]
        else:  # "contains" (default)
            base_query = "FROM titles WHERE title LIKE ?"
            params = [f"%{query}%"]

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
            SELECT id, title, url, section, metadata, quality, created_at
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


if __name__ == "__main__":
    # Initialize database when run directly
    init_db()
    print(f"Database initialized at {config.DATABASE_PATH}")
