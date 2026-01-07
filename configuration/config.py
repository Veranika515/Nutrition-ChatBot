import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NUTRITION_API_KEY = os.getenv("NUTRITION_API_KEY")

for name, val in {
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "NUTRITION_API_KEY": NUTRITION_API_KEY,
}.items():
    if not val:
        raise RuntimeError(f"Missing {name} in .env")
