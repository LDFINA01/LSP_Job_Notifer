import logging
import json
import time
import asyncio
from typing import Dict, List, Optional
import aiohttp
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import traceback

from config import (
    BASE_URL,
    LOGIN_URL,
    JOB_POSTINGS_URL,
    DEFAULT_HEADERS,
    LOGIN_PAYLOAD,
    LOG_LEVEL,
    LOG_FILE
)
from notifications import NotificationManager

class LSPScraper:
    def __init__(self):
        self.logger = self._setup_logger()
        self.session = None
        self.notification_manager = NotificationManager()
        self.seen_jobs = set()
        self.driver = None

    def _setup_logger(self) -> logging.Logger:
        """Set up logging configuration."""
        logger = logging.getLogger('LSPScraper')
        logger.setLevel(LOG_LEVEL)

        # File handler
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setLevel(LOG_LEVEL)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(LOG_LEVEL)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger

    async def _init_session(self):
        """Initialize aiohttp session."""
        if not self.session:
            self.session = aiohttp.ClientSession(headers=DEFAULT_HEADERS)

    async def _close_session(self):
        """Close aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None

    def _init_selenium(self):
        """Initialize Selenium WebDriver."""
        if not self.driver:
            try:
                self.logger.info("Setting up Chrome WebDriver")
                chrome_options = Options()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--log-level=3')  # Suppress console messages
                
                # Try direct approach first (works on most modern systems)
                try:
                    self.logger.info("Initializing Chrome directly")
                    self.driver = webdriver.Chrome(options=chrome_options)
                    self.logger.info("Chrome WebDriver initialized successfully")
                    return
                except Exception as e1:
                    self.logger.warning(f"Direct Chrome initialization failed: {str(e1)}")
                
                # Try with webdriver-manager as fallback
                try:
                    # Use specific version to avoid compatibility issues
                    from webdriver_manager.chrome import ChromeDriverManager
                    from selenium.webdriver.chrome.service import Service
                    
                    driver_path = ChromeDriverManager().install()
                    # Extract directory from path to avoid using the problematic THIRD_PARTY_NOTICES file
                    driver_dir = "/".join(driver_path.split("/")[:-1])
                    self.logger.info(f"Chrome WebDriver installed at directory: {driver_dir}")
                    
                    # Look for chromedriver.exe or chromedriver in that directory
                    import os
                    for possible_driver in ["chromedriver.exe", "chromedriver"]:
                        full_path = os.path.join(driver_dir, possible_driver)
                        if os.path.exists(full_path):
                            self.logger.info(f"Found driver at: {full_path}")
                            service = Service(full_path)
                            self.driver = webdriver.Chrome(service=service, options=chrome_options)
                            self.logger.info("Chrome WebDriver initialized with explicit path")
                            return
                    
                    # If no specific driver found, try with the directory
                    service = Service(driver_dir)
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.logger.info("Chrome WebDriver initialized with directory path")
                except Exception as e2:
                    self.logger.error(f"WebDriver Manager approach failed: {str(e2)}")
                    raise Exception(f"All initialization methods failed: {str(e1)} and {str(e2)}")
                
            except Exception as e:
                self.logger.error(f"Failed to initialize Chrome WebDriver: {str(e)}")
                raise

    def _close_selenium(self):
        """Close Selenium WebDriver."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    async def login(self) -> bool:
        """Log in to the LSP system using Selenium."""
        try:
            self._init_selenium()
            self.logger.info("Initializing browser for login...")
            
            # First visit the login page
            self.logger.info(f"Attempting to visit login page: {LOGIN_URL}")
            self.driver.get(LOGIN_URL)
            self.logger.info("Visited login page")
            
            # Log current URL and page title
            self.logger.info(f"Current URL: {self.driver.current_url}")
            self.logger.info(f"Page title: {self.driver.title}")
            
            # Log page source for debugging
            self.logger.info("Page source preview:")
            self.logger.info(self.driver.page_source[:500])  # First 500 chars
            
            # Wait for the login form to be present
            self.logger.info("Waiting for login form elements...")
            try:
                # Wait for Angular app to load completely - this is crucial for SPAs
                time.sleep(3)
                
                # Find email input using the correct selector
                username_field = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='email']"))
                )
                self.logger.info("Found username field")
            except Exception as e:
                self.logger.error(f"Could not find username field: {str(e)}")
                self.logger.error("Available elements on page:")
                elements = self.driver.find_elements(By.CSS_SELECTOR, "*")
                for elem in elements[:10]:  # Log first 10 elements
                    self.logger.error(f"Element: {elem.tag_name} - {elem.get_attribute('class')}")
                raise
            
            # Find and fill in the username field
            self.logger.info(f"Attempting to enter username: {LOGIN_PAYLOAD['userName']}")
            username_field.clear()
            username_field.send_keys(LOGIN_PAYLOAD['userName'])
            self.logger.info("Entered username")
            
            # Find and fill in the password field
            self.logger.info("Looking for password field")
            try:
                password_field = self.driver.find_element(By.CSS_SELECTOR, "input[name='password']")
                self.logger.info("Found password field")
            except Exception as e:
                self.logger.error(f"Could not find password field: {str(e)}")
                raise
            
            password_field.clear()
            password_field.send_keys(LOGIN_PAYLOAD['userPassword'])
            self.logger.info("Entered password")
            
            # Wait for the login button to be enabled
            self.logger.info("Looking for login button")
            try:
                # Wait for the button to become enabled as Angular updates the form
                time.sleep(1)
                
                # Need to execute JavaScript to enable the button, as it might be disabled until form is valid
                self.driver.execute_script("""
                    document.querySelector("button[name='btn-login']").removeAttribute("disabled");
                """)
                
                login_button = self.driver.find_element(By.CSS_SELECTOR, "button[name='btn-login']")
                self.logger.info("Found login button")
            except Exception as e:
                self.logger.error(f"Could not find login button: {str(e)}")
                self.logger.error("Available buttons on page:")
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for button in buttons:
                    self.logger.error(f"Button text: {button.text} - class: {button.get_attribute('class')}")
                raise
            
            self.logger.info("Clicking login button")
            login_button.click()
            self.logger.info("Clicked login button")
            
            # Wait for successful login (wait for the job portal page to load)
            self.logger.info("Waiting for successful login...")
            try:
                # Allow more time for the SPA to navigate and load
                time.sleep(3)
                
                # Check if we're redirected to another page
                if "/jobs" in self.driver.current_url or "/dashboard" in self.driver.current_url:
                    self.logger.info("Successfully logged in based on URL change")
                    self.logger.info(f"Current URL after login: {self.driver.current_url}")
                    
                    # Send Telegram notification on successful login
                    try:
                        notification_sent = await self.notification_manager.send_telegram("LSP Job Notifier: Application has started and successfully logged in! Now monitoring for new job postings.")
                        if notification_sent:
                            self.logger.info("Login notification sent successfully")
                        else:
                            self.logger.warning("Failed to send login notification")
                    except Exception as e:
                        self.logger.error(f"Error sending login notification: {str(e)}")
                    
                    return True
                    
                # As a fallback, check for elements that appear after login
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "ag-body-viewport"))
                )
                self.logger.info("Successfully logged in")
                self.logger.info(f"Current URL after login: {self.driver.current_url}")
                
                # Send Telegram notification on successful login (fallback path)
                try:
                    notification_sent = await self.notification_manager.send_telegram("LSP Job Notifier: Application has started and successfully logged in! Now monitoring for new job postings.")
                    if notification_sent:
                        self.logger.info("Login notification sent successfully")
                    else:
                        self.logger.warning("Failed to send login notification")
                except Exception as e:
                    self.logger.error(f"Error sending login notification: {str(e)}")
                
                return True
            except Exception as e:
                self.logger.error(f"Login failed: {str(e)}")
                self.logger.error(f"Current URL after failed login: {self.driver.current_url}")
                self.logger.error("Page source after failed login:")
                self.logger.error(self.driver.page_source[:1000])  # First 1000 chars
                return False
                
        except Exception as e:
            self.logger.error(f"Login error: {str(e)}")
            self.logger.error("Full error details:", exc_info=True)
            return False

    def _extract_job_details(self, job_element) -> Dict:
        """Extract job details from a job element."""
        try:
            # Convert the row to string to generate a unique ID
            job_id = hash(str(job_element))
            
            # Extract cell contents - adjust these selectors based on inspection of actual page
            cells = job_element.find_all('div', class_='ag-cell')
            
            if not cells or len(cells) < 3:
                self.logger.warning(f"Found job element but couldn't extract enough cells: {len(cells) if cells else 0} cells")
                return None
            
            # Logging the first job's structure to help debug
            if job_id not in self.seen_jobs:
                self.logger.info(f"Job element structure: {len(cells)} cells found")
                for i, cell in enumerate(cells):
                    self.logger.info(f"Cell {i}: {cell.text.strip()}")
            
            # Extract data from cells - indexes may need adjustment
            job_data = {
                'id': job_id,
                'title': cells[0].text.strip() if len(cells) > 0 else "Unknown Title",
                'location': cells[1].text.strip() if len(cells) > 1 else "Unknown Location",
                'date': cells[2].text.strip() if len(cells) > 2 else "Unknown Date",
                'description': cells[3].text.strip() if len(cells) > 3 else "No description available"
            }
            
            return job_data
        except Exception as e:
            self.logger.error(f"Error extracting job details: {str(e)}")
            return None

    async def check_jobs(self) -> List[Dict]:
        """Check for new job postings."""
        try:
            self._init_selenium()
            self.driver.get(JOB_POSTINGS_URL)
            
            # Wait for AG-Grid to load and be visible
            self.logger.info("Waiting for job listings grid to load...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "ag-center-cols-container"))
            )
            
            # Additional wait to ensure grid data is loaded
            time.sleep(2)
            
            # Find the grid container
            grid_container = self.driver.find_element(By.CLASS_NAME, "ag-center-cols-container")
            
            # Find all row elements within the grid
            job_elements = grid_container.find_elements(By.CLASS_NAME, "ag-row")
            
            self.logger.info(f"Found {len(job_elements)} job elements in the grid")
            
            new_jobs = []
            for job_element in job_elements:
                try:
                    # Extract cells from the row
                    cells = job_element.find_elements(By.CLASS_NAME, "ag-cell")
                    
                    if len(cells) >= 4:  # Ensure we have all required cells
                        job_id = cells[0].text.strip()
                        client = cells[1].text.strip()
                        appointment_time = cells[2].text.strip()
                        duration = cells[3].text.strip()
                        
                        job_details = {
                            'id': job_id,
                            'title': f"Interpretation for {client}",
                            'client': client,
                            'date': appointment_time,
                            'duration': duration,
                            'description': f"Duration: {duration} minutes\nTime: {appointment_time}\nClient: {client}"
                        }

                        self.logger.info(f"Found new job: {job_details}")
                        new_jobs.append(job_details)
                        self.seen_jobs.add(job_id)
                
                except Exception as e:
                    self.logger.error(f"Error processing job element: {str(e)}")
                    continue
            
            if not new_jobs:
                self.logger.info("No new jobs found in the grid")
            else:
                self.logger.info(f"Found {len(new_jobs)} new jobs")
            
            return new_jobs
            
        except Exception as e:
            self.logger.error(f"Error checking jobs: {str(e)}")
            self.logger.error(f"Detailed error: {traceback.format_exc()}")
            return []

    async def process_new_jobs(self, jobs: List[Dict]):
        """Process new job postings and send notifications."""
        for job in jobs:
            subject = f"New Job Available: {job['title']}"
            message = f"""
            <h2>New Job Available!</h2>
            <p><strong>Title:</strong> {job['title']}</p>
            <p><strong>Location:</strong> {job['location']}</p>
            <p><strong>Date:</strong> {job['date']}</p>
            <p><strong>Description:</strong> {job['description']}</p>
            <p><a href="{JOB_POSTINGS_URL}">View Job</a></p>
            """
            
            await self.notification_manager.notify(subject, message)
            self.logger.info(f"Notification sent for job: {job['id']}")

    async def run(self):
        """Main execution loop."""
        # Verify notification systems on startup
        await self._verify_notification_systems()
        
        while True:
            try:
                # Login
                if not await self.login():
                    self.logger.error("Failed to login, retrying in 60 seconds...")
                    await asyncio.sleep(60)
                    continue

                # Check for new jobs
                new_jobs = await self.check_jobs()
                
                if new_jobs:
                    self.logger.info(f"Found {len(new_jobs)} new jobs")
                    await self.process_new_jobs(new_jobs)
                else:
                    self.logger.info("No new jobs found")

                # Wait before next check
                await asyncio.sleep(300)  # 5 minutes

            except Exception as e:
                self.logger.error(f"Error in main loop: {str(e)}")
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def cleanup(self):
        """Clean up resources."""
        await self._close_session()
        self._close_selenium()

    async def _verify_notification_systems(self):
        """Verify all notification systems on startup"""
        self.logger.info("Verifying notification systems...")
        # Test Telegram
        await self.notification_manager.verify_telegram_bot() 