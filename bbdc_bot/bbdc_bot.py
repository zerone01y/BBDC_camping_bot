from bbdc_bot.logger import logger
import datetime
from telegram import Update, ForceReply
from telegram.ext import (
    ContextTypes,
)
from bbdc_slot_finder import (
    load_config,
    UserSession,
    BbdcApi,
    start_browser,
    TokenExpireError,
)
from bbdc_bot.conv_book_slots import (
    get_debug_slots_list,
    browser_book,
)
from bbdc_bot.conv_config_bot import config_conv_handler
import os, json


DEBUG = os.environ.get("BBDC_BOT_DEBUG", False)
if DEBUG:
    pass
    # use historical posted requests to simulate the API responses
    # with open("json-server/api-data/POST.json", "r") as f:
    #     REQS = json.load(f)


CONFIG = load_config("config_bot.yaml")
TOKEN = CONFIG["telegram"]["token"]
ADMIN = CONFIG["telegram"].get("admin", [])


async def command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    logger.info(f"Received update request from {chat_id}.")
    try:
        config = context.chat_data["config"] = UserSession(chat_id)
        if not config._client:
            session = context.chat_data["client"] = BbdcApi(config)
    except NameError as e:
        await update.message.reply_text("Ooops! User not found.")
        return
    msg = "Profile found!"
    if config.profile:
        msg += f"\nCourse type: {config.profile['courseType']}"
        msg += f"\nBalance: {config.profile['accountBal']}"
    await update.message.reply_text(msg)
    return


# /help
async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends explanation on how to use the bot."""
    if not context.chat_data.get("config", False):
        # Send message with text and appended InlineKeyboard
        await update.message.reply_text("Ooops cannot find your profile.")
    else:
        await update.message.reply_text(
            "Profile found! \n"
            + "Check slots once with /check,\n"
            + "Or camp with '/camp <x>' to check slots repeatedly every <x> seconds.\n"
            + "Unset the camping schedule with /unset.\nIf token expired, try /login. \n"
        )


# /login
async def command_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    message = await update.message.reply_text("Sign in request received...")
    if not context.chat_data.get("config", False):
        try:
            config = context.chat_data["config"] = UserSession(chat_id)
            if not config._client:
                session = context.chat_data["client"] = BbdcApi(config)
        except:
            await update.message.edit_text("Ooops! User not found.")
            return
    else:
        session: BbdcApi = context.chat_data.get("client", None)
        if hasattr(session, "_browser"):
            await session.close_client()
    headless = False
    force_login = False
    if context.args:
        if context.args[0] == "headless":
            headless = True
        if "f" in context.args:
            force_login = True
    status = False
    try:
        status = await start_browser(
            context.chat_data["config"],
            directory=f"user/{chat_id}",
            headless=headless,
            refresh_token=True,
            keep_browser=False,
        )
        if status:
            await context.chat_data["config"].update_auth(force_update=True)
            await message.edit_text("Successfully logged in!")
        else:
            await message.edit_text("Log in failed!")

    except Exception as e:
        logger.error(e)
        await message.edit_text(f"Log in failed...{e}")


def display_slot(slot):
    message = f"""
Slot Available!
ID: {slot['slots_code']}
Date: {datetime.datetime.strptime(slot['slot_date'], '%Y-%m-%d').strftime('%Y-%m-%d (%a)')}
Session {slot["session"]}: {slot["start_time"]}-{slot["end_time"]}
Total Fee: {slot["total_fee"]}
"""
    return message


async def command_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.debug("Checking slots...")
    chat_id = update.effective_chat.id
    if not context.chat_data.get("config", False):
        try:
            config = context.chat_data["config"] = UserSession(chat_id)
            if not config._client:
                session = context.chat_data["client"] = BbdcApi(config)
                await session.init_playwright_browser()

        except NameError as e:
            await update.message.reply_text("Ooops! User not found.")
            return
    config = context.chat_data["config"]
    session: BbdcApi = context.chat_data.get("client", False)

    try:
        message = await update.message.reply_text("Checking...")
        if not (hasattr(session, "_browser") or session.stop):
            # if browser not exists, and session not stopped:
            await session.init_playwright_browser()
        async for new_slots in session.scan_slots():
            if len(new_slots) and config["autobook"]["Ding"]:
                os.system("say -v bubbles Ding")
            for slot, item in new_slots.items():
                if slot not in config.released_slots:
                    msg = display_slot(item)
                    logger.info(msg)
                    await context.bot.send_message(chat_id=chat_id, text=msg)
                else:
                    logger.info(f"Slot {slot} found again")
                    pass
            if len(new_slots):
                await autobook_processor(update, context, new_slots)
    except TokenExpireError as e:
        await message.edit_text(f"Token expired, please re-login: {e.msg}")
        return
    except Exception as e:
        logger.error(e)
        os.system("say --voice='Bad News' Oooops! Camper quits")
        await message.edit_text(f"Error: {e}")
        raise (e)
    await print_current_slots(update, context, message=message)


async def autobook_processor(update: Update, context, slots_list=None):

    # entry point for camper booking; this is usually month by month
    # will determine if slots will be booked; initiate chat_data["book"] for
    if slots_list is None:
        slots_list = context.chat_data.get("slots_list")
    config = context.chat_data["config"]
    session = context.chat_data.get("client", False)
    context.chat_data["book"] = {}
    if DEBUG:
        slots_list = get_debug_slots_list()

    if slots_list:
        trysell_auto = bool(config["autobook"]["trysell"])
        trysell_sessions = config.get("trysell_session", [])
        advance_auto = bool(config["autobook"]["advance"])
        trysell_condition = (
            datetime.date.today() + datetime.timedelta(hours=24)
        ).strftime("%Y%m%d")

        if trysell_auto or advance_auto:
            trysell_slots = []
            advance_slots = []
            for slot in slots_list:  # %Y%m%d\d-\d+
                if slot[:8] <= trysell_condition:
                    if slot[8] in trysell_sessions:
                        trysell_slots += [slot]
                else:
                    advance_slots += [slot]
            if trysell_auto and advance_auto:
                slots = trysell_slots + advance_slots
            else:  # only one
                slots = (
                    trysell_slots if config["autobook"]["trysell"] else advance_slots
                )

            context.chat_data["book"]["slots"] = {i: slots_list[i] for i in slots}
            context.chat_data["book"]["all"] = len(
                context.chat_data["book"]["slots"]
            ) == len(slots_list)

            if context.chat_data["book"]["slots"]:
                context.chat_data["book"]["auto"] = True
                # await api_preprocess_booking(update, context)
                await browser_book(update, context)


async def print_current_slots(
    update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs
) -> None:
    config: UserSession = context.chat_data.get("config", {})
    session: BbdcApi = context.chat_data.get("client", {})
    if config and len(config.released_slots):
        slots_list = context.chat_data["config"].released_slots
        msg = "Available slots summary:\n"
        msg += "\n".join(
            f'{slots_list[i]["slot_date"]} Session {slots_list[i]["session"]}'
            for i in slots_list
        )
    else:
        msg = "Sorry, no slots available now. Maybe /check again later?"
    if "message" in kwargs and kwargs["message"]:
        message = kwargs["message"]
        await message.edit_text(msg)
    else:
        await update.message.reply_text(msg)


async def camper(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the alarm message."""
    job = context.job
    chat_id = job.chat_id
    config: UserSession = context.chat_data["config"]
    session: BbdcApi = context.chat_data.get("client", {})
    if not (hasattr(session, "_browser_page") or session.stop):
        # if browser not exists, and session not stopped:
        await session.init_playwright_browser(headless=False)
    try:
        async for new_slots in session.scan_slots():
            for slot, item in new_slots.items():
                if slot not in config.released_slots:
                    msg = display_slot(item)
                    logger.info(msg)
                    await context.bot.send_message(chat_id=chat_id, text=msg)
                else:
                    logger.info(f"Slot {slot} found again")
                    pass
            if len(new_slots):
                await autobook_processor(job, context, new_slots)
    except TokenExpireError as e:
        job.schedule_removal()
        remove_job_if_exists(name=f"{chat_id}", context=context)
        await context.bot.send_message(
            chat_id, "Token expired. Camping schedule cancelled."
        )

    except Exception as e:
        os.system("say --voice='Bahh' Oooops! ")

        job.schedule_removal()
        remove_job_if_exists(name=f"{chat_id}", context=context)

        await context.bot.send_message(
            chat_id, f"Camping schedule cancelled due to errors: {e}"
        )
        logger.error(e)
        raise e


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    login_job = context.job_queue.get_jobs_by_name(name + "login")
    for job in login_job:
        job.schedule_removal()
    end_job = context.job_queue.get_jobs_by_name(name + "end")
    for job in end_job:
        job.schedule_removal()
    return True


async def command_camp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a job to the queue."""
    chat_id = update.effective_message.chat_id
    try:
        due = float(context.args[0])
        if due < 30:
            await update.effective_message.reply_text("Minimum interval is 30 seconds!")
            return
        if len(context.args) > 1:
            start_time = float(context.args[1])  # in hours
            start_time = start_time * 3600
        else:
            start_time = 0
        if len(context.args) > 2:
            end_time = float(context.args[2])  # in hours
            end_time = end_time * 3600
            if end_time < start_time:
                start_time = 0
        else:
            end_time = 4 * 3600  # None
        if not context.chat_data.get("config", False):
            # if no configuration
            try:
                config = context.chat_data["config"] = UserSession(chat_id)
                if not config._client:
                    session = context.chat_data["client"] = BbdcApi(config)

            except:
                await update.message.reply_text("Ooops! User not found.")
                return
        else:
            # if there's configuration: always use the refreshed-auth to log in
            await context.chat_data["config"].update_auth()
        try:
            job_removed = remove_job_if_exists(str(chat_id), context)
            context.chat_data["repeat_due"] = due
            # if start_time > 5 * 3600:
            # context.job_queue.run_once(
            #    command_login, start_time - 30, name=str(chat_id) + "login"
            # )

            context.job_queue.run_repeating(
                camper,
                due,
                first=start_time,
                last=end_time,
                chat_id=chat_id,
                name=str(chat_id),
                job_kwargs={"max_instances": 1, "coalesce": True},
            )

            text = f"Camping bot successfully set, repeat every {due} seconds. "
            if start_time:
                text += f"Start {start_time/3600:.1f} hours later. "
            if end_time:
                text += f"End {end_time/3600:.1f} hours later."
                context.job_queue.run_once(
                    notify_job_end,
                    end_time + 15,
                    chat_id=chat_id,
                    name=str(chat_id) + "end",
                    job_kwargs={"misfire_grace_time": None},
                )
            if job_removed:
                text += " Old one was removed. "
            logger.debug(f"Camping set for {chat_id}, {text}")
            await update.effective_message.reply_text(text)
        except Exception as e:
            await update.message.reply_text("Can't set camping bot!")
            raise e

    except (IndexError, ValueError):
        await update.effective_message.reply_text("Usage: /camp <seconds>")


async def notify_job_end(context):
    job = context.job
    chat_id = job.chat_id
    try:
        await context.chat_data["client"].close_client()
    except:
        logger.warning("failed to close client.")
    await context.bot.send_message(chat_id=chat_id, text="Camping schedule ended.")


async def command_unset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the job if the user changed their mind."""
    chat_id = update.message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)
    text = (
        "Camping successfully cancelled!"
        if job_removed
        else "You have no active timer."
    )
    await update.message.reply_text(text)


async def command_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id in ADMIN:
        await update.message.reply_document(
            "log.txt",
        )
    return


async def command_myschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.debug("Checking schedule")
    chat_id = update.effective_chat.id
    config = context.chat_data.get("config", False)
    session = context.chat_data.get("client", False)
    if not config:
        try:
            config = context.chat_data["config"] = UserSession(chat_id)
            session = context.chat_data["client"] = BbdcApi(config)
            await session.init_playwright_browser()
        except NameError as e:
            await update.message.reply_text("Ooops! User not found.")
            return
    if not (hasattr(session, "_browser") or session.stop):
        # if browser not exists, and session not stopped:
        await session.init_playwright_browser()
    days = int(context.args[0]) if context.args else 7
    days_text = (datetime.date.today() + datetime.timedelta(days=days)).strftime(
        "%Y-%m-%d"
    )
    try:
        text = ""
        schedules = await session.list_scheduled()
        schedules_session = sorted(schedules)
        if schedules_session:
            text += f"{len(schedules_session)} schedules ahead."
        count = 0
        for i, dt in enumerate(schedules_session):
            if dt[:10] < days_text:
                count += 1
                text += f"\n{i+1}. {dt[5:]}, {schedules[dt]['dataType']}"
            else:
                break
        if not count:
            text += f"\nNo schedules in the next {days} days."
    except Exception as e:
        await update.message.reply_text(f"Can't get schedule: {e}")
    try:
        await update.message.reply_document(
            f"user/{chat_id}/bbdc.ics", "Your calendar file is ready!\n" + text
        )
    except:
        pass
