import telegram
import logging
import os
import requests
import traceback
import json
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID
)

class NotificationManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.telegram_bot = None
        
        # Initialize Telegram bot if configured
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            self.logger.info(f"Initializing Telegram bot with token: {TELEGRAM_BOT_TOKEN[:4]}...{TELEGRAM_BOT_TOKEN[-4:]} and chat ID: {TELEGRAM_CHAT_ID}")
            try:
                self.telegram_bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
                self.logger.info("Telegram bot initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Telegram bot: {str(e)}")
                self.logger.error(f"Detailed error: {traceback.format_exc()}")
        else:
            self.logger.warning(f"Telegram not configured properly. Token present: {bool(TELEGRAM_BOT_TOKEN)}, Chat ID present: {bool(TELEGRAM_CHAT_ID)}")

    async def verify_telegram_bot(self):
        """Test Telegram bot by getting bot information"""
        if not self.telegram_bot:
            self.logger.warning("Cannot verify Telegram bot: Bot not initialized")
            return False
            
        try:
            self.logger.info("Verifying Telegram bot configuration...")
            bot_info = await self.telegram_bot.get_me()
            self.logger.info(f"Telegram bot verification successful! Bot username: @{bot_info.username}")
            return True
        except Exception as e:
            self.logger.error(f"Telegram bot verification failed: {str(e)}")
            self.logger.error(f"Detailed error: {traceback.format_exc()}")
            return False

    async def send_telegram(self, message):
        """Send notification via Telegram."""
        # First try with python-telegram-bot
        if self.telegram_bot:
            try:
                self.logger.info(f"Attempting to send Telegram message to chat ID: {TELEGRAM_CHAT_ID}")
                # Check if message contains HTML tags
                if '<' in message and '>' in message:
                    self.logger.info("Sending message with HTML parsing")
                    await self.telegram_bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=message,
                        parse_mode='HTML'
                    )
                else:
                    # For plain text messages, don't specify parse_mode
                    self.logger.info("Sending plain text message")
                    await self.telegram_bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=message
                    )
                self.logger.info("Telegram message sent successfully via python-telegram-bot")
                return True
            except Exception as e:
                self.logger.error(f"Failed to send Telegram notification via python-telegram-bot: {str(e)}")
                self.logger.error(f"Detailed error: {traceback.format_exc()}")
        else:
            self.logger.warning("Telegram bot not initialized, trying direct API call")
            
        # Fallback to direct API call if python-telegram-bot fails
        try:
            self.logger.info("Attempting to send message via direct API call")
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML" if ('<' in message and '>' in message) else None
            }
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}
            
            self.logger.info(f"API URL: {url}")
            self.logger.info(f"Payload: {json.dumps(payload)}")
            
            response = requests.post(url, json=payload, timeout=10)
            self.logger.info(f"Direct API response status: {response.status_code}")
            self.logger.info(f"Direct API response: {response.text}")
            
            if response.status_code == 200:
                self.logger.info("Telegram message sent successfully via direct API")
                return True
            else:
                self.logger.error(f"Failed to send via direct API. Status: {response.status_code}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to send via direct API: {str(e)}")
            self.logger.error(f"Detailed error: {traceback.format_exc()}")
            return False

    async def notify(self, subject, message):
        """Send notifications through Telegram."""
        # Format message with HTML for subject
        formatted_message = f"<b>{subject}</b>\n\n{message}" if '<' in message else f"{subject}\n\n{message}"
        return await self.send_telegram(formatted_message) 