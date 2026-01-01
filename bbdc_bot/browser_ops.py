from bbdc_slot_finder.browser_login import record_requests
from bbdc_slot_finder import BbdcApi, UserSession
from bbdc_bot.logger import logger
from datetime import datetime
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    ForceReply,
)

from telegram.constants import ParseMode
from bbdc_bot.bbdc_bot import remove_job_if_exists


async def open_browser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context._chat_id
    job_removed = remove_job_if_exists("browser", context)

    if job_removed:
        update.message.reply_text("Opening browser... Previous camper cancelled.")
    if "client" in context.chat_data:
        session = context.chat_data["client"]
    else:
        config = context.chat_data["config"] = UserSession(chat_id)
        session = context.chat_data["client"] = BbdcApi(config)
    if hasattr(session, "_browser"):
        await session.close_browser()

    await session.init_playwright_browser(headless=False)

    return True


async def kill_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if "client" in context.chat_data:
        session: BbdcApi = context.chat_data["client"]
    await session.close_browser()


async def debug_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "client" in context.chat_data:
        session: BbdcApi = context.chat_data["client"]
        await session._browser_page.pause()


command_quit_browser = CommandHandler("quit_browser", kill_browser)
command_open_browser = CommandHandler("open_browser", open_browser)
command_pause_browser = CommandHandler("pause_browser", debug_browser)
