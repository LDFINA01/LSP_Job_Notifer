import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# LSP Credentials
LSP_USERNAME = os.getenv('LSP_USERNAME')
LSP_PASSWORD = os.getenv('LSP_PASSWORD')

# Base URLs
BASE_URL = "https://kyrm.lspware.com"
LOGIN_URL = f"{BASE_URL}/scheduler/#/login"
JOB_POSTINGS_URL = f"{BASE_URL}/scheduler/#/jobs"

# Notification Settings
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Scraping Settings
SCRAPE_INTERVAL = int(os.getenv('SCRAPE_INTERVAL', '300'))

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'logs/scraper.log')

# File Management
MAX_DATA_FILES = int(os.getenv('MAX_DATA_FILES', '5'))  # Maximum HTML files to keep
MAX_SCREENSHOT_FILES = int(os.getenv('MAX_SCREENSHOT_FILES', '5'))  # Maximum screenshot files to keep
CLEANUP_OLD_FILES = os.getenv('CLEANUP_OLD_FILES', 'True').lower() in ('true', 'yes', '1')

# Headers
DEFAULT_HEADERS = {
    'Content-Type': 'application/json;charset=UTF-8',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Origin': BASE_URL,
    'Referer': f"{BASE_URL}/scheduler/",
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin'
}

# Login payload
LOGIN_PAYLOAD = {
    "userName": LSP_USERNAME,
    "userPassword": LSP_PASSWORD,
    "company": {
        "companyWebsite": "kyrm.lspware.com"
    },
    "changePassword": "N",
    "id": None,
    "loginWith2fa": False,
    "otpFor2fa": None,
    "canAccessMobile": False,
    "employeeId": "",
    "loginFromWidget": "N",
    "deviceInfo": {
        "deviceType": "web",
        "browser": "Chrome",
        "browserVersion": "134.0.0.0",
        "os": "Windows",
        "osVersion": "10.0.19045"
    }
}

# Create logs directory if it doesn't exist
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True) 