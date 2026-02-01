import pytest
from nutrition.nutrition import calculate_targets, _to_int_grams

def test_calculate_targets_male():
    """Ověření Mifflin-St Jeor vzorce pro muže."""
    result = calculate_targets(
        sex="Muž",
        age=25,
        height_cm=180,
        weight_kg=80,
        activity="Střední",
        goal="Udržovat"
    )

    # Проверяем ключевые значения
    # BMR = 10*80 + 6.25*180 - 5*25 + 5 = 1805
    # TDEE = 1805 * 1.55 (Střední) ≈ 2798
    assert result["calories"] == 2798
    assert result["protein_g"] == 160  # 2.0 * 80 kg
    assert result["pal"] == 1.55

def test_calculate_targets_female_lose_weight():
    """Kontrola výpočtu kalorického deficitu u žen."""
    result = calculate_targets(
        sex="Žena",
        age=30,
        height_cm=170,
        weight_kg=70,
        activity="Sedavá",
        goal="Hubnout"
    )

    # BMR = 10*70 + 6.25*170 - 5*30 - 161 = 1451.5
    # TDEE = 1451.5 * 1.2 = 1741.8
    # Target = 1741.8 - 500 = 1241.8 ≈ 1242
    assert result["calories"] == 1242

@pytest.mark.parametrize("input_val, expected", [
    ("100g", 100),
    ("50.5", 51),      # Kontrola zaokrouhlování
    ("200 grams", 200),
    ("abc", None),     # Nesprávné zadání
    ("150,5", 151)     # Nahrazení čárky tečkou
])
def test_to_int_grams_parsing(input_val, expected):
    """Kontrola regulárního výrazu a logiky parsování gramů."""
    assert _to_int_grams(input_val) == expected