import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CALORIE_NINJAS_KEY = os.getenv("CALORIE_NINJAS_KEY")

for name, val in {
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "CALORIE_NINJAS_KEY": CALORIE_NINJAS_KEY,
}.items():
    if not val:
        raise RuntimeError(f"Missing {name} in .env")
