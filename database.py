import sqlite3
import os
from datetime import datetime, timedelta
from config import Config

DB_FILE = Config.SQLITE_DB_PATH

def get_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    """Initializes the SQLite database tables."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Favorites table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_term TEXT UNIQUE NOT NULL,
                chat_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Notified hits table to prevent duplicate notifications
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notified_hits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_term TEXT NOT NULL,
                file_url TEXT NOT NULL,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(search_term, file_url)
            )
        """)
        
        # 3. Search cache table to bypass Telegram's 64-byte callback_data limit
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_url TEXT NOT NULL,
                file_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

# --- Favorites Helpers ---

def add_favorite(search_term: str, chat_id: int) -> bool:
    """Adds a search term to favorites. Returns True if successful, False if already exists."""
    search_term = search_term.strip().lower()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO favorites (search_term, chat_id) VALUES (?, ?)",
                (search_term, chat_id)
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def remove_favorite(fav_id: int) -> bool:
    """Removes a favorite search term by its ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favorites WHERE id = ?", (fav_id,))
        conn.commit()
        return cursor.rowcount > 0

def get_favorites():
    """Retrieves all favorite search terms."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, search_term, chat_id, created_at FROM favorites")
        return [dict(row) for row in cursor.fetchall()]

# --- Notified Hits Helpers ---

def is_hit_notified(search_term: str, file_url: str) -> bool:
    """Checks if a hit has already been notified to the user."""
    search_term = search_term.strip().lower()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM notified_hits WHERE search_term = ? AND file_url = ?",
            (search_term, file_url)
        )
        return cursor.fetchone() is not None

def add_notified_hit(search_term: str, file_url: str):
    """Marks a hit as notified."""
    search_term = search_term.strip().lower()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO notified_hits (search_term, file_url) VALUES (?, ?)",
                (search_term, file_url)
            )
            conn.commit()
    except Exception as e:
        # Log error or pass silently since it's just tracking
        pass

# --- Search Cache Helpers ---

def cache_search_result(file_url: str, file_name: str) -> int:
    """Caches a search result URL and Name, returning its unique cache ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO search_cache (file_url, file_name) VALUES (?, ?)",
            (file_url, file_name)
        )
        conn.commit()
        return cursor.lastrowid

def get_cached_search_result(cache_id: int):
    """Retrieves a cached search result by its ID."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT file_url, file_name FROM search_cache WHERE id = ?", (cache_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def cleanup_old_cache(hours: int = 24):
    """Deletes cached search results older than specified hours to keep DB lightweight."""
    cutoff_time = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM search_cache WHERE created_at < ?", (cutoff_time,))
        conn.commit()
