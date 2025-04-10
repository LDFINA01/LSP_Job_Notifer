import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import telegram
import logging
import os
import requests
import traceback
import json
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    EMAIL_SMTP_SERVER,
    EMAIL_SMTP_PORT,
    EMAIL_USERNAME,
    EMAIL_PASSWORD
)

class NotificationManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.telegram_bot = None
        
        # Print values to help debug
        self.logger.info(f"TELEGRAM_BOT_TOKEN: {TELEGRAM_BOT_TOKEN[:4]}...{TELEGRAM_BOT_TOKEN[-4:] if TELEGRAM_BOT_TOKEN else 'None'}")
        self.logger.info(f"TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")
        
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

    def send_email(self, subject, message):
        """Send notification via email."""
        if not all([EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, EMAIL_USERNAME, EMAIL_PASSWORD]):
            self.logger.warning("Email notifications not configured")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_USERNAME
            msg['To'] = EMAIL_USERNAME
            msg['Subject'] = subject

            msg.attach(MIMEText(message, 'html'))

            with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
                server.send_message(msg)

            return True
        except Exception as e:
            self.logger.error(f"Failed to send email notification: {str(e)}")
            return False

    async def notify(self, subject, message):
        """Send notifications through all configured channels."""
        success = True

        # Send Telegram notification
        if self.telegram_bot:
            # Format message with HTML for subject but only if it contains HTML tags
            formatted_message = f"<b>{subject}</b>\n\n{message}" if '<' in message else f"{subject}\n\n{message}"
            telegram_success = await self.send_telegram(formatted_message)
            success = success and telegram_success

        # Send email notification
        email_success = self.send_email(subject, message)
        success = success and email_success

        return success 