from telegram.ext import Application, CommandHandler, MessageHandler, filters
from configuration.config import TELEGRAM_BOT_TOKEN
from database.database import init_db
from handlers.handlers import *
def main():
    init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(
        filters.Text(["Denní přehled"]), handle_daily_summary)
    )

    app.add_handler(MessageHandler(
        filters.Text(["Týdenní přehled"]), handle_weekly_summary)
    )

    app.add_handler(MessageHandler(
        filters.Text(["Nastavit profil"]),enter_profile_setup)
    )

    app.add_handler(MessageHandler(
        filters.Text(["Počítat kalorie"]),
        enter_calorie_mode
    ))

    app.add_handler(MessageHandler(
        filters.Text(["Přidat do jídelníčku"]),
        enter_add_meal_menu
    ))

    app.add_handler(MessageHandler(filters.Text(["Snídaně"]), set_mode_breakfast))
    app.add_handler(MessageHandler(filters.Text(["Oběd"]), set_mode_lunch))
    app.add_handler(MessageHandler(filters.Text(["Večeře"]), set_mode_dinner))
    app.add_handler(MessageHandler(filters.Text(["Svačina"]), set_mode_snack))

    app.add_handler(MessageHandler(
        filters.Text(["Smazat poslední položku"]), handle_delete_last_meal)
    )

    app.add_handler(MessageHandler(
        filters.Text(["Zpět na hlavní menu"]),
        exit_to_main_menu
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    print("NutriBot is running (long polling)…")
    app.run_polling()

if __name__ == "__main__":
    main()
