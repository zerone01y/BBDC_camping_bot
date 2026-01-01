from seleniumwire import webdriver
from seleniumwire.utils import decode
from selenium.webdriver.chrome.service import Service

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.options import Options
from bbdc_slot_finder.auto_decoder import get_captcha
from io import BytesIO
from bbdc_slot_finder.logger import logger
import time, pathlib, json, asyncio, os

# Set logging level for seleniumwire to WARNING
SELENIUM_PORT = 9324


def authentication_page(username, password, browser, wait):
    wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="input-8"]')))
    wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="input-15"]')))
    id_login = browser.find_element(By.XPATH, '//*[@id="input-8"]')
    id_login.send_keys(username)
    password_login = browser.find_element(By.XPATH, '//*[@id="input-15"]')
    password_login.send_keys(password)
    login_button = browser.find_element(
        By.XPATH, '//*[@id="app"]/div/div/div[1]/div/div/form/div/div[5]/button/span'
    )
    login_button.click()


def browser_auth_captcha(browser, wait, auto=True):
    # captcha figure
    def get_img():
        captcha_figure = wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//*[@class='form-captcha-image-wrapper']/div/div")
            )
        )
        return BytesIO(captcha_figure.screenshot_as_png)

    img = get_img()
    captcha = get_captcha(img, auto)

    while len(captcha) != 5:
        # refresh
        captcha_input = browser.find_element(
            By.XPATH, '//*[@id="app"]/div/div/div[1]/div/div/form/div/div[2]/div/a'
        ).click()
        img = get_img()
        captcha = get_captcha(img, auto)

    captcha_input = browser.find_element(
        By.XPATH, '//*[text()[contains(.,"Captcha")]]'
    ).find_element(By.XPATH, "following-sibling::input")

    captcha_input.send_keys(captcha)

    # click verify
    verify_button = browser.find_element(
        By.XPATH, '//*[@id="app"]/div/div/div[1]/div/div/form/div/div[4]/button/span'
    )
    verify_button.click()
    booking_button = wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, "//div[@class='v-navigation-drawer__content']//div[3]/div[2]")
        )
    )


def browser_check_slots(browser, wait):
    try:
        booking_button = wait.until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    "//div[@class='v-navigation-drawer__content']//div[3]/div[2]",
                )
            )
        )
    except:
        expand_button = browser.find_element(
            By.XPATH, "//div[contains(@class, 'decrease')]/button"
        )
        expand_button.click()
        booking_button = wait.until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    "//div[@class='v-navigation-drawer__content']//div[3]/div[2]",
                )
            )
        )
    finally:
        booking_button.click()

    # click practical test
    # wait.until(EC.visibility_of_element_located((By.XPATH, "//div[@class='v-navigation-drawer__content']//div[3]/div[2]/div[2]/a[2]")))
    prac = wait.until(
        EC.visibility_of_element_located(
            (
                By.XPATH,
                "//div[@class='v-navigation-drawer__content']//div[3]/div[2]//div[2]/a[2]",
            )
        )
    )
    prac.click()
    # app > div.v-dialog__content.v-dialog__content--active > div > div > div.InstrutorTypeList > div > div > div.v-input__slot > div > div:nth-child(1)
    book_slot_button = wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, '//*[@class="C3Practical"]/div//div//div//div//button')
        )
    )
    book_slot_button.click()
    # not fixed
    no_fixed_instructor_button = wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, '//*[@class="InstrutorTypeList"]/div/div/div[1]/div/div[1]')
        )
    )
    no_fixed_instructor_button.click()
    next_button = browser.find_element(By.XPATH, '//*[text()[contains(.,"NEXT")]]')
    next_button.click()
    # calendar = wait.until(EC.visibility_of_element_located((By.CLASS_NAME, 'calendar-row')))
    # current_month = calendar.find_element(By.CLASS_NAME, 'title')
    # calendar_grid = current_month.find_element(By.XPATH, "following-sibling::*")
    # calendar_grid.find_elements(By.XPATH, ".//button")
    logger.debug("Enters booking page")


# Sometimes I have some tedious thing to do like data entry
# Sometimes I script that tedious thing using selenium
# Sometimes I have to login to something to enter that data
# This allows you to rerun your script using the same session


SELENIUM_SESSION_FILE = "./selenium_session"
SELENIUM_PORT = 9515


# Create a request interceptor
def interceptor(request):
    del request.headers["sec-ch-ua"]  # Delete the header first
    request.headers["sec-ch-ua"] = (
        '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"'
    )


def intercept_and_add_jsessionid(driver, jsessionid):
    # Modify requests going to the backend API
    def request_interceptor(request):
        del request.headers["sec-ch-ua"]  # Delete the header first
        request.headers["sec-ch-ua"] = (
            '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"'
        )
        if request.url.startswith("https://booking.bbdc.sg/bbdc-back-service/"):
            if jsessionid:
                # Add JSESSIONID to the headers
                del request.headers["jsessionid"]
                request.headers["jsessionid"] = jsessionid
                print(f"Added jsessionid: {jsessionid} to {request.url}")

    del driver.request_interceptor
    driver.request_interceptor = request_interceptor


def build_browser_(headless=False):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")

    chrome_options.add_argument("--window-size=1280,900")
    chrome_options.add_argument("--allow-running-insecure-content")

    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0"
    )
    chrome_options.add_argument(
        "user-data-dir=/Users/yangly/Library/Application Support/Microsoft Edge/Profile 1"
    )

    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--enable-file-cookies")
    chrome_options.add_argument("--no-sandbox")

    if os.path.isfile(SELENIUM_SESSION_FILE):
        session_file = open(SELENIUM_SESSION_FILE)
        session_info = session_file.readlines()
        session_file.close()

        executor_url = session_info[0].strip()
        session_id = session_info[1].strip()

        driver = webdriver.Remote(command_executor=executor_url, options=chrome_options)
        # prevent annoying empty chrome windows
        driver.close()
        driver.quit()

        # attach to existing session
        driver.session_id = session_id
        return driver

    # Define the specific port you want to use
    # service = Service(port=SELENIUM_PORT)  # Example: Use port 9515

    driver = webdriver.Chrome(
        options=chrome_options,
        # service=service
    )

    session_file = open(SELENIUM_SESSION_FILE, "w")
    session_file.writelines(
        [
            driver.command_executor._url,
            "\n",
            driver.session_id,
            "\n",
        ]
    )
    session_file.close()
    return driver


def build_browser(directory, headless=False, no_quit=True):
    # Create a request interceptor
    def interceptor(request):
        del request.headers["sec-ch-ua"]  # Delete the header first
        request.headers["sec-ch-ua"] = (
            '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"'
        )

    def intercept_and_add_jsessionid(driver, jsessionid):
        # Modify requests going to the backend API
        def request_interceptor(request):
            del request.headers["sec-ch-ua"]  # Delete the header first
            request.headers["sec-ch-ua"] = (
                '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"'
            )
            if request.url.startswith("https://booking.bbdc.sg/bbdc-back-service/"):
                if jsessionid:
                    # Add JSESSIONID to the headers
                    del request.headers["jsessionid"]
                    request.headers["Jsessionid"] = jsessionid
                    logger.debug(f"Added jsessionid to {request.url}")
            else:
                print(f"skip: url = {request.url}")

        del driver.request_interceptor
        driver.request_interceptor = request_interceptor

    # Set the interceptor on the driver
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")

    chrome_options.add_argument("--window-size=1280,900")
    chrome_options.add_argument("--allow-running-insecure-content")

    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0"
    )
    chrome_options.add_argument(
        "user-data-dir=/Users/yangly/Library/Application Support/Microsoft Edge/Profile 1"
    )

    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--enable-file-cookies")
    browser = webdriver.Chrome(options=chrome_options)
    # browser = build_browser(headless=headless)
    browser.request_interceptor = interceptor
    browser.scopes = [".*booking.bbdc.sg/bbdc-back-service.*", ".*bbdc-back-service.*"]

    try:
        # browser.execute_cdp_cmd('Network.enable', {})
        if no_quit:
            with open(f"{directory}/cookies.json", "r") as f:
                cookies = json.load(f)
                for cookie in cookies:
                    if "expiry" in cookie:
                        cookie["expires"] = cookie["expiry"]
                        del cookie["expiry"]

            with open(f"{directory}/headers.json", "r") as f:
                headers = json.load(f)
                if "jsessionid" in headers:
                    intercept_and_add_jsessionid(browser, headers["jsessionid"])
            # browser.execute_cdp_cmd('Network.setCookie', cookie)
            # browser.execute_cdp_cmd('Network.disable', {})
            browser.get("https://booking.bbdc.sg/?#/booking/chooseSlot")
            for c in cookies:
                browser.add_cookie(c)
            print("loading coookies")
            try:
                WebDriverWait(browser, 2).until(
                    EC.url_changes("https://booking.bbdc.sg/?#/booking/chooseSlot")
                )
                print("URL has changed to:", browser.current_url)
            except:
                print("URL did not change within 2 seconds")

    except:
        pass
    return browser


def browser_login(
    browser,
    config,
    check_slots=True,
    directory="user",
):
    logger.debug("Opening browser to log in...")
    # username password
    username = config["login"]["username"]
    password = config["login"]["password"]
    # auto_captcha_login = config["login"]["auto_captcha"]

    # browser = build_browser(headless=headless, no_quit=no_quit, directory=directory)
    wait = WebDriverWait(browser, 60)

    try:
        # login BBDC
        try:
            del browser.request_interceptor
            browser.delete_all_cookies()
        except:
            pass
        finally:
            browser.request_interceptor = interceptor
        browser.get("https://booking.bbdc.sg/#/login")
        get_url = browser.current_url
        if get_url.startswith("https://booking.bbdc.sg/#/login"):
            authentication_page(username, password, browser, wait)
        # captcha
        try_time = 0
        wait.until(
            lambda browser: browser.current_url.startswith(
                "https://booking.bbdc.sg/#/loginCaptcha"
            )
        )
    except TimeoutException as e:
        raise e

    get_url = browser.current_url

    while get_url.startswith("https://booking.bbdc.sg/#/loginCaptcha"):
        try_time += 1
        if try_time > 3:
            return False
        try:
            browser_auth_captcha(browser, wait)
            get_url = browser.current_url

        except TimeoutException:
            browser.refresh()
    logger.debug("Logged in...")

    wait_l = WebDriverWait(browser, timeout=10)

    wait_l.until(
        lambda browser: browser.current_url.startswith(
            "https://booking.bbdc.sg/#/home/index"
        )
    )
    time.sleep(3)
    with open(f"{directory}/cookies.json", "w") as f:
        json.dump(browser.get_cookies(), f)
    rq = list(filter(lambda x: "getUserProfile" in x.url, browser.requests))[-1]
    headers = {i[0]: i[1] for i in rq.headers._headers}
    headers.pop("content-length")

    pathlib.Path("user").mkdir(exist_ok=True)
    with open(f"{directory}/headers.json", "w") as f:
        json.dump(headers, f)
    try:
        payload = json.loads(
            decode(
                rq.response.body,
                rq.response.headers.get("Content-Encoding", "identity"),
            ).decode()
        )["data"]["enrolDetail"]

        with open(f"{directory}/profile.json", "w") as f:
            json.dump(payload, f)
    except:
        print("profile not saved")
        pass

    print("log in successfully")
    rqs = list(filter(lambda x: "Captcha" in x.url, browser.requests))
    for rq in rqs:
        try:
            captcha = json.loads(
                decode(
                    rq.response.body,
                    rq.response.headers.get("Content-Encoding", "identity"),
                ).decode()
            )["data"]["image"].split(",")[1]
            with open("test/captcha.txt", "a+") as f:
                f.write(captcha + "\n")
        except:
            pass

    if check_slots:
        try:
            browser_check_slots(browser, wait)
        except:
            pass

    # https://gist.github.com/stevenctl/d34e0494843479b2a12b9e58cf8d645e
    session_file = open(SELENIUM_SESSION_FILE, "w")
    session_file.writelines(
        [
            browser.command_executor._url,
            "\n",
            browser.session_id,
            "\n",
        ]
    )
    session_file.close()

    return browser


def browser_find_available_months(
    wait, browser, wanted, enable_bot, bot_token="", chat_id=""
):
    import datetime

    months_array = wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, '//*[@class="dateList dateList-web d-none d-md-flex"]')
        )
    ).find_elements(By.XPATH, ".//button")
    return_months = [
        month.find_element(By.XPATH, ".//span").text for month in months_array
    ]

    logger.debug("look for available slots")
    successful = False
    available_months = []
    for want in wanted:
        if (
            datetime.date(want // 100, want % 100, 1).strftime("%b'%y").upper()
            in return_months
        ):
            successful = True
            available_months.append(want)
    if successful:
        message = f"""{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Found available slots for {available_months}"""

    else:
        message = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No slots available"
    logger.info(message)
    browser.refresh()

    # headers = login(config, headless)
    # connect to Chrome
    # browser = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)


def record_requests(browser, file, slice_l=None, slice_u=None):
    with open(file, "w") as f:
        messages = {}
        count = 0
        for i in browser.requests[slice_l:slice_u]:
            count += 1
            messages[count] = {}
            message = messages[count]
            message["method"] = i.method
            message["url"] = i.url
            message["headers"] = {k[0]: k[1] for k in i.headers._headers}
            try:
                if len(i.body):
                    message["payload"] = json.loads(
                        decode(i.body, i.headers.get("Content-Encoding", "identity"))
                    )
            except:
                print("failed to save payload")
                pass
            try:
                message["response"] = json.loads(
                    decode(
                        i.response.body,
                        i.response.headers.get("Content-Encoding", "identity"),
                    )
                )
            except:
                print("failed to save response")
                pass
        json.dump(messages, f)
