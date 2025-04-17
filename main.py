import asyncio
import signal
import sys
from scraper import LSPScraper

async def send_test_notification():
    """Send a test notification to verify the notification system"""
    scraper = LSPScraper()
    await scraper.notification_manager.send_telegram("This is a test notification from LSP Job Notifier")
    await scraper.cleanup()

async def debug_closed_jobs():
    """Debug function to check closed jobs"""
    scraper = LSPScraper()
    print("Checking closed jobs for debugging...")
    try:
        # Ensure we're logged in
        login_success = await scraper.login()
        if not login_success:
            print("Failed to log in, cannot check closed jobs")
            return
        
        # Check closed jobs
        closed_jobs = await scraper.check_closed_jobs()
        
        # Print results
        print(f"\n{'='*50}")
        print(f"FOUND {len(closed_jobs)} CLOSED JOBS")
        print(f"{'='*50}")
        
        for i, job in enumerate(closed_jobs):
            print(f"\nJOB #{i+1}:")
            print(f"ID: {job['id']}")
            print(f"Title: {job['title']}")
            print(f"Client: {job['client']}")
            print(f"Date: {job['date']}")
            print(f"Duration: {job['duration']}")
            print(f"Location: {job['location']}")
            print(f"Description: {job['description']}")
            print("-" * 30)
        
        print("\nDebugging complete. Check logs and screenshots for more details.")
    except Exception as e:
        print(f"Error during debugging: {str(e)}")
    finally:
        await scraper.cleanup()

async def debug_direct_jobs():
    """Debug function to check jobs using the direct DOM navigation approach"""
    scraper = LSPScraper()
    print("Checking jobs using direct DOM navigation approach...")
    try:
        # Ensure we're logged in
        login_success = await scraper.login()
        if not login_success:
            print("Failed to log in, cannot check jobs")
            return
        
        # Check jobs using direct approach
        jobs = await scraper.check_jobs_direct()
        
        # Print results
        print(f"\n{'='*50}")
        print(f"FOUND {len(jobs)} JOBS USING DIRECT APPROACH")
        print(f"{'='*50}")
        
        for i, job in enumerate(jobs):
            print(f"\nJOB #{i+1}:")
            print(f"ID: {job['id']}")
            print(f"Title: {job['title']}")
            print(f"Client: {job['client']}")
            print(f"Date: {job['date']}")
            print(f"Duration: {job['duration']}")
            print(f"Location: {job['location']}")
            print(f"Description: {job['description']}")
            print("-" * 30)
        
        print("\nDebugging complete. Check logs and screenshots for more details.")
    except Exception as e:
        print(f"Error during debugging: {str(e)}")
    finally:
        await scraper.cleanup()

async def main():
    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--test-notification':
            print("Sending test notification...")
            await send_test_notification()
            return
        elif sys.argv[1] == '--debug-closed-jobs':
            await debug_closed_jobs()
            return
        elif sys.argv[1] == '--debug-direct-jobs':
            await debug_direct_jobs()
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