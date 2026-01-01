from playwright.async_api import async_playwright, expect, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from bbdc_slot_finder.auto_decoder import auto_solve_captcha_data
from bbdc_slot_finder.exceptions import TokenExpireError
from bbdc_slot_finder.const import *
import json
import random
import time
import datetime
import re
import logging
import os

DEBUG = os.environ.get("BBDC_BOT_DEBUG", False)
logger = logging.getLogger(__name__)
MAX_BOOKING_DATES = 3
import json


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


async def log_request_response(request, directory="."):
    # 获取请求头和请求负载
    request_headers = request.headers
    request_post_data = request.post_data
    response = await request.response()
    # 获取响应体
    try:
        response_body = await response.json()
    except:
        logger.error("failed to save response body (as json)")
        response_body = {}

    # 构建日志数据
    log_data = {
        "request_url": request.url,
        "request_headers": request_headers,
        "request_post_data": request_post_data,
        "response_body": response_body,
    }

    # 保存日志数据到文件
    file_name = f"logs/log_rq.json"
    with open(file_name, "a+") as f:
        json.dump(log_data, f, indent=4)
        f.write(",\n")
        # 监听请求和响应事件


async def save_cookies(page, directory):
    # Save cookies
    cookies = await page.context.cookies("https://booking.bbdc.sg")
    with open(f"{directory}/cookies.json", "w") as f:
        json.dump(cookies, f)


async def login_bbdc(config, page: Page, directory="."):

    username = config["login"]["username"]
    password = config["login"]["password"]
    try:
        # Authentication page
        await authentication_page(
            username, password, page
        )  # fill in usernaem and password
        async with page.expect_response("**/getLoginCaptchaImage") as first:
            await page.get_by_role("button", name="Access to Booking System").click()
        response = await first.value
        if not response.ok:
            raise Exception("Fail to verify user account. Account suspended?")
        trial_count = 0

        while "loginCaptcha" in page.url:
            if trial_count == 0:
                await solve_playwright_captcha(
                    page, None, auth_getLoginCaptchaImage, response
                )

            elif trial_count >= 3:
                break
            elif trial_count != 0:
                await page.wait_for_timeout(5000)
                async with page.expect_response("**/getLoginCaptchaImage") as first:
                    await page.locator(".v-responsive__content").click()
                response = await first.value
                await solve_playwright_captcha(
                    page,
                    None,
                    auth_getLoginCaptchaImage,
                )
            trial_count += 1

            await page.get_by_role("button", name="Verify").click()
            try:
                await page.wait_for_url(
                    "https://booking.bbdc.sg/?#/booking/chooseSlot", timeout=10000
                )
            except:
                pass
        if "loginCaptcha" in page.url:
            return False
        logger.debug("Logged in...")
        # page.wait_for_timeout(3000)  # Wait for 3 seconds
        return True

    except Exception as e:
        if "home" in page.url:
            pass
        else:
            logger.error(f"An error occurred: {e}")
            raise e


async def chooseslot_page_refresh(page):
    """similar to api.list_c3_slot_released; no arg required, return True/False, data"""
    async with page.expect_response("**/listC3PracticalSlotReleased") as res:
        if not "chooseSlot" in page.url:
            await go_to_booking(page)
        else:
            await page.reload()
    res = await res.value
    data = await res.json()
    if len(data["data"]) == 0:
        logger.error("No data")
    return data["success"], data["data"]


async def list_c3_slot_released(
    page: Page,
    m: str = None,
):
    if "login" in page.url:
        return False, {}

    """similar to api.list_c3_practical_slot_released"""
    if m is None:
        suc, data = await chooseslot_page_refresh(page)
        return suc, data  # True/False, {"releasedSlotMonthList":...}
    else:
        # m = None or string(int) like "202407",
        month_code = datetime.datetime.strptime(str(m), "%Y%m").strftime(
            "%b"
        )  # example: 'Apr'
        month_button = (
            page.locator(".dateList")
            .filter(has=page.locator("button[class*=available]", has_text=month_code))
            .get_by_role("button", name=month_code)
            .locator("visible=true")
        )
        month_button_enabled = await month_button.count()
        if month_button_enabled:  # if any, and if enabled
            month_button_enabled = await month_button.is_enabled()
        if (
            not month_button_enabled
        ):  # not enabled: it is current month, no data available
            return True, {}
        else:
            async with page.expect_response(
                "**/listC3PracticalSlotReleased", timeout=10000
            ) as res:
                await month_button.click()
            res = await res.value
            data = await res.json()
            return data["success"], data["data"]


async def go_to_booking(page):
    "from other pages to chooseslot page;"
    button_locator = (
        page.get_by_role("button", name="Booking", exact=True)
        .locator("..")
        .get_by_role("link", name="Practical", exact=True)
    )
    button_locator_visible = await button_locator.is_visible()
    if not button_locator_visible:
        await page.get_by_role("button", name="Booking", exact=True).click()
        dialog_count = await page.get_by_role("dialog").count()
        if (
            dialog_count
        ):  # if any dialog, just continue (e.g. previously selected slots without booking)
            await page.get_by_role("button", name="Next", exact=True).click()
    await button_locator.click()
    await expect(page).to_have_url(re.compile(".*booking/practical"))
    await page.get_by_role("button", name="Book Slot").nth(0).click()
    await page.locator("div").filter(
        has_text=re.compile(r"^Book without fixed instructor$")
    ).click()
    await page.get_by_role("button", name="NEXT").click()


async def solve_playwright_captcha(
    page: Page,
    trigger_button_name="CONFIRM",
    response_api=booking_getCaptchaImage,
    response=None,
    captcha_label="Captcha",
):
    """
    page: booking confirm page or captcha page;
    the function will obtain the captcha image, solve the captcha to obtain a 5-digit code,
    and fillin the captcha.
    The function may confirm booking and fill in the captcha solved;
    For login page: solve_playwright_captcha(
                    page, None, auth_getLoginCaptchaImage, response
                )
    For booking page: solve_playwright_captcha
    """
    captcha = ""
    counter = 0
    # choices: pass the response directly, or press the trigger button
    if response:
        data = await response.json()
        data = data["data"]
        captcha = auto_solve_captcha_data(data)
        counter += 1
    if trigger_button_name:
        trigger_button = page.get_by_role("button", name=trigger_button_name)
        await expect(trigger_button).to_be_visible()
    while len(captcha) != 5:
        if counter:
            await page.wait_for_timeout(3020)
        counter += 1
        if counter > 3:  # three chances, 1, 2, 3
            break
        async with page.expect_response(f"**/{response_api}") as first:
            img_locator = page.locator(".v-responsive__content")
            # regresh the captcha image if is visible, or press trigger button
            img_locator_visible = await img_locator.is_visible()
            if img_locator_visible:
                await img_locator.click()
            else:
                await trigger_button.click()
        result_response = await first.value
        data = await result_response.json()
        data = data["data"]
        captcha = auto_solve_captcha_data(data)
    await page.get_by_label(captcha_label).click()
    await page.get_by_label(captcha_label).fill(captcha)

    # page.get_by_label("Captcha").click()
    # page.get_by_label("Captcha").fill(captcha)
    # page.get_by_role("button", name="Verify").click()


async def select_slots(page: Page, slots: dict = None, select_all=False):
    # get list of buttons for all dates
    # page.locator(".calendar-col").locator(".title").inner_text() # example: 'APR 2025'
    # Next step: confirm
    # click Month
    m = list(slots.keys())[0][:6]
    month_code = datetime.datetime.strptime(str(m), "%Y%m").strftime(
        "%b"
    )  # example: 'Apr'
    month_button = page.get_by_role("button", name=month_code).locator("visible=true")
    await month_button.click()
    buttons = (
        await page.locator(".calendar-col")
        .get_by_role("button", name=re.compile("\d+"))
        .all()
    )
    if select_all is True:
        async with page.expect_response(
            "**/updateSlotListClashStatus"
        ) as response_info:
            for i in buttons[:MAX_BOOKING_DATES]:  # can at most book the first 3 dates
                await i.click()
        slots_buttons = (
            await page.locator(".sessionCard").locator("visible=true").all()
        )  # .locator(".sessionCard").locator("visible=true")
        if len(slots_buttons) == 0:
            await page.pause()
        for i in slots_buttons:  # choose all session available
            await i.click()
    else:
        # put slots into groups of days
        days = set(i[6:8] for i in slots.keys())  # example: {'202504291-2345678', ...}
        reg_days = "(" + "|".join(sorted(days)) + ")"  # example: "(24|28)"
        buttons = (
            await page.locator(".calendar-col")
            .get_by_role("button", name=re.compile(reg_days))
            .all()
        )
        async with page.expect_response(
            "**/updateSlotListClashStatus"
        ) as response_info:
            for i in buttons[:3]:  # can at most book the first 3 dates
                await i.click()
        sessions = page.locator(".sessionCard").locator(
            "visible=true"
        )  # .locator(".sessionCard").locator("visible=true")
        for k, slot in slots.items():
            try:
                date = datetime.datetime.strptime(
                    slot["slot_date"], "%Y-%m-%d"
                ).strftime("%d %b %Y")
                await sessions.filter(has_text=date).filter(
                    has_text="SESSION " + slot["session"]
                ).click(timeout=3000)
            except PlaywrightTimeoutError:
                logger.info("timeoutime  t")
                pass  # the date may not be chosen, and therefore the session is not displayed
    next_button = page.get_by_role("button", name="NEXT")
    next_button_enabled = await next_button.is_enabled()
    if next_button_enabled:
        await next_button.click()
        confirm_button = page.get_by_role("button", name="CONFIRM")
        confirm_button_enabled = await confirm_button.is_enabled()
        if confirm_button_enabled:
            return True
        else:
            notice = await page.locator(".notice").inner_text()
            logger.warning(notice)
            close_button = page.get_by_role("button", name="CLOSE")
            close_button_enabled = await close_button.is_enabled()
            if close_button_enabled:
                await close_button.click()
            return False
    else:
        return False


async def book_slots(page: Page):
    """on page: pop-up dialog to confirm booking"""
    await solve_playwright_captcha(page)
    async with page.expect_response("**/callBookC3PracticalSlot") as first:
        await page.get_by_role("dialog").filter(has_text="Captcha").get_by_role(
            "button", name="Confirm"
        ).click()
    response = await first.value
    response = await response.json()
    if response["success"]:
        await page.reload()
        await go_to_booking(page)
        return True, response["data"]
    else:
        return False, response["message"]


async def authentication_page(username, password, page: Page):
    await page.get_by_label("Login ID").click()
    await page.get_by_placeholder("example: 567A02071990").fill(username)
    await page.wait_for_timeout(303)
    await page.get_by_label("Password", exact=True).click()
    await page.get_by_label("Password", exact=True).fill(password)
    await page.wait_for_timeout(205)


async def scan_slots(
    page: Page, month_wanted=["202504", "202505"], res_data: dict = None
):
    # first refresh choose slot_page
    if res_data is None:
        response = await chooseslot_page_refresh(page)
        res_data = response.json()
    if res_data["success"]:
        data = res_data["data"]
        count = 0
        for month in data["releasedSlotMonthList"]:
            month_code: str = month["slotMonthEn"][:3]  # example: 'Apr'
            month_digi: str = month["slotMonthYm"]  # example: '202504'
            if month_digi in month_wanted:
                if count > 0:
                    await page.wait_for_timeout(300)
                    month_button = page.get_by_role("button", name=month_code)
                    button_count = await month_button.count()
                    if not button_count:
                        yield {}
                        continue
                    else:
                        month_button_enabled = await month_button.is_enabled()
                        if (
                            not month_button_enabled
                        ):  # if not enabled: then stop scanning...[can improve]
                            yield {}
                        async with page.expect_response(
                            "**/listC3PracticalSlotReleased", timeout=30000
                        ) as res:
                            await page.get_by_role("button", name=month_code).click()
                        response = await res.value
                        data = await response.json()
                        data = data["data"]
                        slots = parse_released_slots(
                            data
                        )  # slots = {'2025-04-29 00:00:00':[{...}]}
                        yield slots


async def intercept_and_add_jsessionid(page, directory):
    jsessionid = None

    async def handle_request(route, request):
        # Add jsessionid parameter
        headers = request.headers.copy()

        if jsessionid:
            headers["jsessionid"] = jsessionid
            headers["authorization"] = authorization
            print(f"Added jsessionid to {request.url}")
        await route.fallback(headers=headers)

    try:
        # Load cookies
        with open(f"{directory}/cookies.json", "r") as f:
            cookies = json.load(f)
            for cookie in cookies:
                if cookie["name"] == "bbdc-token":
                    if "expiry" in cookie:
                        cookie["expires"] = cookie["expiry"]
                        del cookie["expiry"]
                    break

        if cookie["name"] == "bbdc-token":
            await page.context.add_cookies(
                [
                    cookie,
                ]
            )

            # Load headers
            with open(f"{directory}/headers.json", "r") as f:
                headers = json.load(f)
                if "jsessionid" in headers:
                    jsessionid = headers["jsessionid"]
                    authorization = headers["authorization"]
                    await page.context.route("**/bbdc-back-service**", handle_request)
    except Exception as e:
        print(e)


async def build_bbdc_browser(p, debug, headless, directory, refresh_token):
    async def handle_bbdc_response(response):
        if "bbdc-back-service" in response.url and (
            "listC3PracticalSlotReleased" not in response.url
        ):
            request_response = await response.response()
            await log_request_response(response)
            if "getUserProfile" in response.url:
                try:
                    payload = await request_response.json()
                    payload = payload["data"]
                    with open(f"{directory}/profile.json", "w") as f:
                        json.dump(payload["enrolDetail"], f)
                    logger.debug("save user profile")
                except:
                    logger.error("fail to save save user profile")
            if "Captcha" in response.url:
                pass

    # userDataDir = "user_data"
    # path_to_extension = "/Users/yangly/Library/Application Support/Microsoft Edge/Default/Extensions"
    # Make sure to run headed.
    debug_kwargs = {}
    if debug:
        debug_kwargs.update(
            {
                "record_har_path": "logs/har/playwright.har.zip",
                "record_har_mode": "minimal",
                # "devtools": True,
            }
        )
    storage_state = not refresh_token
    state = f"{directory}/auth.json" if storage_state else None

    browser_ = await p.chromium.launch(
        headless=headless,
        args=[
            "--enable-automation",
            "--window-size=1280,900",
            "--disable-infobars",
            # f"--disable-extensions-except={path_to_extension}",
            # f"--load-extension={path_to_extension}",
        ],
    )
    browser = await browser_.new_context(
        # user_data_dir=userDataDir,
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0",
        storage_state=state,
        base_url=bbdc_base_url,
        **debug_kwargs,
        # extra_http_headersx # Literal['full', 'minimal'] | None = None,
        # record_har_content: Literal['attach', 'embed', 'omit'] | None = None,
    )
    if len(browser.pages):
        page = browser.pages[0]
    else:
        page = await browser.new_page()
    page.on("requestfinished", handle_bbdc_response)

    if not refresh_token:
        await intercept_and_add_jsessionid(page, directory)

    return browser, page


async def start_browser(
    config,
    headless=False,
    directory=".",
    debug=False,
    refresh_token=False,
    keep_browser=True,
):

    async with async_playwright() as p:
        browser, page = await build_bbdc_browser(
            p, debug, headless, directory, refresh_token
        )

        success = True
        try:
            async with page.expect_response(
                "**/listC3PracticalSlotReleased", timeout=30000
            ) as res:
                await page.goto(
                    "https://booking.bbdc.sg/?#/booking/chooseSlot?courseType=3C&insInstructorId=&instructorType="
                )
            response = await res.value
            res_data = await response.json()
            if res_data["success"] is False:
                raise TokenExpireError(response["message"])
            print("Continue with previous logged in status.")
        except:
            success = False
            await page.wait_for_url("**/*login*", timeout=500)  # 等待最多10秒
            if "login" in page.url:
                refresh_token = True
                await page.context.unroute("**/bbdc-back-service**")
                try:
                    success = await login_bbdc(config, page)
                    if success:
                        await save_cookies(page, directory)
                        await browser.storage_state(path=f"{directory}/auth.json")
                except:
                    return success
        # if "chooseSlot" not in page.url:
        #    await go_to_booking(page)
        # async for i in scan_slots(page, res_data=res_data):
        #    success_flag = await select_slots(page, i)
        #    await book_slots(page)
        # page.evaluate("localStorage.setItem(\"startTime\", new Date().getTime())")

        # Pause the page, and start recording manually.
        if keep_browser:
            await page.pause()
        # await list_c3_slot_released(page)
        # save_cookies(page, directory)
        await browser.close()

    if refresh_token and success:
        with open("logs/log_rq.json", "r") as f:
            text = f.read()
            headers = json.loads(text[:-2] + "]")[-1]["request_headers"]
        with open(f"{directory}/headers.json", "r") as f:
            header_old = json.loads(f.read())
            header_old.update(headers)
        with open(f"{directory}/headers.json", "w") as f:
            json.dump(header_old, f)
    return True
