from bbdc_bot.logger import logger
from telegram import Update, ForceReply
from telegram.ext import (
    Application,
    CommandHandler,
)
from bbdc_slot_finder.config import load_config
from bbdc_bot import book_slot_handler, config_conv_handler
from bbdc_bot.conv_cancel_slots import cancel_slot_handler
from bbdc_bot.bbdc_bot import (
    command_camp,
    command_check,
    command_help,
    command_log,
    command_login,
    command_myschedule,
    command_start,
    command_unset,
)
from bbdc_bot.browser_ops import (
    command_quit_browser,
    command_open_browser,
    command_pause_browser,
)

CONFIG = load_config("config_bot.yaml")
TOKEN = CONFIG["telegram"]["token"]
ADMIN = CONFIG["telegram"].get("admin", [])

from warnings import filterwarnings
from telegram.warnings import PTBUserWarning

# filter PTBUserWarning:  PTBUserWarning: If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message. Read this FAQ entry to learn more about the per_* settings: https://github.com/python-telegram-bot/python-telegram-bot/wiki/Frequently-Asked-Questions#what-do-the-per_-settings-in-conversationhandler-do.
filterwarnings(
    action="ignore", message=r".*CallbackQueryHandler.*", category=PTBUserWarning
)


async def post_stop(context):
    for key in context.chat_data.keys():
        config = context.chat_data[key].get("config", None)
        session = context.chat_data[key].get("client", False)
        if session is not False:
            await session.close_client()

    print("stop")


def main() -> None:
    """Run bot."""
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler(["start"], command_start))
    application.add_handler(CommandHandler("login", command_login))
    application.add_handler(CommandHandler("help", command_help))
    application.add_handler(CommandHandler("log", command_log))
    application.add_handler(CommandHandler("myschedule", command_myschedule))
    application.add_handler(CommandHandler("check", command_check))
    application.add_handler(CommandHandler("camp", command_camp))
    application.add_handler(CommandHandler("unset", command_unset))
    application.add_handler(book_slot_handler)
    application.add_handler(config_conv_handler)
    application.add_handler(cancel_slot_handler)
    application.add_handler(command_quit_browser)
    application.add_handler(command_open_browser)
    application.add_handler(command_pause_browser)
    application.post_stop = post_stop
    application.run_polling(
        poll_interval=2,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
