import datetime, pathlib
from bbdc_slot_finder.logger import logger
from telegram.ext import ContextTypes
from bbdc_slot_finder.auto_decoder import get_captcha_image, auto_solve_captcha_data
from bbdc_slot_finder.exceptions import NameError, SessionStopError, TokenExpireError
from bbdc_slot_finder.config import load_config, write_config
from bbdc_slot_finder.const import *
from random import random
import json, time, os
import asyncio
from typing import Optional, Dict
from bbdc_slot_finder.async_playwright_browser_ops import (
    async_playwright,
    build_bbdc_browser,
    list_c3_slot_released as browser_check_slot,
)

DEBUG = os.environ.get("BBDC_BOT_DEBUG", False)
# from browser_login import login

if DEBUG:
    pass
    #with open("json-server/api-data/POST.json", "r") as f:
    #    REQS = json.load(f)


class UserSession(dict):
    @staticmethod
    def get_config(chat_id, read_config=True) -> Optional[Dict]:
        """Get configuration settings for a specific chat ID.

        Args:
            chat_id (int): The unique identifier for the chat.
            read_config (bool, optional): Whether to read the configuration file. Defaults to True.

        Returns:
            dict: A dictionary containing the configuration settings for the chat ID.
        """

        pathlib.Path(f"user/{chat_id}").mkdir(exist_ok=True)
        config_file = pathlib.Path(f"user/{chat_id}/config.yaml")
        if config_file.is_file():
            if read_config:
                config = load_config(config_file)
                config["month"] = list(
                    filter(
                        lambda x: x >= int(datetime.date.today().strftime("%Y%m")),
                        config["month"],
                    )
                )
            else:
                config = {}
            try:
                with open(f"user/{chat_id}/headers.json", "r") as f:
                    config["headers"] = json.loads(f.read())
                    config["headers"].pop("content-length", None)
                    config["headers"].pop("cookie", None)
                with open(f"user/{chat_id}/profile.json", "r") as f:
                    config["profile"] = json.loads(f.read())
                with open(f"user/{chat_id}/cookies.json", "r") as f:
                    config["stored_cookies"] = json.loads(f.read())
                logger.debug("update session authorization")
            except FileNotFoundError as e:
                if not config["headers"]:
                    msg = "User authentication file non-existant. use /login to login to account."
                    logger.warning(msg)
                    return None
                    # return empty config
            return config
        else:
            return None

    @property
    def client(self):
        return self._client

    def __init__(self, chat_id) -> None:
        super().__init__()
        self.chat_id = chat_id
        config = self.get_config(chat_id)
        if config:
            self.headers = config.pop("headers", None)
            self.profile = config.pop("profile", None)
            self.stored_cookies = config.pop("stored_cookies", None)
            self.update(config)
            self._client = None
            # self._client = BbdcApi(self.headers, self.stored_cookies)
            self.scheduled = None
            self.released_slots = {}
        else:
            raise NameError()

    async def update_auth(self, force_update=False):
        config = self.get_config(self.chat_id, read_config=False)
        self.headers = config.pop("headers")
        self.profile = config.pop("profile")
        self.stored_cookies = config.pop("stored_cookies", None)
        self._client._update_auth(force_update=force_update)

    def save(self) -> None:
        write_config(dict(self), f"user/{self.chat_id}/config.yaml")
        self.save_headers()
        self.save_profile()

    def save_headers(self):
        with open(f"user/{self.chat_id}/headers.json", "w") as f:
            json.dump(self.headers, f)

    def save_profile(self):
        with open(f"user/{self.chat_id}/profile.json", "w") as f:
            json.dump(self.profile, f)


class BbdcApi(object):
    def __init__(self, user_session: UserSession):
        self.user_session = user_session
        user_session._client = self
        self.stop = None

    def _update_auth(self, force_update=False):
        # if self.stop=None or False (not stopped), or if force to update
        if (not self.stop) or force_update:
            if getattr(self, "_httpx_client", False):
                self.init_httpx_client()
            else:
                # if force update, reset stop sign
                self.stop = False

    async def close_browser(self, stop=False):
        if hasattr(self, "_stopped"):
            # in case the process is triggered repeatedly via hooks
            del self._stopped
            return
        if stop:
            self.stop = stop
        logger.info("browser closing..")
        if getattr(self, "_browser", False):
            if DEBUG:
                await self._browser.tracing.stop(path="trace.zip")
            try:
                self._stopped = True
                await self._browser.close()
                await self._browser.browser.close()
                await self._browser_playwright.stop()
            except:
                pass
            finally:
                if getattr(self, "_browser", False):
                    del self._browser
                    del self._browser_page
                    del self._browser_client
                    del self._browser_playwright

    async def init_playwright_browser(self, headless=None):
        if self.stop:
            # if the session was closed due to TokenExpireError and has not been re-authorized
            raise SessionStopError()
        logger.info("init browser")
        self.stop = False
        if headless is None:
            headless = not (bool(DEBUG))
        self._browser_playwright = await async_playwright().start()
        self._browser, self._browser_page = await build_bbdc_browser(
            self._browser_playwright,
            debug=DEBUG,
            headless=headless,
            directory=f"user/{self.user_session.chat_id}",
            refresh_token=False,
        )
        await self._browser_page.goto(
            "https://booking.bbdc.sg/?#/booking/chooseSlot?courseType=3C&insInstructorId=&instructorType="
        )
        self._browser_client = self._browser_page.request
        self._browser.on("close", self.close_browser)
        if DEBUG:
            await self._browser.tracing.start(
                screenshots=False, snapshots=True, sources=True
            )
        return

    async def _post_request(
        self, endpoint: str, payload: dict = None, sleep: float = 1
    ):  # post request from playwright
        if self.stop:
            print("session stopped. do not post request.")
            self.close_browser(stop=True)
            raise SessionStopError()
        url = f"{endpoint}"
        if DEBUG:
            sleep = 0
        try:
            await asyncio.sleep(sleep)  # sleep
            # 发送POST请求
            response = await self._browser_client.post(
                url, headers=self.user_session.headers, data=payload
            )
            return response
            # logger.info(f"Request successful: {response.json()}")
        except Exception as e:
            print(f"An unexpected error occurred during: {e}")
            try:
                with open("logs/log.json", "a+") as f:
                    f.write(f"{datetime.datetime.now()} - {response.text}\n")
            except:
                pass
            await self.close_client(stop=True)  # force close
            raise (e)

    @staticmethod
    async def handle_response(response, key="data"):
        res = await response.json()
        if res["success"]:
            return True, res[key]
        else:
            logger.warning("failed request")
            with open("logs/log.json", "a+") as f:
                text = await response.text()
                f.write(f"{datetime.datetime.now()} - {response.url}: {text}\n")
            logger.info(res["message"])
            return False, res["message"]

    async def close_client(self, stop=False):
        self.stop = stop
        if hasattr(self, "_browser"):
            await self.close_browser(stop=stop)

    @staticmethod
    def parse_available_month(data, request_month, current_month) -> list:
        """Parse the available months from the given data based on the requested month and current month.

        Args:
            data (dict): The data obtained from list3Cslotsreleased json.
            request_month (list): The list of requested months.
            current_month (int): The current month.

        Returns:
            list: A list of available months that meet the conditions.
        """
        avail_months = data["releasedSlotMonthList"]
        avail_months_list = [
            i["slotMonthYm"]
            for i in avail_months
            if int(i["slotMonthYm"]) in request_month
            and i["slotMonthYm"] != str(current_month)
        ]
        return avail_months_list

    @staticmethod
    def parse_released_slots(data: dict) -> dict:
        """Parse released slots data and return a dictionary of parsed slot information.

        Args:
            data (dict): A dictionary containing released slot data.

        Returns:
            dict: A dictionary containing parsed slot information with slot keys and corresponding details.
        """
        if not data:
            return
        slot_list = {}
        slot_data = data["releasedSlotListGroupByDay"]
        if slot_data is None:
            return slot_list
        for day, slots in slot_data.items():
            date = datetime.datetime.fromisoformat(day).strftime("%Y%m%d")
            for slot in slots:
                slotDate_code = date + slot["slotRefName"].split(" ")[1]
                # slotDate_code = date + slot["slotRefName"].split(" ")[1]  # %Y%m%d\d-\d+
                slot_key = f"{slotDate_code}-{slot['slotId']}"
                slot_list.update(
                    {
                        slot_key: {
                            "payload": {
                                "slotIdEnc": slot["slotIdEnc"],
                                "bookingProgressEnc": slot["bookingProgressEnc"],
                            },
                            "slot_id": int(slot["slotId"]),
                            "total_fee": slot["totalFee"],
                            "slots_code": f"{slotDate_code}-{slot['slotId']}",
                            "slot_date": day[:10],
                            "group": slot["c3PsrFixGrpNo"],
                            "session": slot["slotRefName"].split(" ")[1],
                            "start_time": slot["startTime"],
                            "end_time": slot["endTime"],
                        }
                    }
                )
        return slot_list

    async def list_scheduled(self):
        user_session = self.user_session

        response = await self._post_request(
            booking_listManageBooking,
            payload={"courseType": user_session.profile["courseType"]},
        )

        suc, res = await self.handle_response(response)
        if suc is True:
            from bbdc_bot.cal import schedule_to_ics

            active_booking_list = res["theoryActiveBookingList"]
            with open(f"user/{user_session.chat_id}/schedule.json", "w") as f:
                json.dump(active_booking_list, f)
            with open(f"user/{user_session.chat_id}/bbdc.ics", "wb") as f:
                f.write(schedule_to_ics(active_booking_list))
            user_session.scheduled = {
                (
                    datetime.datetime.strptime(
                        i["slotRefDate"], "%Y-%m-%d %H:%M:%S.0"
                    ).strftime("%Y-%m-%d, %a ")
                    + i["startTime"]
                ): i
                for i in active_booking_list
            }

            # YYYY-mm-dd, %a %H:%M
            return user_session.scheduled
        else:
            await self.close_client(stop=True)
            raise Exception("Unknwon error: failed network request")

    async def list_c3_slot_released(self, month=None):
        user_session = self.user_session
        await asyncio.sleep(random() * 20)
        suc, data = await browser_check_slot(self._browser_page, month)
        if suc:
            if len(data):
                user_session.profile["accountBal"] = data["accountBal"]
            return data
        elif not suc:
            await self.close_client(stop=True)
            raise TokenExpireError("")

    async def scan_slots(self):
        user_session = self.user_session
        wanted_months = user_session["month"]
        new_slots_list = {}
        course_type = user_session.profile["courseType"]
        month_to_visit = {None}
        month_visited = []
        while len(month_to_visit):
            m = month_to_visit.pop()  # e.g. 202408
            data = await self.list_c3_slot_released(
                m,
            )
            month_visited.append(str(m))
            if data:
                slots_list = BbdcApi.parse_released_slots(data)
                if len(slots_list):
                    if m is None:
                        # determine m value if m is None;
                        m = int(list(slots_list.keys())[0][:6])
                        month_visited.append(str(m))
                        if m in wanted_months:  #
                            new_slots_list.update(slots_list)
                            logger.info(
                                f"{len(slots_list)} slots found in current month!"
                            )
                            yield slots_list
                    else:
                        new_slots_list.update(slots_list)
                        logger.info(f"{len(slots_list)} slots found!")
                        yield slots_list
                # determine the months to visit
                avail_month = BbdcApi.parse_available_month(data, wanted_months, m)
                if m is None:
                    # m = avail_month.pop(0)
                    month_visited.append(str(m))
                month_to_visit.update(avail_month)
                month_to_visit.difference_update(month_visited)
                logger.info(f"requested for month: {m}")
                await asyncio.sleep(10)
            # else:
            #    # await self.close_client(stop=True)
            #    raise (Exception("No data received"))
        user_session.released_slots.clear()
        user_session.released_slots.update(new_slots_list)
