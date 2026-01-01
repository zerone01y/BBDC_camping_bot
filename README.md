# BBDC-Booking-Bot

> ⚠️ **IMPORTANT WARNING**: This repository is shared as a personal reference and learning exercise, inspired by and adapted from various public GitHub projects. It may **violate BBDC’s Terms of Service**, and there is **no guarantee it will continue to work**, as the website’s APIs or anti-bot measures may change at any time. The code was **last tested in 2024**. Whether to use it, and any consequences that may arise (including possible account suspension or banning), are **entirely the user’s own responsibility**.

## Project Overview

This is a server-side script integrated with a Telegram Bot for automatically checking and booking driving lesson slots at BBDC (Bukit Batok Driving Centre).

### Core Features
- 🤖 **Telegram Bot Control**: Remotely control server behavior through Telegram Bot
- 🔍 **Automatic Slot Checking**: Periodically scans the BBDC website to find available driving lesson slots
- 📱 **Telegram Notifications**: Instantly sends notifications via Telegram when available slots are found
- ✅ **Automatic Booking**: Supports automatic booking of eligible slots (advance booking/try-sell booking)
- 📅 **Schedule Management**: View booked lesson schedules and generate iCal calendar files
- 🔄 **Scheduled Checking (Camping)**: Set up scheduled tasks to automatically check for available slots at specified intervals
- 🌐 **Direct Browser Interaction**: Open browser window on hosting server to directly interact with BBDC website

### Important Usage Notes

⚠️ **Configuration Requirements**:
- **Username and password must be configured on the server**: BBDC account username and password need to be set in the configuration file on the server. **They cannot be configured through the Telegram Bot**
- **Single login restriction**: If the Bot is enabled, **you cannot log in to the same BBDC account on other devices or browsers simultaneously**, as this will cause session conflicts and authentication failures
- For first-time use, you need to log in on the server using the `/login` command. Login information must be configured locally on the server beforehand.

## Authentication & Data Storage

**Important Security Note**: 
- The bot stores your BBDC username and password **explicitly** in the user configuration file (`user/<chat_id>/config.yaml`)
- After initial login, the bot uses cookies and authentication headers stored in `user/<chat_id>/` to maintain your session
- Your credentials are stored in plain text - ensure proper file permissions and security measures
- Files stored per user:
  - `config.yaml`: User configuration including username, password, and booking preferences
  - `headers.json`: Authentication headers
  - `cookies.json`: Session cookies
  - `profile.json`: User profile information

## Prerequisites

- Python 3.7+
- [Telegram Bot Token](https://t.me/botfather) - Create a Telegram bot to get a Token
- [PlayWright](https://playwright.dev/python/docs/library)
- (Optional) Tesseract OCR - For automatic captcha recognition

## Installation

### 1. Clone the Repository

```sh
git clone https://github.com/kombucha7/bbdc-bot.git
cd bbdc-bot
```

### 2. Create Virtual Environment

```sh
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate
```

### 3. Install Dependencies

```sh
pip install -r requirements.txt
playwright install
```


### 4. Install Tesseract OCR (Optional, for automatic captcha recognition)

**macOS:**
```sh
brew install tesseract
```

**Linux (Ubuntu/Debian):**
```sh
sudo apt-get install tesseract-ocr
```

**Windows:**
Download and install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)

## Configuration

### 1. Create Telegram Bot

1. Search for [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` command to create a new bot
3. Follow the prompts to set bot name and username
4. Get your Bot Token (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
5. Get your Chat ID (you can message [@userinfobot](https://t.me/userinfobot) to get it)

### 2. Configure Telegram Bot

Edit the `config_bot.yaml` file:

```yaml
telegram:
  token: "YOUR_TELEGRAM_BOT_TOKEN"
  admin: [YOUR_CHAT_ID]  # Optional: admin list. Admins can use /log command to download log files
```

### 3. User Configuration

After running the bot, sending `/start` to the bot will create a local folder `user/<chat_id>`. Create a config file and configure your username and password to allow automatical log in. 

### Example User Configuration

Your `user/<chat_id>/config.yaml` will look like:

```yaml
login:
  password: 'your_password'
  username: your_username
autobook:
  Ding: true
  advance: true
  trysell: false
month:
- 202411
- 202412
trysell_session:
- '7'
- '8'
- '2'
```

**Note**: Your username and password will be stored in plain text in `user/<chat_id>/config.yaml`. The bot will use cookies and authentication headers to maintain your session after the initial login.

It is possible to change the config in the bot (apart from the login session):

Use the `/config` command to configure:
- **Month Settings**: Select months to check for slots
- **Automatic Booking Settings**:
  - `advance`: Automatically book slots more than 48 hours in advance
  - `trysell`: Automatically book slots within 48 hours
  - `auto_captcha`: Automatically recognize captchas
  - `safe_mode`: Re-confirm availability before booking
  - `Ding`: Play notification sound when available slots are found
- **Try-sell Session Selection**: Select try-sell sessions allowed for automatic booking

**Important Note**: If automatic booking is enabled (`advance` or `trysell`), when you use `/check` or `/camp` commands and available slots are found, the system will **automatically book** eligible slots without requiring manual use of the `/book` command. The `/book` command is mainly for manually selecting specific slots, or when automatic booking is not enabled.

## Usage

### Start the Bot

Before starting the bot, make sure:
1. ✅ You have completed all [configuration steps](#configuration)
2. ✅ Virtual environment is created and activated
3. ✅ All dependencies are installed
4. ✅ `config_bot.yaml` file is configured (with Telegram bot token)

**Start command**:

```sh
# Make sure virtual environment is activated
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows

# Start the bot
python bot.py
```

After the bot starts, you will see it online in Telegram. For first-time use, follow these steps:

1. Send `/start` command to the bot in Telegram
2. Send `/login` command to log in to your BBDC account
3. Send `/config` command to configure automatic booking settings
4. Send `/check` or `/camp` command to start checking for available slots


### Common Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and check user configuration |
| `/login` | Log in to BBDC account (first time use or when token expires) |
| `/login headless` | Login in headless mode (runs in background) |
| `/check` | Check for available slots once |
| `/camp <seconds>` | Set up periodical slot checking at the specified interval (in seconds). The period should be at least 30s but less than 15 mins, otherwise BBDC may terminate the session. E.g.  `/camp 300` will check slots every 5 minutes.|
| `/camp <seconds> <start_hour> <end_hour>` | Set periodical checking with start and end times. |
| `/unset` | Cancel scheduled checking task |
| `/myschedule [days]` | View booked schedule (default 7 days) |
| `/config` | Configure bot settings (months, autobook, etc.) |
| `/help` | Show help information |
| `/log` | (Admin only) Download the latest log file. Only users in the admin list can use this command |
| `/open_browser` | Open browser window on the hosting server, allowing direct viewing and interaction with the BBDC website |
| `/quit_browser` | Close the browser window opened on the server |
| `/pause_browser` | Pause browser (for debugging) |


Note: When a new slot is found, user should use automatical booking or `/open_browser` to make the booking, instead of using other devices/browser to log in and book. Frequent login may lead to account suspension.


## Important Notes

⚠️ **Important Warnings**:
- **This code was last tested in February 2025. There is no guarantee that it will work again. Use at your own risk.**
- Due to BBDC website updates and anti-botting measures, using this tool carries certain risks. Use at your own discretion.
- **Your username and password are stored in plain text** in `user/<chat_id>/config.yaml`. The script may download sensitive information from BBDC website. These information will be stored on the server and not shared online.
- The bot uses cookies and authentication headers to maintain your session after initial login.
- It is recommended to set reasonable checking intervals to avoid excessive requests.
- Tokens may expire. If you encounter authentication errors, use `/login` to re-login.

## References

- [Telegram Bot API](https://core.telegram.org/bots)
- [Create Telegram Bot Tutorial](https://dev.to/rizkyrajitha/get-notifications-with-telegram-bot-537l)
- [Playwright Documentation](https://playwright.dev/python/)

## Related Projects

- https://github.com/rohit0718/BBDC-Bot
- https://github.com/weimingwill/bbdc-booking
- https://github.com/lizzzcai/bbdc-booking-bot

