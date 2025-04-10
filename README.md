# LSP Job Notifier

An automated server-side scraper that monitors the LSP scheduling system for interpreter job postings and sends notifications when new appointments are available.

## Features

- Automated login and session management
- Real-time monitoring of job postings
- Multiple notification channels (Email, Telegram)
- Robust error handling and logging
- Automatic session recovery
- Configurable scraping intervals

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
4. Configure your notification preferences in the `.env` file

## Environment Variables

Create a `.env` file with the following variables:

```
# LSP Credentials
LSP_USERNAME=your_email@example.com
LSP_PASSWORD=your_password

# Notification Settings
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_specific_password

# Scraping Settings
SCRAPE_INTERVAL=300  # seconds
```

## Usage

Run the scraper:
```bash
python main.py
```

The scraper will:
1. Log in to the LSP system
2. Monitor for new job postings
3. Send notifications when new appointments are found
4. Automatically handle session management and re-authentication

## Error Handling

The scraper includes comprehensive error handling for:
- Failed login attempts
- Session timeouts
- Network issues
- Invalid credentials
- Rate limiting

## Logging

Logs are stored in `logs/` directory with the following information:
- Login attempts and results
- Job posting updates
- Error messages and stack traces
- Session management events

## Security

- Credentials are stored securely in environment variables
- All communications use HTTPS
- Session cookies are managed securely
- No sensitive data is logged

## Maintenance

Regular updates may be required if the LSP system changes its:
- HTML structure
- API endpoints
- Authentication mechanism
- Cookie handling

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request 