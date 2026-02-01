import pytest

from database import database

# Fikstura pro dočasnou databázi v souboru
@pytest.fixture
def mock_db(monkeypatch, tmp_path):
    # Vytvoříme cestu k dočasnému souboru v dočasné složce systému
    test_db_file = tmp_path / "test_meals.db"
    # Nahrazujeme cestu v modulu database
    monkeypatch.setattr(database, "DB_PATH", str(test_db_file))
    database.init_db()
    return database

def test_init_db_creates_tables(mock_db):
    """Ověření, že tabulky byly skutečně vytvořeny v souboru."""
    with mock_db.get_db_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row["name"] for row in cursor.fetchall()]
        assert "meals" in tables
        assert "profiles" in tables

def test_upsert_and_get_profile(mock_db):
    """Kontrola uložení a čtení profilu."""
    user_id = "test_user_1"
    profile_data = {"sex": "Muž", "age": 25, "height_cm": 180, "weight_kg": 80, "activity": "Sedavá", "goal": "Udržovat"}
    targets = {"pal": 1.2, "calories": 2200, "protein_g": 160, "fat_g": 70, "carbs_g": 230}

    mock_db.upsert_profile(user_id, profile_data, targets)
    row = mock_db.get_profile(user_id)

    assert row is not None
    assert row["target_calories"] == 2200