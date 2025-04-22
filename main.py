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
    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--test-notification':
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
        # Start the monitoring in quiet mode
        print("LSP Job Notifier started. Running in background mode with minimal output.")
        print("Press Ctrl+C to stop.")
        await scraper.run()
    except Exception as e:
        print(f"Fatal error: {str(e)}")
    finally:
        await scraper.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 