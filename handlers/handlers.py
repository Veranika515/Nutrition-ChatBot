import hashlib

from openai import OpenAI
from telegram import ReplyKeyboardMarkup, KeyboardButton
from telegram import Update
from telegram.ext import ContextTypes

from configuration.config import OPENAI_API_KEY
from database.database import get_db_connection
from nutrition.nutrition import get_food_info, parse_food_pairs_free

client = OpenAI(api_key=OPENAI_API_KEY)

def anonymize_user(user_id: int) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Denní přehled"), KeyboardButton("Počítat kalorie"), KeyboardButton("Přidat do jídelníčku")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

MEAL_PICK_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Snídaně"), KeyboardButton("Oběd"), KeyboardButton("Večeře"),  KeyboardButton("Svačina")],
        [KeyboardButton("Zpět na hlavní menu")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

EXIT_ONLY_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Zpět na hlavní menu")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = anonymize_user(update.effective_user.id)
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

    context.user_data["mode"] = None

    await update.message.reply_text(
        "👋 Dobrý den! Jsem *NutriBot*, Váš výživový poradce.\n\n"
        "🍽️ Pomohu Vám pečovat o zdravé stravování:\n"
        "• Rychle spočítejte kalorie – klepněte na tlačítko „počítat kalorie“.\n"
        "• Přidejte do dnešního jídelníčku to, co jste snědl(a) – klepněte na „Přidat do jídelníčku“.\n"
        "• Podívejte se na souhrn dne – tlačítkem „denní přehled“.\n\n"
        "💬 A pokud máte otázky týkající se výživy nebo zdravého životního stylu, jednoduše se zeptejte – rád Vám odpovím!",

    parse_mode="Markdown",
        reply_markup=MAIN_KB,
    )

async def _save_meal(update: Update, context: ContextTypes.DEFAULT_TYPE, meal_type: str, pairs):
    if not meal_type:
        await update.message.reply_text("⚠️ Není vybrán typ jídla.")
        return
    if not pairs:
        await update.message.reply_text(
            "⚠️ Napište položky ve formátu: \n✅`potravina gramy`✅, \nnapř. `banán 120 rýže 150`.",
            parse_mode="Markdown"
        )
        return

    user_id = anonymize_user(update.effective_user.id)

    lines, total_kcal, inserted_any = [], 0.0, False
    with get_db_connection() as conn:
        for food, grams in pairs:
            info = get_food_info(food, grams)
            if not info:
                lines.append(f"⚠️ Nepodařilo se najít údaje o `{food}`.")
                continue
            conn.execute("""
                INSERT INTO meals (user_id, meal_type, food, grams, kcal, protein, fat, carbs)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, meal_type, info["food_name"], grams,
                  info["kcal"], info["protein"], info["fat"], info["carbs"]))
            inserted_any = True
            total_kcal += info["kcal"]
            lines.append(
                f"• {info['food_name']} {grams} g = {info['kcal']:.1f} kcal "
                f"({info['protein']:.1f} bíl., {info['fat']:.1f} tuk., {info['carbs']:.1f} sach.)"
            )
        if inserted_any:
            conn.commit()

    if not inserted_any:
        await update.message.reply_text(
            "❌ Nic jsem neuložil — nepodařilo se získat údaje o žádné položce.",
            parse_mode="Markdown"
        )
        return

    lines.insert(0, f"✅ Přidáno do {meal_type}:")
    lines.append(f"\n🔥 Celkem: {total_kcal:.1f} kcal")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def enter_calorie_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "calories"
    await update.message.reply_text(
        "🔢 *Režim výpočtu kalorií*\n"
        "Pište potraviny a gramy na řádek, např.:\n`rýže 100`  \nnebo  \n`banán 120 rýže 150`.\n"
        "Pro ukončení klepni na „Zpět na hlavní nabídku“.",
        parse_mode="Markdown",
        reply_markup=EXIT_ONLY_KB,
    )

async def enter_add_meal_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "pick_meal"
    context.user_data.pop("meal_type", None)
    await update.message.reply_text(
        "Prosím vyberte, do kterého jídla chcete zapisovat: "
        "klepněte na *Snídaně / Oběd / Večeře / Svačina*.",
        parse_mode="Markdown",
        reply_markup=MEAL_PICK_KB,
    )

async def exit_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = None
    await update.message.reply_text(
        "🧭 Jste zpět v hlavním menu! \nVyberte, prosím, další akci",
        reply_markup=MAIN_KB,
    )

MEAL_TYPES = {"snídaně", "oběd", "večeře", "svačina"}

async def set_meal_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, meal_type: str):
    context.user_data["mode"] = "meal"
    context.user_data["meal_type"] = meal_type
    await update.message.reply_text(
        f"🍽️ Zapisování do *{meal_type}* je aktivní.\n"
        "Napište položky ve formátu: \n✅`potravina gramy`✅, \nnapř. `banán 120 rýže 150`.\n"
        "Pro návrat klepněte na „Zpět na hlavní menu“.",
        parse_mode="Markdown",
        reply_markup=EXIT_ONLY_KB,
    )

async def set_mode_breakfast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await set_meal_mode(update, context, "snídaně")

async def set_mode_lunch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await set_meal_mode(update, context, "oběd")

async def set_mode_dinner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await set_meal_mode(update, context, "večeře")

async def set_mode_snack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await set_meal_mode(update, context, "svačina")

async def handle_calorie_query(update, context):
    parts = (update.message.text or "").strip().split()
    start_idx = 1 if parts and parts[0].lower() in ("kcal", "kalorie") else 0
    pairs = parse_food_pairs_free(parts, start=start_idx)
    if not pairs:
        await update.message.reply_text(
            "Napište položky ve formátu: \n✅`potravina gramy`✅, \nnapř.: `kcal smažený sýr 100 párek 50`  \nnebo  bez prefixu kcal:\n`rýže 100`",
            parse_mode="Markdown"
        )
        return

    lines = ["📏 *Výpočet kalorií (bez uložení):*", ""]
    total = 0.0
    for food, grams in pairs:
        info = get_food_info(food, grams)
        if not info:
            lines.append(f"• ⚠️ `{food}` — údaje se nepodařilo najít.")
            continue
        total += info["kcal"]
        lines.append(
            f"• {info['food_name']} {grams} g = {info['kcal']:.1f} kcal "
            f"({info['protein']:.1f} bíl., {info['fat']:.1f} tuk., {info['carbs']:.1f} sach.)"
        )

    lines.append(f"\n🔥 Celkem: {total:.1f} kcal")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_daily_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = anonymize_user(update.effective_user.id)
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT meal_type, food, grams, kcal
            FROM meals
            WHERE user_id = ? AND date = CURRENT_DATE
            ORDER BY meal_type
        """, (user_id,)).fetchall()

    if not rows:
        await update.message.reply_text("📭 Zatím jsi dnes nic nezadal.")
        return

    reply_lines = ["📊 *Tvůj denní přehled:*"]
    total = 0.0
    current = None
    for r in rows:
        if r["meal_type"] != current:
            reply_lines.append(f"\n🍽️ {r['meal_type'].capitalize()}:")
            current = r["meal_type"]
        reply_lines.append(f"   • {r['food']} {r['grams']} g = {r['kcal']:.1f} kcal")
        total += r["kcal"]

    reply_lines.append(f"\n🔥 Celkem: {total:.1f} kcal")
    await update.message.reply_text("\n".join(reply_lines), parse_mode="Markdown")

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    if mode == "calories":
        return await handle_calorie_query(update, context)

    if mode == "pick_meal":
        return await update.message.reply_text(
            "🔽 Vyberte prosím z tlačítek níže, do kterého jídla chcete zapisovat.",
            reply_markup=MEAL_PICK_KB,
        )

    if mode == "meal":
        meal_type = context.user_data.get("meal_type")
        parts = (update.message.text or "").strip().split()
        pairs = parse_food_pairs_free(parts, start=0)  # без префикса
        if not pairs:
            return await update.message.reply_text(
                "⚠️ Napište prosím ve formátu: `potravina gramy`, \nnapř. `banán 120 rýže 150`.",
                parse_mode="Markdown",
                reply_markup=EXIT_ONLY_KB,
            )
        return await _save_meal(update, context, meal_type, pairs)

    user_msg = (update.message.text or "").strip()

    if not user_msg:
        await update.message.reply_text(
            "Prosím, vyberte jednu z možností v hlavním menu níže.",
            reply_markup=MAIN_KB,
        )
        return

    # user_msg = update.message.text
    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "Jsi výživový poradce. Odpovídej česky, stručně a přátelsky. Nezdrav se, dokud uživatel nezačne pozdravem."},
            {"role": "user", "content": user_msg}
        ],
        max_completion_tokens=200,
        temperature=1.0
    )
    await update.message.reply_text(completion.choices[0].message.content)