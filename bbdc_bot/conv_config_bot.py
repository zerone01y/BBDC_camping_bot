from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    ForceReply,
)
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bbdc_bot.logger import logger
from bbdc_slot_finder.api import UserSession, BbdcApi
import json, datetime
from dateutil.relativedelta import relativedelta

UPDATE_CONFIG, SET_MONTH, SET_AUTOBOOK, SAVE_CONFIG, SET_AUTH, FIVE, TYPING = range(7)
SESSIONS = list(range(2001, 2009))

CONFIRM, CANCEL_CONFIG = 1001, 1002
TIMES = [
    "07:30-09:10",
    "09:20-11:00",
    "11:30-13:10",
    "13:20-15:00",
    "15:20-17:00",
    "17:10-18:50",
    "19:20-21:20",
    "21:10-22:50",
]


# /config
async def set_config(update, context):
    chat_id = update.effective_chat.id
    logger.info(f"Received set_config_request from {chat_id}.")

    query = update.callback_query

    config = context.chat_data.get("config", False)
    session = context.chat_data.get("client", False)
    if query:
        await query.answer()
    else:
        try:
            if not config:
                config = context.chat_data["config"] = UserSession(chat_id)
            if not session:
                session = context.chat_data["client"] = BbdcApi(config)
        except NameError:
            await update.message.reply_text("Ooops! User not found.")
            return ConversationHandler.END

    text = "Client status: \n"
    text += f"Stopped: {session.stop}\n"
    text += f"Browser running: {hasattr(session, '_browser')}\n"
    text += f"Browser page: {hasattr(session, '_browser_page')}\n"
    if hasattr(session, "_browser_page"):
        text += f"page url: {session._browser_page.url}\n"

    # bbdc account username and password

    keyboard = [
        [
            InlineKeyboardButton("Month", callback_data=str(SET_MONTH)),
            InlineKeyboardButton("AutoBook", callback_data=str(SET_AUTOBOOK)),
            InlineKeyboardButton("Authentication", callback_data=str(SET_AUTH)),
        ],
        [
            InlineKeyboardButton("Save changes", callback_data=str(SAVE_CONFIG)),
            InlineKeyboardButton("Cancel", callback_data=str(CANCEL_CONFIG)),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(
            text + f"Choose a configuration section: ",
            reply_markup=reply_markup,
        )
    else:
        await context.bot.send_message(
            chat_id,
            text + f"Loading configuration...Choose a configuration section:",
            reply_markup=reply_markup,
        )
    return UPDATE_CONFIG


async def set_month(update, context):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    current_months = context.chat_data["config"]["month"]

    if len(query.data) == 6:
        dt = int(query.data)
        if dt in current_months:
            current_months.remove(dt)
        else:
            current_months.append(dt)

    check_mark = "✔️"
    cross_mark = "✖️"
    candidates = [(datetime.date.today() + relativedelta(months=i)) for i in range(8)]
    buttons = [
        [
            InlineKeyboardButton(
                (
                    check_mark
                    if (int(i.strftime("%Y%m")) in current_months)
                    else cross_mark
                )
                + i.strftime("%Y%m"),
                callback_data=i.strftime("%Y%m"),
            )
        ]
        for i in candidates
    ] + [[InlineKeyboardButton("Back", callback_data=str(UPDATE_CONFIG))]]
    reply_markup = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(
        f"Camp for the following months: ",
        reply_markup=reply_markup,
    )
    logger.debug("trigger set_month")
    return SET_MONTH


async def set_autobook(update, context):
    logger.debug("trigger autobook config")
    query = update.callback_query
    await query.answer()
    autobook = context.chat_data["config"]["autobook"]

    if len(query.data) > 1:
        slot = query.data
        autobook[slot] = bool(1 - autobook[slot])

    check_mark = "✔️"
    cross_mark = "✖️"
    # advance or trysell
    buttons = [
        [
            InlineKeyboardButton(
                (check_mark if autobook[i] else cross_mark) + i, callback_data=str(i)
            )
            for i in ["advance", "trysell"]
        ],
        [
            InlineKeyboardButton(
                (check_mark if autobook[i] else cross_mark) + i,
                callback_data=i,
            )
            for i in [
                "Ding",
            ]
        ]
        + [
            InlineKeyboardButton("trysell_session", callback_data=str(FIVE)),
        ],
        [
            InlineKeyboardButton("Back", callback_data=str(UPDATE_CONFIG)),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(
        f"Automatically book slots for: \n[Advance]: more than 48 hours; \n[Try-sell]: within 48 hours; \n"
        "Choose the sessions booked automatically if trysell is enabled.",
        reply_markup=reply_markup,
    )
    return SET_AUTOBOOK


async def set_autobook_sessions(update, context):
    logger.debug("trigger autobook try-sell session selection")
    query = update.callback_query
    await query.answer()
    sessions = context.chat_data["config"]["trysell_session"]

    if len(query.data) == 4:
        if query.data[-1] in sessions:
            sessions.remove(query.data[-1])
        else:
            sessions.append(query.data[-1])

    check_mark = "✔️"
    cross_mark = "✖️"
    buttons = [
        [
            InlineKeyboardButton(
                (check_mark if str(i)[-1] in sessions else cross_mark)
                + "Session "
                + str(i)[-1]
                + " "
                + j,
                callback_data=str(i),
            )
        ]
        for i, j in zip(SESSIONS, TIMES)
    ] + [[InlineKeyboardButton("Back", callback_data=str(UPDATE_CONFIG))]]
    reply_markup = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(
        f"Allow booking the following try-sell sessions: ",
        reply_markup=reply_markup,
    )
    logger.debug("trigger set_trysell_sessions")
    return FIVE


async def set_auth(update, context):
    logger.debug("trigger auth")
    query = update.callback_query
    if query:
        await query.answer()
        if query.data == str(SET_AUTH):
            context.chat_data["CURRENTITEM"] = "cookie"
            await query.message.delete()
            await context.bot.send_message(
                chat_id=context._chat_id, text=f"Cookie is:", reply_markup=ForceReply()
            )
        return TYPING
    elif context.chat_data["CURRENTITEM"] == "cookie":
        context.chat_data["CURRENTITEM"] = "jsessionid"
        await update.message.reply_text(f"jsessionid is:", reply_markup=ForceReply())
        return TYPING
    else:
        chat_id = context._chat_id
        await update.message.reply_text("Authentication info saved.")
        return await save_config(update, context)


async def save_config(update, context):
    query = update.callback_query
    if query:
        await query.answer()
    context.chat_data["config"].save()
    if query:
        await query.edit_message_text(f"Configuration saved. ")
    logger.debug("trigger save_config")
    return ConversationHandler.END


async def accept_auth_input(update, context):
    # query = update.callback_query
    # await query.answer()
    data = update.message.text
    current_item = context.chat_data["CURRENTITEM"]
    context.chat_data["config"].headers[current_item] = data
    if current_item == "cookie":
        try:
            cookies = data.split("; ")
            auth = [i for i in cookies if i.startswith("bbdc-token")][0]
            auth = auth.split("=")[1].replace("%20", " ")
            context.chat_data["config"].headers["authorization"] = auth
        except:
            update.message.reply_text(f"{current_item} is in wrong pattern...")
    return await set_auth(update, context)


async def cancel_config_process(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Returns `ConversationHandler.END`, which tells the
    ConversationHandler that the conversation is over.
    """
    context.bot_data.clear()
    context.user_data.clear()
    if context.chat_data.get("book"):
        context.chat_data["book"].clear()
    logger.info("Conversation ends here.")
    query = update.callback_query
    if query:
        await query.edit_message_text(text=f"Operation canceled.")
    else:
        await update.effective_message.reply_text(text=f"Operation canceled.")

    return ConversationHandler.END


config_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("config", set_config)],
    states={
        UPDATE_CONFIG: [
            CallbackQueryHandler(set_month, pattern="^" + str(SET_MONTH) + "$"),
            CallbackQueryHandler(set_autobook, pattern="^" + str(SET_AUTOBOOK) + "$"),
            CallbackQueryHandler(save_config, pattern="^" + str(SAVE_CONFIG) + "$"),
            CallbackQueryHandler(set_auth, pattern="^" + str(SET_AUTH) + "$"),
            CallbackQueryHandler(
                cancel_config_process, pattern="^" + str(CANCEL_CONFIG) + "$"
            ),
        ],
        SET_MONTH: [
            CallbackQueryHandler(set_month, pattern="^\d{6}$"),
            CallbackQueryHandler(set_config, pattern=f"^{UPDATE_CONFIG}$"),
        ],
        SET_AUTOBOOK: [
            CallbackQueryHandler(
                set_autobook, pattern="^(advance|trysell|auto_captcha|safe_mode|ding)$"
            ),
            CallbackQueryHandler(set_config, pattern=f"^{UPDATE_CONFIG}$"),
            CallbackQueryHandler(set_autobook_sessions, pattern=f"^{FIVE}$"),
        ],
        FIVE: [
            CallbackQueryHandler(
                set_autobook_sessions,
                pattern=f"^(" + "|".join(str(i) for i in SESSIONS) + ")$",
            ),
            CallbackQueryHandler(set_config, pattern=f"^{UPDATE_CONFIG}$"),
        ],
        TYPING: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                accept_auth_input,
            ),
        ],
        SET_AUTH: [
            CallbackQueryHandler(set_auth, pattern="^" + str(SET_AUTH) + "$"),
        ],
        CANCEL_CONFIG: [
            CommandHandler("cancel", cancel_config_process),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_config_process),
    ],
)
