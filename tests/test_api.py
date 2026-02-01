from unittest.mock import patch, MagicMock
from nutrition.nutrition import get_food_info


# 1. Test úspěšného scénáře
@patch('nutrition.nutrition.requests.get')
@patch('nutrition.nutrition.translate_to_english')
def test_get_food_info_success(mock_translate, mock_get):
    mock_translate.return_value = "apple"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "items": [
            {"calories": 52, "protein_g": 0.3, "fat_total_g": 0.2, "carbohydrates_total_g": 14, "serving_size_g": 100}]
    }
    mock_get.return_value = mock_response

    result = get_food_info("Jablko", 100)
    assert result is not None
    assert result["kcal"] == 52.0


# 2. Test prázdné odpovědi (Potravina nenalezena)
@patch('nutrition.nutrition.requests.get')
@patch('nutrition.nutrition.translate_to_english')
def test_get_food_info_not_found(mock_translate, mock_get):
    mock_translate.return_value = "unknown_food"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"items": []}  # Prázdný seznam
    mock_get.return_value = mock_response

    result = get_food_info("Neznámé jídlo", 100)

    # Ověřujeme, že funkce vrací None, když API nic nenajde
    assert result is None


# 3. Test chyby autorizace (HTTP 401)
@patch('nutrition.nutrition.requests.get')
@patch('nutrition.nutrition.translate_to_english')
def test_get_food_info_auth_error(mock_translate, mock_get):
    mock_translate.return_value = "apple"
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    mock_get.return_value = mock_response

    result = get_food_info("Jablko", 100)

    # Ověřujeme, že při chybě klíče aplikace nespadne, ale vrátí None
    assert result is None


# 4. Test chyby serveru (HTTP 500)
@patch('nutrition.nutrition.requests.get')
@patch('nutrition.nutrition.translate_to_english')
def test_get_food_info_server_error(mock_translate, mock_get):
    mock_translate.return_value = "apple"
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_get.return_value = mock_response

    # get_food_info v nutrition.py má v sobě retry smyčku (3 pokusy)
    result = get_food_info("Jablko", 100)

    assert result is None