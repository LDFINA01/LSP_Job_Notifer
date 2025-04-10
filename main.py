import asyncio
import signal
import sys
from scraper import LSPScraper

async def send_test_notification():
    """Send a test notification to verify the notification system"""
    scraper = LSPScraper()
    await scraper.notification_manager.send_telegram("This is a test notification from LSP Job Notifier")
    await scraper.cleanup()

async def main():
    # Check if we should just send a test notification
    if len(sys.argv) > 1 and sys.argv[1] == '--test-notification':
        print("Sending test notification...")
        await send_test_notification()
        return
        
    scraper = LSPScraper()
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutting down gracefully...")
        asyncio.create_task(scraper.cleanup())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await scraper.run()
    except Exception as e:
        print(f"Fatal error: {str(e)}")
    finally:
        await scraper.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 