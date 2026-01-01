from bbdc_slot_finder.api import UserSession, BbdcApi
from bbdc_slot_finder.async_playwright_browser_ops import select_slots, book_slots
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
import time
from telegram.constants import ParseMode

CONFIRM, CANCEL_BOOKING, CHOOSING = 3001, 3102, 3103
CAPTCHA, END = range(2)
TOTAL_VOTER_COUNT = 1

DEBUG = os.environ.get("BBDC_BOT_DEBUG", False)

"""
def get_debug_slots_list():
    with open("json-server/api-data/POST.json", "r") as f:
        reqs = json.load(f)
    data = reqs["bbdc-back-service-api-booking-c3practical-listC3PracticalSlotReleased"]
    slots_list = BbdcApi.parse_released_slots(data["data"])
    return slots_list
"""

# /start
async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a predefined poll"""
    logger.info(f"Request for booking from {update.effective_chat.id}")
    config: UserSession = context.chat_data.get("config", None)
    session: BbdcApi = context.chat_data.get("client", {})
    if DEBUG:
        if config is None:
            config = context.chat_data["config"] = UserSession(context._chat_id)
        if not session:
            session = context.chat_data["client"] = BbdcApi(config)
        slots_data = get_debug_slots_list()
        config.released_slots.update(slots_data)
    if not config:
        update.message.reply_text(
            "No active session found. /check for released slots first."
        )
        return ConversationHandler.END
    slots_data = config.released_slots
    slots_keys = set(slots_data.keys())
    logger.info(f"slots keys: {slots_keys}")
    if len(slots_keys) == 0:
        message = await update.effective_message.reply_text(
            "No slots available at the moment."
        )
        return ConversationHandler.END

    if len(slots_keys) == 1:
        msg = "One slot available... "
        i = list(slots_keys)[0]
        context.chat_data["book"] = {
            "slots": slots_data,
            "auto": context.chat_data["config"]
            .get("autobook", {})
            .get("auto_captcha", True),
        }
        msg += (
            f"{datetime.datetime.strptime(slots_data[i]['slot_date'], '%Y-%m-%d').strftime('%m/%d %a')}, "
            f"S{slots_data[i]['session']} at {slots_data[i]['start_time']}, "
            f"${slots_data[i]['total_fee']}"
        )
        logger.info(msg)
        message = await update.effective_message.reply_text(msg)
        await api_preprocess_booking(update, context)
        return ConversationHandler.END
    else:
        context.chat_data["book"] = {
            "slots": set(),
            "auto": context.chat_data["config"]
            .get("autobook", {})
            .get("auto_captcha", True),
        }
        await list_slots_to_book(update, context)
        return CHOOSING


async def list_slots_to_book(update, context):
    book = context.chat_data["book"]
    chosen_slots: set = book["slots"]
    config: UserSession = context.chat_data["config"]
    session: BbdcApi = context.chat_data.get("client", {})
    slots_list = config.released_slots
    query = update.callback_query
    if query:
        if len(query.data) == 17:
            if query.data in chosen_slots:
                chosen_slots.difference_update([query.data])
            elif query.data == "000000000-0000000":
                chosen_slots.update(slots_list.keys())
            else:
                chosen_slots.update([query.data])
    choices_short = lambda i: (
        f"{datetime.datetime.strptime(slots_list[i]['slot_date'], '%Y-%m-%d').strftime('%m/%d,%a')}"
        f",S{slots_list[i]['session']}"
    )
    choices_long = lambda i: (
        f"{datetime.datetime.strptime(slots_list[i]['slot_date'], '%Y-%m-%d').strftime('%m/%d-%a')}"
        f",S{slots_list[i]['session']}-{slots_list[i]['start_time']},"
        f"${slots_list[i]['total_fee']}"
    )
    keys = [
        InlineKeyboardButton(
            ("*" if i in chosen_slots else "") + choices_short(i), callback_data=str(i)
        )
        for i in sorted(slots_list)
    ] + [InlineKeyboardButton("All", callback_data="000000000-0000000")]

    keyboard = [keys[i : i + 2] for i in range(0, len(keys), 2)] + [
        [
            InlineKeyboardButton(i, callback_data=j)
            for (i, j) in zip(["Submit", "Cancel"], [CONFIRM, CANCEL_BOOKING])
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    account_bal = str(config.profile.get("accountBal", "null"))
    chosen_slots = sorted(list(chosen_slots))
    msg = f"Which slots would you like to book? Account Balance: {account_bal}." + (
        f"\nChosen:\n" + "\n".join(choices_long(i) for i in chosen_slots)
        if len(chosen_slots)
        else ""
    )
    if query:
        await query.edit_message_text(
            msg,
            reply_markup=reply_markup,
        )
    else:
        message = await context.bot.send_message(
            context._chat_id,
            text=msg,
            reply_markup=reply_markup,
        )
    return CHOOSING


async def handle_booking_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    if query.data == str(CANCEL_BOOKING):
        logger.info("Booking cancelled.")
        context.bot_data.clear()
        context.user_data.clear()
        await query.edit_message_text(text=f"Booking canceled.")
        return ConversationHandler.END
    elif query.data == str(CONFIRM):
        book: dict = context.chat_data["book"]
        if len(book["slots"]) == 0:
            await query.edit_message_text(text=f"Booking canceled.")
            return ConversationHandler.END
        if isinstance(book["slots"], set):
            slots_data = context.chat_data["config"].released_slots
            book["slots"] = {k: slots_data[k] for k in book["slots"]}
        logger.info("Booking request confirmed.")
        text = query.message.text_html
        await query.edit_message_text(text=text + "\nGot it.", parse_mode="HTML")
        # process_booking(update, context)

        status = await browser_book(update, context)
        return status


async def browser_book(update, context):
    book: dict = context.chat_data["book"]
    config: UserSession = context.chat_data["config"]
    session: BbdcApi = context.chat_data.get("client", {})
    slots_data: dict = book["slots"]
    chat_id: int = context._chat_id

    page = session._browser_page
    msg = f"Autobooking slots. Selecting slots..."
    message = await context.bot.send_message(chat_id=chat_id, text=msg)
    if book["all"]:
        success_flag = await select_slots(page, slots_data, select_all=True)
    else:
        success_flag = await select_slots(page, slots_data)
    await message.edit_text(text=f"{msg}: {success_flag}")
    if success_flag:
        counter = 1
        while counter <= 3:
            sucess, data = await book_slots(page)
            msg = "Finished! " if sucess else "Failed. "
            if not sucess:
                msg += data
            else:
                for slot in data["bookedPracticalSlotList"]:
                    msg += f'{slot["slotRefDate"]} {slot["slotRefName"]}: {slot["startTime"]}-{slot["endTime"]}\n'
                    msg += (
                        "Success!" if slot["success"] else f'Failed: {slot["message"]}'
                    )
                    msg += "\n"
                context.chat_data["book"].clear()
            await message.edit_text(msg)
            time.sleep(5)
            if (not sucess) and ("Incorrect Captcha" in msg):
                msg = "Attempting again..."
                message = await context.bot.send_message(chat_id=chat_id, text=msg)
                counter += 1
            else:
                return ConversationHandler.END


async def api_preprocess_booking(update, context):
    """Process booking information and handle slot booking logic asynchronously."""
    # slots_code: list of int
    # slots_list: {slots_code: dictionary of slots_data};
    book: dict = context.chat_data["book"]
    config: UserSession = context.chat_data["config"]
    session: BbdcApi = context.chat_data.get("client", {})
    slots_data: dict = book["slots"]
    chat_id: int = context._chat_id
    if DEBUG and not context.chat_data.get("config", False):
        # if not DEBUG: there should already have config
        context.chat_data["config"] = UserSession(chat_id)
        session = context.chat_data["client"] = BbdcApi(config)
    msg: str = f"Processing booking... Auto-mode={book['auto']}"
    logger.info(msg)
    message = await context.bot.send_message(chat_id=chat_id, text=msg)

    if config["autobook"].get("safe_mode", True):  # manual standard process
        # not auto-book: check availability again
        # sort slots into date-slots dict for clashed check
        msg = f"\nConfirming avaliability of slots..."
        await message.edit_text(text=msg)

        total_items: int = len(slots_data)
        slots_to_book: list = await session.api_update_clash_status(slots_data)
        encryptslotlist = [
            slots_data[i]["payload"]
            for i in slots_data
            if slots_data[i]["slot_id"] in slots_to_book
        ]
        confirmed_slots = len(slots_to_book)
        msg += f"({confirmed_slots:d}/{total_items})"
        logger.info(msg)
        await message.edit_text(text=msg)
    else:
        # not check for clashed status
        await message.edit_text("Skip updating clash status")
        encryptslotlist = [
            slots_data[i]["payload"] for i in slots_data
        ]  # [{...}, {...}]
        slots_to_book = [slots_data[i]["slot_id"] for i in slots_data]  # [id1, id2,...]

    if slots_to_book:
        book_payload = {
            "courseType": config.profile["courseType"],
            "insInstructorId": "",
            "subVehicleType": None,
            "instructorType": "",
            "slotIdList": slots_to_book,
            "encryptSlotList": encryptslotlist,
        }
        context.chat_data["book"]["payload"] = book_payload
        return await api_request_for_captcha(update, context)
    else:
        await message.edit_text("No slots to book...")
        return ConversationHandler.END
    # get captcha


async def api_request_for_captcha(update, context):
    chat_id = context._chat_id
    config: UserSession = context.chat_data["config"]
    session: BbdcApi = context.chat_data.get("client", {})

    book_data: dict = context.chat_data["book"]

    logger.info("request bbdc api for captcha")
    await context.bot.send_message(chat_id=chat_id, text="Requesting for captcha")
    try:
        img, captcha_json = await session.get_booking_captcha_image(book_data["auto"])
    except Exception as e:
        logger.info(f"Error: {e}")
        return ConversationHandler.END
    context.chat_data["book"]["payload"].update(captcha_json)
    if not book_data["auto"]:
        logger.info("Manual booking mode...")
        message_photo = await context.bot.send_photo(
            chat_id=chat_id,
            photo=img,
            caption="Solve the captcha:",
            reply_markup=ForceReply(),
        )
        context.chat_data["book"]["captcha_photo"] = message_photo
        return CAPTCHA
    else:
        await send_book_requests(update, context)
        return ConversationHandler.END


async def send_book_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # if it's message handler
    book: dict = context.chat_data["book"]
    config: UserSession = context.chat_data["config"]
    session: BbdcApi = context.chat_data.get("client", {})
    chat_id = context._chat_id

    if not book.get("counter", False):
        book["counter"] = 1
    else:
        book["counter"] += 1
    if getattr(update, "message", False):  # receive captcha
        user = update.message.from_user
        chat_id = update.message.chat_id
        if not update.message.text.startswith("/"):  # /check instead of booking
            captcha = update.message.text
            logger.info(f"Received captcha: {captcha}")
            book["payload"]["verifyCodeValue"] = captcha
    # else (auto mode), update is from callback query; captcha is already filled in
    try:
        logger.info(f"Send request to book...")

        message = await context.bot.send_message(
            chat_id=chat_id, text=f"Calling book service"
        )
        success, res = await session.book_slots(book["payload"], sleep=2)
    except:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Fail to book slots.",
        )
        return ConversationHandler.END

    if success:
        msg = "Book information:\n"
        for slot in res["bookedPracticalSlotList"]:
            msg += f'{slot["slotRefDate"]} {slot["slotRefName"]}: {slot["startTime"]}-{slot["endTime"]}\n'
            msg += "Success!" if slot["success"] else f'Failed: {slot["message"]}'
            msg += "\n"
        await message.edit_text(text=msg)
        context.chat_data["book"].clear()
        return ConversationHandler.END
    else:
        logger.warning(res)
        book = context.chat_data["book"]
        chat_id = context._chat_id
        if "Incorrect Captcha" in res and book["counter"] < 2:
            if not book["auto"]:
                await context.chat_data["book"]["captcha_photo"].delete()
                message_msg = context.chat_data["book"]["captcha_msg"]
                await message_msg.edit_text(f"{res}. Please try again.")
            else:
                await message.edit_text(text=f"{res}. Attempting again...")
            await asyncio.sleep(2)
            await api_request_for_captcha(update, context)
            return CAPTCHA

        else:
            with open("logs/log.json", "a+") as f:
                json.dump(res, f)
    await context.bot.send_message(chat_id=chat_id, text=f"Booking unsuccessful: {res}")
    return ConversationHandler.END


async def cancel_booking_process(
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
    await update.effective_message.reply_text(text=f"Operation canceled.")

    return ConversationHandler.END


# application.add_handler(CallbackQueryHandler(button, ))
# Add ConversationHandler to application that will be used for handling updates
book_slot_handler = ConversationHandler(
    entry_points=[
        CommandHandler("book", start_booking),
        #
        CallbackQueryHandler(
            handle_booking_confirmation, f"^({CONFIRM}|{CANCEL_BOOKING})$"
        ),
    ],
    states={
        CHOOSING: [
            CallbackQueryHandler(list_slots_to_book, r"^(\d{9}-\d{7})$"),
            CallbackQueryHandler(
                handle_booking_confirmation, f"^({CONFIRM}|{CANCEL_BOOKING})$"
            ),
        ],
        CONFIRM: [
            CallbackQueryHandler(
                handle_booking_confirmation, f"^{CONFIRM}|{CANCEL_BOOKING}$"
            )
        ],
        CAPTCHA: [
            MessageHandler(
                filters.Regex("^([A-z0-9]{4,6})$"),
                send_book_requests,
            ),
        ],
        CANCEL_BOOKING: [
            CallbackQueryHandler(
                cancel_booking_process,
                "^" + str(CANCEL_BOOKING) + "$",
            )
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_booking_process),
    ],
)
# application.add_handler(CallbackQueryHandler(button))
# Run the bot until the user presses Ctrl-C
