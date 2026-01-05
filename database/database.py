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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY,
                sex TEXT NOT NULL,
                age INTEGER NOT NULL,
                height_cm REAL NOT NULL,
                weight_kg REAL NOT NULL,
                activity TEXT NOT NULL,
                pal REAL NOT NULL,
                goal TEXT NOT NULL,
                target_calories REAL NOT NULL,
                target_protein_g REAL NOT NULL,
                target_fat_g REAL NOT NULL,
                target_carbs_g REAL NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        try:
            conn.execute(
                "ALTER TABLE profiles ADD COLUMN show_targets INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass

        conn.commit()

def upsert_profile(user_id: str, profile: dict, targets: dict) -> None:
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO profiles (
                user_id, sex, age, height_cm, weight_kg, activity, pal, goal,
                target_calories, target_protein_g, target_fat_g, target_carbs_g, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                sex=excluded.sex,
                age=excluded.age,
                height_cm=excluded.height_cm,
                weight_kg=excluded.weight_kg,
                activity=excluded.activity,
                pal=excluded.pal,
                goal=excluded.goal,
                target_calories=excluded.target_calories,
                target_protein_g=excluded.target_protein_g,
                target_fat_g=excluded.target_fat_g,
                target_carbs_g=excluded.target_carbs_g,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                user_id,
                profile["sex"],
                profile["age"],
                profile["height_cm"],
                profile["weight_kg"],
                profile["activity"],
                targets["pal"],
                profile["goal"],
                targets["calories"],
                targets["protein_g"],
                targets["fat_g"],
                targets["carbs_g"],
            ),
        )
        conn.commit()

def set_show_targets(user_id: str, enabled: bool) -> None:
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE profiles SET show_targets = ? WHERE user_id = ?",
            (1 if enabled else 0, user_id),
        )
        conn.commit()

def get_profile(user_id: str):
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT target_calories, show_targets
            FROM profiles
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return row
