from telegram.ext import Application, CommandHandler, MessageHandler, filters
from configuration.config import TELEGRAM_BOT_TOKEN
from database.database import init_db
from handlers.handlers import *
def main():
    init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"(?i)^\s*denní\s+přehled\s*$"), handle_daily_summary)
    )

    app.add_handler(MessageHandler(
        filters.Regex(r"(?i)^\s*týdenní\s+přehled\s*$"), handle_weekly_summary)
    )

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"(?i)^\s*počítat\s+kalorie\s*$"),
        enter_calorie_mode
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"(?i)^\s*přidat\s+do\s+jídelníčku\s*$"),
        enter_add_meal_menu
    ))

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^\s*snídaně\s*$"), set_mode_breakfast))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^\s*oběd\s*$"), set_mode_lunch))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^\s*večeře\s*$"), set_mode_dinner))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^\s*svačina\s*$"), set_mode_snack))

    app.add_handler(MessageHandler(
        filters.Regex(r"(?i)^\s*smazat\s+poslední\s+položku$\s*$"), handle_delete_last_meal)
    )

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(
            r"(?i)^\s*(?:↩︎[\s\u00A0]*)?Zpět[\s\u00A0]+na[\s\u00A0]+hlavní[\s\u00A0]+menu\s*$"),
        exit_to_main_menu
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^(kcal|kalorie)\b"),
        handle_calorie_query
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    print("🤖 NutriBot is running (long polling)…")
    app.run_polling()

if __name__ == "__main__":
    main()
