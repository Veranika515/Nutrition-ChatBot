import time

import requests
import re
from typing import List, Tuple
from openai import OpenAI
from configuration.config import OPENAI_API_KEY, CALORIE_NINJAS_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

# _NUM_RE = re.compile(r"^(\d+(?:[.,]\d+)?)$", re.IGNORECASE)
_NUM_RE = re.compile(r"^(\d+(?:[.,]\d+)?)(?:\s*(?:g|gram|grams|gramů|gramy)?)$", re.IGNORECASE)

def translate_to_english(food_name: str) -> str:
    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "Překládej pouze názvy potravin z češtiny do angličtiny. Odpověz jen překladem, bez vysvětlení."},
            {"role": "user", "content": food_name}
        ],
        max_completion_tokens=10
    )
    return completion.choices[0].message.content.strip().lower()

def _to_int_grams(tok: str) -> int | None:
    tok = tok.strip().lower()
    m = _NUM_RE.match(tok)
    if not m:
        return None
    num = m.group(1).replace(",", ".")
    try:
        return int(round(float(num)))
    except ValueError:
        return None

GRAM_WORDS = {"g", "gram", "grams", "gramy", "gramů"}

def parse_food_pairs_free(tokens: List[str], start: int = 0) -> List[Tuple[str, int]]:
    pairs: List[Tuple[str, int]] = []
    buf: List[str] = []
    i = start
    while i < len(tokens):
        tok = tokens[i]
        grams = _to_int_grams(tok)
        if grams is not None:
            if buf:
                food = " ".join(buf).strip()
                if food:
                    pairs.append((food, grams))
                buf = []
        else:
            if tok.strip().lower() in GRAM_WORDS:
                i += 1
                continue

            buf.append(tok)
        i += 1
    return pairs

def get_food_info(food_name: str, grams: int):
    food_name_en = translate_to_english(food_name)

    query = f"{food_name_en} {int(round(grams))}g"

    url = "https://api.calorieninjas.com/v1/nutrition"
    headers = {"X-Api-Key": CALORIE_NINJAS_KEY}

    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, params={"query": query}, timeout=12)
        except requests.RequestException as e:
            print("❌ CalorieNinjas network error:", e)
            return None

        if 200 <= resp.status_code < 300:
            data = resp.json()
            items = data.get("items") or []
            if not items:
                print("⚠️ Not found in CalorieNinjas:", query)
                return None
            f = items[0]
            return {
                "food_name": food_name,
                # "food_name_en": f.get("name", food_name_en),
                "kcal": float(f.get("calories", 0) or 0),
                "protein": float(f.get("protein_g", 0) or 0),
                "fat": float(f.get("fat_total_g", 0) or 0),
                "carbs": float(f.get("carbohydrates_total_g", 0) or 0),
            }

        if resp.status_code in (401, 403):
            print("❌ CalorieNinjas auth error:", resp.text[:200])
            return None

        if 500 <= resp.status_code < 600:
            print(f"❌ CalorieNinjas API error {resp.status_code}: {resp.text[:200]}")
            time.sleep(0.5 * (2 ** attempt))  # 0.5s, 1s
            continue

        print(f"❌ CalorieNinjas API error {resp.status_code}: {resp.text[:200]}")
        return None
    return None