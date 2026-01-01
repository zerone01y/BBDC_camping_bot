from bbdc_slot_finder import UserSession, BbdcApi
from bbdc_bot.logger import logger
import os, json, asyncio, datetime
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

CONFIRM, CANCEL_C, OPERATION = 3201, 3202, 3203

DEBUG = os.environ.get("BBDC_BOT_DEBUG", False)


# /start
async def start_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a predefined poll"""
    logger.info(f"Request for slot cancel from {update.effective_chat.id}")
    # config: UserSession = context.chat_data.get("config", None)

    config = context.chat_data.get("config", False)
    session = context.chat_data.get("client", False)
    if not config:
        await update.message.reply_text(
            "No active session found. /check for released slots first."
        )
        return ConversationHandler.END
    slots_data = config.scheduled
    slots_keys = set(slots_data.keys())
    logger.info(f"slots keys: {slots_keys}")
    if len(slots_keys) == 0:
        message = await update.effective_message.reply_text(
            "No slots scheduled at the moment."
        )
        return ConversationHandler.END

    if len(slots_keys) == 1:
        msg = "One slot available... "
        i = list(slots_keys)[0]
        msg += (
            f"{datetime.datetime.strptime(slots_data[i]['slotRefDate'][:10], '%Y-%m-%d').strftime('%m/%d %a')}, "
            f"S{slots_data[i]['sessionNo']} at {slots_data[i]['startTime']}, "
            f"${slots_data[i]['bookingCharge']}"
        )
        logger.info(msg)
        message = await update.effective_message.reply_text(msg)
        await process_canceling(update, context)
        return ConversationHandler.END
    else:
        await list_slots_to_cancel(update, context)
        return CONFIRM


async def list_slots_to_cancel(update, context):
    slots_list = context.chat_data["config"].scheduled
    config: UserSession = context.chat_data["config"]
    session: BbdcApi = context.chat_data.get("client", {})

    choices_short = lambda i: (
        f"{datetime.datetime.strptime(slots_list[i]['slotRefDate'][:10], '%Y-%m-%d').strftime('%m/%d %a')}, "
        f"S{slots_list[i]['sessionNo']} {slots_list[i]['startTime']}"
    )
    keys = [
        InlineKeyboardButton(choices_short(i), callback_data=str(i))
        for i in sorted(slots_list)
    ]

    keyboard = [keys[i : i + 2] for i in range(0, len(keys), 2)] + [
        [InlineKeyboardButton("Cancel", callback_data=CANCEL_C)]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"Which slots would you like to cancel? Total booked slots: {len(slots_list)}"

    message = await context.bot.send_message(
        context._chat_id,
        text=msg,
        reply_markup=reply_markup,
    )
    return CONFIRM


async def handle_cancel_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    config: UserSession = context.chat_data["config"]
    session: BbdcApi = context.chat_data.get("client", {})
    slots_data: dict = config.scheduled
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    if query.data == str(CANCEL_C):
        logger.info("Operation cancelled.")
        await query.edit_message_text(text=f"Operation canceled.")
        return ConversationHandler.END
    if query.data in slots_data.keys():
        i = query.data
        msg = "Slot to cancel: "
        msg += (
            f"{datetime.datetime.strptime(slots_data[i]['slotRefDate'][:10], '%Y-%m-%d').strftime('%m/%d %a')}, "
            f"S{slots_data[i]['sessionNo']} at {slots_data[i]['startTime']} - {slots_data[i]['endTime']}, "
            f"${slots_data[i]['bookingCharge']}"
        )

        keyboard = [
            [
                InlineKeyboardButton("Cancel", callback_data=CANCEL_C),
                InlineKeyboardButton("Confirm", callback_data=i),
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            msg,
            reply_markup=reply_markup,
        )
        return OPERATION
    else:
        logger.info("Operation cancelled: query data not valid")

        await query.edit_message_text(text=f"Operation failed.")
        return ConversationHandler.END


async def process_canceling(update, context):
    # slots_code: list of int
    # slots_list: {slots_code: dictionary of slots_data};
    config: UserSession = context.chat_data["config"]
    session: BbdcApi = context.chat_data.get("client", {})
    slots_list: dict = config.scheduled
    chat_id: int = context._chat_id
    if DEBUG and not context.chat_data.get("config", False):
        # if not DEBUG: there already should be config
        context.chat_data["config"] = UserSession(chat_id)
        session = context.chat_data["client"] = BbdcApi(config)
    query = update.callback_query
    await query.answer()
    i = query.data
    slotid, slot_type = slots_list[i]["bookingId"], slots_list[i]["dataType"]
    msg = await session.cancel_slot(slotid, slot_type)

    await query.edit_message_text(f"{msg}")
    return ConversationHandler.END


async def end_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Returns `ConversationHandler.END`, which tells the
    ConversationHandler that the conversation is over.
    """
    context.bot_data.clear()
    context.user_data.clear()
    if context.chat_data.get("book"):
        context.chat_data["book"].clear()
    logger.info("Conversation ends here.")
    await update.effective_message.reply_text(text=f"Operation canceled.")

    return ConversationHandler.END


# application.add_handler(CallbackQueryHandler(button, ))
# Add ConversationHandler to application that will be used for handling updates
cancel_slot_handler = ConversationHandler(
    entry_points=[
        CommandHandler("cancel_slot", start_cancel),
    ],
    #
    states={
        CONFIRM: [
            CallbackQueryHandler(
                handle_cancel_confirmation,
                "^(" + f"{CANCEL_C}" + "|\d{4}-\d{2}-\d{2}.+)$",
            ),
        ],
        OPERATION: [
            CallbackQueryHandler(process_canceling, "^(\d{4}-\d{2}-\d{2}.+)$"),
            CallbackQueryHandler(handle_cancel_confirmation, f"^({CANCEL_C})$"),
        ],
        CANCEL_C: [
            CallbackQueryHandler(
                end_conversation,
                "^" + str(CANCEL_C) + "$",
            )
        ],
    },
    fallbacks=[
        CommandHandler("cancel", end_conversation),
    ],
)
# application.add_handler(CallbackQueryHandler(button))
# Run the bot until the user presses Ctrl-C
