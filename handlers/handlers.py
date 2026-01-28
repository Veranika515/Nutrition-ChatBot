import hashlib

from openai import OpenAI
from telegram import ReplyKeyboardMarkup, KeyboardButton
from telegram import Update
from telegram.ext import ContextTypes

from configuration.config import OPENAI_API_KEY
from database.database import get_db_connection, upsert_profile, set_show_targets, get_profile
from nutrition.nutrition import get_food_info, parse_food_pairs_free, parse_food_pairs_llm, calculate_targets
from datetime import datetime, timedelta, date

client = OpenAI(api_key=OPENAI_API_KEY)

def anonymize_user(user_id: int) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Nastavit profil")],
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

SEX_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Muž"), KeyboardButton("Žena")],
        [KeyboardButton("Zrušit")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

ACTIVITY_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Sedavá"), KeyboardButton("Lehká")],
        [KeyboardButton("Střední"), KeyboardButton("Vysoká")],
        [KeyboardButton("Zrušit")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

GOAL_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Hubnout"), KeyboardButton("Udržovat"), KeyboardButton("Nabírat")],
        [KeyboardButton("Zrušit")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

CANCEL_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton("Zrušit")]],
    resize_keyboard=True,
    one_time_keyboard=False,
)

TARGETS_OPTIN_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton("Ano"), KeyboardButton("Ne")]],
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
        "• Rychle spočítejte kalorie – klepněte na tlačítko „Počítat kalorie“.\n"
        "• Přidejte do dnešního jídelníčku to, co jste snědl(a) – klepněte na „Přidat do jídelníčku“.\n"
        "• Podívejte se na souhrn dne – tlačítkem „Denní přehled“, nebo na souhrn týdne – tlačítkem „Týdenní přehled“.\n\n"
        "• Nastavte si osobní cíle (kalorie a makroživiny) pomocí vědeckých výpočtů – tlačítkem „Nastavit profil“.\n\n"
        "💬 A pokud máte otázky týkající se výživy nebo zdravého životního stylu, jednoduše se zeptejte – rád Vám odpovím!",

    parse_mode="Markdown",
        reply_markup=MAIN_KB,
    )

def get_today_kcal_sum(user_id: str) -> float:
    with get_db_connection() as conn:
        r = conn.execute(
            "SELECT COALESCE(SUM(kcal), 0) FROM meals WHERE user_id = ? AND date = CURRENT_DATE",
            (user_id,),
        ).fetchone()
    return float(r[0]) if r else 0.0

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

    prof = get_profile(user_id)
    if prof and prof["show_targets"] == 1:
        target = float(prof["target_calories"])
        eaten = get_today_kcal_sum(user_id)
        pct = (eaten / target * 100) if target > 0 else 0

        if eaten <= target:
            balance_text = f"Zbývá: {target - eaten:.0f} kcal"
        else:
            balance_text = f"⚠️ Nad limit o: {eaten - target:.0f} kcal"

        await update.message.reply_text(
            f"📌 Dnes: {eaten:.0f} / {target:.0f} kcal ({pct:.0f}%)\n"
            f"{balance_text}",
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
        "Pro ukončení klepněte na „Zpět na hlavní nabídku“.",
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
            "  ✅`vařená rýže 100 pečené kuře 150`✅",
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
                    ORDER BY 
                        CASE meal_type
                            WHEN 'snídaně' THEN 1
                            WHEN 'svačina' THEN 2
                            WHEN 'oběd' THEN 3
                            WHEN 'večeře' THEN 4
                            ELSE 5
                        END
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

    prof = get_profile(user_id)
    if prof and prof["show_targets"] == 1:
        target = float(prof["target_calories"])
        eaten = get_today_kcal_sum(user_id)
        pct = (eaten / target * 100) if target > 0 else 0

        if eaten <= target:
            balance_text = f"Zbývá: {target - eaten:.0f} kcal"
        else:
            balance_text = f"⚠️ Nad limit o: {eaten - target:.0f} kcal"

        reply_lines.append("")
        reply_lines.append(
            f"📌 Cíl: {target:.0f} kcal | "
            f"Snědeno: {eaten:.0f} kcal ({pct:.0f}%) | "
        )
        reply_lines.append(balance_text)
    await update.message.reply_text("\n".join(reply_lines), parse_mode="Markdown")

async def handle_weekly_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = anonymize_user(update.effective_user.id)

    today = datetime.now().date()
    start_date = today - timedelta(days=6)

    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT date, meal_type, food, grams, kcal
            FROM meals
            WHERE user_id = ? AND date BETWEEN ? AND ?
            ORDER BY date, 
                CASE meal_type
                    WHEN 'snídaně' THEN 1
                    WHEN 'svačina' THEN 2
                    WHEN 'oběd' THEN 3
                    WHEN 'večeře' THEN 4
                    ELSE 5
                END
        """, (user_id, start_date.isoformat(), today.isoformat())).fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 Za posledních 7 dní zatím nemáte žádné záznamy.",
            reply_markup=MAIN_KB,
        )
        return

    by_date = {}
    for r in rows:
        d_str = r["date"]
        by_date.setdefault(d_str, []).append(r)

    reply_lines = ["📊 *Týdenní přehled (posledních 7 dní):*"]

    prof = get_profile(user_id)
    show = prof and prof["show_targets"] == 1
    target = float(prof["target_calories"]) if show else None

    d = start_date
    while d <= today:
        d_str = d.isoformat()
        pretty_date = format_czech_date(d)

        day_rows = by_date.get(d_str, [])
        day_total = sum(r["kcal"] for r in day_rows) if day_rows else 0

        day_pct = None
        day_status = None
        if show and day_rows and target and target > 0:
            day_pct = (day_total / target) * 100

            if day_pct < 85:
                day_status = "Nesplněno ❌"
            elif day_pct <= 105:
                day_status = "Splněno ✅"
            else:
                day_status = "Překročeno ⚠️"

        if day_rows:
            line = f"\n📅 *{pretty_date}* ({day_total:.1f} kcal)"
            if day_pct is not None:
                line += f" | {day_pct:.0f}% | {day_status}"
            reply_lines.append(line)
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

async def enter_profile_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "set_profile_1"
    context.user_data["profile"] = {}

    await update.message.reply_text(
        "⚠️ *Upozornění / Disclaimer*\n\n"
        "Doporučení nejsou lékařská rada. Výsledky jsou pouze orientační odhad "
        "na základě výpočtových formulí (Mifflin–St Jeor, PAL).\n\n"
        "Pokračujeme nastavením profilu.\n\n"
        "Krok 1/6: Pohlaví (Muž / Žena):",
        reply_markup=SEX_KB,
        parse_mode="Markdown",
    )

async def handle_profile_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = anonymize_user(update.effective_user.id)
    text = (update.message.text or "").strip()
    if text == "Zrušit":
        context.user_data["mode"] = None
        context.user_data.pop("profile", None)
        return await update.message.reply_text(
            "❌ Nastavení profilu zrušeno.",
            reply_markup=MAIN_KB
        )
    mode = context.user_data.get("mode")
    profile = context.user_data.get("profile", {})

    if mode == "set_profile_1":
        if text not in ("Muž", "Žena"):
            return await update.message.reply_text("Prosím zvolte *Muž* nebo *Žena*.", reply_markup=SEX_KB, parse_mode="Markdown")
        profile["sex"] = text
        context.user_data["profile"] = profile
        context.user_data["mode"] = "set_profile_2"
        return await update.message.reply_text(
            "Krok 2/6: Věk (Zadejte v letech):",
            reply_markup=CANCEL_KB
        )

    if mode == "set_profile_2":
        try:
            age = int(text)
            if age <= 0 or age > 120:
                raise ValueError
        except ValueError:
            return await update.message.reply_text("Prosím zadejte věk jako číslo (např. 32).")
        profile["age"] = age
        context.user_data["profile"] = profile
        context.user_data["mode"] = "set_profile_3"
        return await update.message.reply_text(
            "Krok 3/6: Výška (Zadejte v cm):",
            reply_markup=CANCEL_KB
        )

    if mode == "set_profile_3":
        try:
            height = float(text.replace(",", "."))
            if height <= 50 or height > 250:
                raise ValueError
        except ValueError:
            return await update.message.reply_text("Prosím zadejte výšku v cm jako číslo (např. 168).")
        profile["height_cm"] = height
        context.user_data["profile"] = profile
        context.user_data["mode"] = "set_profile_4"
        return await update.message.reply_text(
            "Krok 4/6: Váha (Zadejte v kg):",
            reply_markup=CANCEL_KB
        )

    if mode == "set_profile_4":
        try:
            weight = float(text.replace(",", "."))
            if weight <= 20 or weight > 400:
                raise ValueError
        except ValueError:
            return await update.message.reply_text("Prosím zadejte váhu v kg jako číslo (např. 70.5).")
        profile["weight_kg"] = weight
        context.user_data["profile"] = profile
        context.user_data["mode"] = "set_profile_5"
        return await update.message.reply_text(
            "Krok 5/6: Úroveň fyzické aktivity\n\n"
            "Vyberte možnost, která se nejvíce blíží Vašemu běžnému životnímu stylu:\n\n"
            "• Sedavá – převážně sedavá práce, minimum pohybu, žádný nebo téměř žádný sport\n"
            "• Lehká – lehký pohyb (procházky), občasná fyzická aktivita 1–2× týdně\n"
            "• Střední – pravidelná fyzická aktivita nebo sport 3–4× týdně\n"
            "• Vysoká – fyzicky náročná práce nebo intenzivní sport téměř každý den\n\n"
            "Jedná se o orientační odhad.",
            reply_markup=ACTIVITY_KB,
        )

    if mode == "set_profile_5":
        if text not in ("Sedavá", "Lehká", "Střední", "Vysoká"):
            return await update.message.reply_text("Prosím vyberte aktivitu z tlačítek.", reply_markup=ACTIVITY_KB)
        profile["activity"] = text
        context.user_data["profile"] = profile
        context.user_data["mode"] = "set_profile_6"
        return await update.message.reply_text(
            "Krok 6/6: Cíl. Co je Vaše priorita? Hubnout / Udržovat / Nabírat",
            reply_markup=GOAL_KB,
        )

    if mode == "set_profile_6":
        if text not in ("Hubnout", "Udržovat", "Nabírat"):
            return await update.message.reply_text("Prosím vyberte cíl z tlačítek.", reply_markup=GOAL_KB)

        profile["goal"] = text
        context.user_data["profile"] = profile

        targets = calculate_targets(
            sex=profile["sex"],
            age=profile["age"],
            height_cm=profile["height_cm"],
            weight_kg=profile["weight_kg"],
            activity=profile["activity"],
            goal=profile["goal"],
        )

        upsert_profile(user_id, profile, targets)

        context.user_data["mode"] = None

        await update.message.reply_text(
            "✅ Profil nastaven a cíle vypočítány! Zobrazuji výsledek...\n\n"
            "*Váš osobní plán (Vědecký odhad)*\n"
            f"Na základě Vašich dat a cíle *{profile['goal'].upper()}* Vám bot doporučuje:\n\n"
            f"🍽️ Cílové Kalorie: *{targets['calories']} kcal* denně\n"
            f"💪 Bílkoviny: *{targets['protein_g']} g*\n"
            f"🧈 Tuky: *{targets['fat_g']} g*\n"
            f"🍞 Sacharidy: *{targets['carbs_g']} g*\n\n"
            "Tato čísla jsou uložena jako Vaše denní cíle.",
            reply_markup=MAIN_KB,
            parse_mode="Markdown",
        )

        context.user_data["mode"] = "profile_optin"

        return await update.message.reply_text(
            "Chcete zobrazovat průběh cíle?\n"
            "(kolik jste snědl(a) a kolik zbývá)",
            reply_markup=TARGETS_OPTIN_KB
        )


async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")

    if mode == "profile_optin":
        text = (update.message.text or "").strip()
        user_id = anonymize_user(update.effective_user.id)

        if text not in ("Ano", "Ne"):
            return await update.message.reply_text(
                "Prosím vyberte: Ano / Ne",
                reply_markup=TARGETS_OPTIN_KB
            )

        set_show_targets(user_id, enabled=(text == "Ano"))
        context.user_data["mode"] = None

        return await update.message.reply_text(
            "✅ Nastavení uloženo.",
            reply_markup=MAIN_KB
        )

    if mode and mode.startswith("set_profile_"):
        return await handle_profile_flow(update, context)

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