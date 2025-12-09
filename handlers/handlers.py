import hashlib

from openai import OpenAI
from telegram import ReplyKeyboardMarkup, KeyboardButton
from telegram import Update
from telegram.ext import ContextTypes

from configuration.config import OPENAI_API_KEY
from database.database import get_db_connection
from nutrition.nutrition import get_food_info, parse_food_pairs_free, parse_food_pairs_llm
from datetime import datetime, timedelta, date

client = OpenAI(api_key=OPENAI_API_KEY)

def anonymize_user(user_id: int) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Denní přehled"), KeyboardButton("Týdenní přehled")],
        [KeyboardButton("Počítat kalorie"), KeyboardButton("Přidat do jídelníčku"), KeyboardButton("Smazat poslední položku")],
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

CALORIES_EXIT_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Zpět na hlavní menu")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

MEAL_EXIT_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Smazat poslední položku")],
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
        "• Podívejte se na souhrn dne – tlačítkem „Denní přehled“, nebo na souhrn týdne – tlačítkem „Týdenní přehled“.\n\n"
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
            "⚠️ Napište položky ve formátu: \n✅`potravina gramy(ml,kusy)`✅, \nnapř. `banán 1 kus vařená rýže 150`.",
            parse_mode="Markdown"
        )
        return

    user_id = anonymize_user(update.effective_user.id)
    header = format_czech_date_header()

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
                f"• {info['food_name'].capitalize()} {grams} g = {info['kcal']:.1f} kcal "
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

    lines.insert(0, f"✅ Přidáno do '{meal_type}' - {header}:")
    lines.append(f"\n🔥 Celkem: {total_kcal:.1f} kcal")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
    )

async def handle_delete_last_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = anonymize_user(update.effective_user.id)

    with get_db_connection() as conn:
        row = conn.execute("""
            SELECT id, meal_type, food, grams, kcal
            FROM meals
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
        """, (user_id,)).fetchone()

        if not row:
            await update.message.reply_text(
                "⚠️ Nemám co smazat – žádná položka zatím není uložena.",
                reply_markup=MEAL_EXIT_KB,
            )
            return

        conn.execute("DELETE FROM meals WHERE id = ?", (row["id"],))
        conn.commit()

    await update.message.reply_text(
        "🗑️ Poslední položka byla smazána:\n"
        f"• {row['meal_type'].capitalize()}: {row['food']} {row['grams']} g "
        f"({row['kcal']:.1f} kcal)",
    )


async def enter_calorie_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "calories"
    await update.message.reply_text(
        "🔢 *Režim výpočtu kalorií*\n"
        "Pište potraviny a gramy(ml,kusy) na řádek, např.:\n✅`vařená rýže 100`✅  \nnebo  \n✅`banán 1 kus vařená rýže 150`✅.\n"
        "Pro ukončení klepni na „Zpět na hlavní nabídku“.",
        parse_mode="Markdown",
        reply_markup=CALORIES_EXIT_KB,
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
        f"🍽️ Zapisování do '*{meal_type}*' je aktivní.\n"
        "Napište položky ve formátu: \n✅`potravina gramy(ml,kusy)`✅, \nnapř. `banán 1 kus vařená rýže 150`.\n"
        "Pro návrat klepněte na „Zpět na hlavní menu“.",
        parse_mode="Markdown",
        reply_markup=MEAL_EXIT_KB,
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
    text = (update.message.text or "").strip()
    pairs = parse_food_pairs_llm(text)

    if not pairs:
        parts = text.split()
        start_idx = 1 if parts and parts[0].lower() in ("kcal", "kalorie") else 0
        pairs = parse_food_pairs_free(parts, start=start_idx)

    if not pairs:
        await update.message.reply_text(
            "Napište prosím, co chcete spočítat.\n"
            "Můžete použít přirozenou větu, např.:\n"
            "  ✅`Kolik kalorií má 60 g ovesné kaše a 250 ml kávy?`✅\n\n"
            "nebo jednoduchý formát:\n"
            "  ✅`vařená rýže 100 pečené kuře 150`✅\n"
            "  případně s prefixem `kcal`, např.:\n"
            "  ✅`kcal smažený sýr 100 párek 50`✅",
            parse_mode="Markdown"
        )
        return

    lines = ["📏 *Výpočet kalorií:*", ""]
    total = 0.0
    for food, grams in pairs:
        info = get_food_info(food, grams)
        if not info:
            lines.append(f"• ⚠️ `{food}` — údaje se nepodařilo najít.")
            continue
        total += info["kcal"]
        lines.append(
            f"• {info['food_name'].capitalize()} {grams} g = {info['kcal']:.1f} kcal "
            f"({info['protein']:.1f} bíl., {info['fat']:.1f} tuk., {info['carbs']:.1f} sach.)"
        )

    lines.append(f"\n🔥 Celkem: {total:.1f} kcal")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

MONTHS_GEN = [
    "ledna", "února", "března", "dubna", "května", "června",
    "července", "srpna", "září", "října", "listopadu", "prosince"
]

def format_czech_date(d: date) -> str:
    month_name = MONTHS_GEN[d.month - 1]
    return f"{d.day}. {month_name}"

def format_czech_date_header() -> str:
    today = datetime.now().date()
    return format_czech_date(today)

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
        await update.message.reply_text("📭 Zatím jste dnes nic nezadal.")
        return

    header = format_czech_date_header()

    reply_lines = [
        f"📊 *Váš denní přehled* - {header}:"
    ]
    total = 0.0
    current = None
    for r in rows:
        if r["meal_type"] != current:
            reply_lines.append(f"\n🍽️ {r['meal_type'].capitalize()}:")
            current = r["meal_type"]
        reply_lines.append(f"   • {r['food'].capitalize()} {r['grams']} g = {r['kcal']:.1f} kcal")
        total += r["kcal"]

    reply_lines.append(f"\n🔥 Celkem: {total:.1f} kcal")
    await update.message.reply_text("\n".join(reply_lines), parse_mode="Markdown")

async def handle_weekly_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = anonymize_user(update.effective_user.id)

    today = datetime.now().date()
    start_date = today - timedelta(days=6)

    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT date, meal_type, food, grams, kcal
            FROM meals
            WHERE user_id = ?
              AND date BETWEEN ? AND ?
            ORDER BY date, meal_type
        """, (user_id, start_date.isoformat(), today.isoformat())).fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 Za posledních 7 dní zatím nemáte žádné záznamy.",
            reply_markup=MAIN_KB,
        )
        return

    by_date = {}
    for r in rows:
        d_str = r["date"]      # očekává se formát 'YYYY-MM-DD'
        by_date.setdefault(d_str, []).append(r)

    reply_lines = ["📊 *Týdenní přehled (posledních 7 dní):*"]

    d = start_date
    while d <= today:
        d_str = d.isoformat()
        pretty_date = format_czech_date(d)

        day_rows = by_date.get(d_str, [])
        day_total = sum(r["kcal"] for r in day_rows) if day_rows else 0

        if day_rows:
            reply_lines.append(f"\n📅 *{pretty_date}* ({day_total:.1f} kcal)")
        else:
            reply_lines.append(f"\n📅 *{pretty_date}*")
            reply_lines.append("   📭 Nic nebylo zaznamenáno.")
            d += timedelta(days=1)
            continue

        current_meal = None
        for r in day_rows:
            if r["meal_type"] != current_meal:
                reply_lines.append(f"🍽️ {r['meal_type'].capitalize()}:")
                current_meal = r["meal_type"]

            reply_lines.append(
                f"   • {r['food']} {r['grams']} g = {r['kcal']:.1f} kcal"
            )

        d += timedelta(days=1)

    await update.message.reply_text(
        "\n".join(reply_lines),
        parse_mode="Markdown",
        reply_markup=MAIN_KB,
    )


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
        text = (update.message.text or "").strip()

        pairs = parse_food_pairs_llm(text)

        if not pairs:
            parts = text.split()
            pairs = parse_food_pairs_free(parts, start=0)

        if not pairs:
            return await update.message.reply_text(
                "⚠️ Napište prosím, co jste jedl(a). "
                "Můžete použít přirozenou větu \n(např. ✅`Dnes jsem měla pečené kuře 60 g a kávu 250 ml`✅)\n "
                "nebo formát `potravina gramy` \n(např. ✅`ovesná kaše 60 káva 250`✅).",
                parse_mode="Markdown",
                reply_markup=MEAL_EXIT_KB,
            )

        return await _save_meal(update, context, meal_type, pairs)

    user_msg = (update.message.text or "").strip()

    if not user_msg:
        await update.message.reply_text(
            "Prosím, vyberte jednu z možností v hlavním menu níže.",
            reply_markup=MAIN_KB,
        )
        return

    system_prompt = """
    Jste výživový poradce. Odpovídejte česky, stručně, profesionálně a přátelsky. 
    Nepoužívejte žádná oslovení typu "pane", "paní", "vážený", ani jiná osobní oslovení.
    Nepoužívejte ani pozdravy na začátku odpovědi, pokud uživatel sám nepozdraví.

    Vždy oslovujte uživatele zdvořile v jednotném čísle ("Vy"), ale bez jakéhokoli přímého oslovování.

    Odpovídejte pouze na dotazy týkající se výživy, jídelníčku, zdravého životního stylu, kalorií, živin nebo potravin.
    Pokud se dotaz netýká těchto témat, odpovězte laskavě, že na takové otázky nemůžete reagovat, protože jste výživový poradce.
    """

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_msg
            }
        ],
        max_completion_tokens=200,
        temperature=1.0
    )
    await update.message.reply_text(completion.choices[0].message.content)