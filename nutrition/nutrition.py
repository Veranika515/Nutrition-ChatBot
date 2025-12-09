import time
import json

import requests
import re
from typing import List, Tuple
from openai import OpenAI
from configuration.config import OPENAI_API_KEY, CALORIE_NINJAS_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

_NUM_RE = re.compile(r"^(\d+(?:[.,]\d+)?)(?:\s*(?:g|gram|grams|gramů|gramy)?)$", re.IGNORECASE)

def translate_to_english(food_name: str) -> str:
    system_prompt = (
        "Jsi odborník na přesné překlady potravin pro kalorické databáze. "
        "Tvým cílem je, aby byl překlad co nejvíce **KALORICKY SPECIFICKÝ**.\n"
        "**NIKDY NESMÍŠ OMITNOUT ZPŮSOB PŘÍPRAVY (např. 'smažený', 'pečený', 'vařený').**\n"
        "Pokud je způsob přípravy uveden, musí být přeložen.\n"
        "Příklady:\n"
        "• Vstup: 'Smažený eidam' → Výstup: 'Fried Edam cheese'\n"
        "• Vstup: 'Pečené kuře' → Výstup: 'Roasted chicken'\n"
        "• Vstup: 'Eidam' → Výstup: 'Edam cheese' (Jen v tomto případě není příprava)\n"
        "**Odpověz POUZE samotným překladem bez jakýchkoliv dalších slov.**"
    )
    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
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
    print(food_name_en)

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

            print("--- FULL API RESPONSE START ---")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            print("--- FULL API RESPONSE END ---")

            items = data.get("items") or []
            if not items:
                print("⚠️ Not found in CalorieNinjas:", query)
                return None
            f = items[0]

            base_kcal = float(f.get("calories", 0) or 0)
            base_protein = float(f.get("protein_g", 0) or 0)
            base_fat = float(f.get("fat_total_g", 0) or 0)
            base_carbs = float(f.get("carbohydrates_total_g", 0) or 0)

            serving_size = float(f.get("serving_size_g", 100.0) or 100.0)

            scale_factor = grams / serving_size

            final_kcal = base_kcal * scale_factor
            final_protein = base_protein * scale_factor
            final_fat = base_fat * scale_factor
            final_carbs = base_carbs * scale_factor

            return {
                "food_name": food_name,
                "kcal": final_kcal,
                "protein": final_protein,
                "fat": final_fat,
                "carbs": final_carbs,
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

def parse_food_pairs_llm(text: str) -> List[Tuple[str, int]]:
    system_prompt = """
        Jsi asistent pro výživu a **přesný parser** textu.
        Tvým úkolem je z české věty vytáhnout všechny potraviny a jejich množství, a to s **maximální kalorickou specifičností**.

        Pravidla:
        1. Vracej POUZE JSON pole objektů: [{"food": "...", "grams": ...}, ...]
        2. Hodnota "food" musí být maximálně přesná a **VŽDY ZAHRNUJE** způsob přípravy (např. 'smažený', 'pečený') nebo část produktu (např. 'kuřecí prsa'), aby nedošlo k chybě v kaloriích.
        3. Pokud je množství uvedeno v ml, převeď 1 ml = 1 g.
        4. Pokud je množství uvedeno v kusech (např. "3 vejce", "2 banány"), odhadni běžnou hmotnost v gramech pro daný počet kusů a vrať výsledek v gramech.
        5. Pokud je jídlo složené (např. sendvič), extrahuj jednotlivé potraviny, které mají uvedené množství.
        6. Nepřidávej žádný text okolo, žádné vysvětlení.

        Příklad vstupu a výstupu:
        Vstup: "Dnes ráno jsem měla 60 g ovesné kaše, 250 ml kávy a 80 g pečených kuřecích prsou."
        Výstup:
        [
          {"food": "ovesná kaše", "grams": 60},
          {"food": "káva", "grams": 250},
          {"food": "pečená kuřecí prsa", "grams": 80}
        ]
        """

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        max_completion_tokens=150,
        temperature=0.1,
    )

    raw = completion.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
        pairs: List[Tuple[str, int]] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                food = str(item.get("food", "")).strip()
                grams = item.get("grams")
                try:
                    grams_int = int(round(float(grams)))
                except Exception:
                    continue
                if food and grams_int > 0:
                    pairs.append((food, grams_int))
        return pairs
    except json.JSONDecodeError:
        return []