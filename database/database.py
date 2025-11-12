import sqlite3

DB_PATH = "meals.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                meal_type TEXT,
                food TEXT,
                grams INTEGER,
                kcal REAL,
                protein REAL,
                fat REAL,
                carbs REAL,
                date DATE DEFAULT CURRENT_DATE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE,
                first_seen DATE DEFAULT CURRENT_DATE
            )
        """)
        conn.commit()
