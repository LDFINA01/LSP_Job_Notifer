import logging
import json
import time
import asyncio
import os
import glob
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
from logging.handlers import RotatingFileHandler

from config import (
    BASE_URL,
    LOGIN_URL,
    JOB_POSTINGS_URL,
    DEFAULT_HEADERS,
    LOGIN_PAYLOAD,
    LOG_LEVEL,
    LOG_FILE,
    MAX_DATA_FILES,
    MAX_SCREENSHOT_FILES,
    CLEANUP_OLD_FILES
)
from notifications import NotificationManager

class LSPScraper:
    def __init__(self):
        self.logger = self._setup_logger()
        self.session = None
        self.notification_manager = NotificationManager()
        self.seen_jobs = set()
        self.driver = None
        if CLEANUP_OLD_FILES:
            self._clean_old_files()

    def _setup_logger(self) -> logging.Logger:
        """Set up logging configuration."""
        logger = logging.getLogger('LSPScraper')
        logger.setLevel(LOG_LEVEL)

        # File handler with rotation to limit file size
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,  # 5 MB max size
            backupCount=3  # Keep 3 backup files
        )
        file_handler.setLevel(LOG_LEVEL)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        
        # Only use file handler, not console handler for quieter operation
        logger.addHandler(file_handler)
        
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
                
                # Use the following options for a more stealthy approach 
                # (less likely to be detected as automated browser)
                chrome_options.add_argument('--headless=new')  # Use newer headless implementation
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--window-size=1920,1080')  # Set a standard window size
                chrome_options.add_argument('--start-maximized')
                
                # Disable logging
                chrome_options.add_argument('--log-level=3')
                
                # Set user agent to match a regular Chrome browser
                chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
                
                # Exclude the "Chrome is being controlled by automated test software" info bar
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                # Try direct approach first (works on most modern systems)
                try:
                    self.logger.info("Initializing Chrome directly")
                    self.driver = webdriver.Chrome(options=chrome_options)
                    
                    # Apply additional settings directly to the driver
                    self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                    })
                    
                    # Execute stealth JS 
                    self.driver.execute_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                    )
                    
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
                            
                            # Apply additional settings
                            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                            })
                            
                            # Execute stealth JS
                            self.driver.execute_script(
                                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                            )
                            
                            self.logger.info("Chrome WebDriver initialized with explicit path")
                            return
                    
                    # If no specific driver found, try with the directory
                    service = Service(driver_dir)
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.logger.info("Chrome WebDriver initialized with directory path")
                    
                    # Apply additional settings
                    self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                    })
                    
                    # Execute stealth JS
                    self.driver.execute_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                    )
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
            
            # Allow more time for the SPA to navigate and load
            time.sleep(5)
            
            # Save current URL for debugging
            current_url = self.driver.current_url
            self.logger.info(f"URL after login attempt: {current_url}")
            
            # Check if we're redirected to another page that indicates successful login
            successful_login = False
            
            # Common URL patterns that indicate successful login
            success_patterns = ["/jobs", "/dashboard", "/interpreter-portal", "/home"]
            for pattern in success_patterns:
                if pattern in current_url:
                    self.logger.info(f"Successfully logged in based on URL change, found pattern: {pattern}")
                    successful_login = True
                    break
            
            # If we don't see a successful login pattern in the URL, try looking for elements that appear after login
            if not successful_login:
                try:
                    self.logger.info("Checking for post-login elements...")
                    
                    # Try to find common elements that appear after login
                    post_login_selectors = [
                        (By.CLASS_NAME, "ag-body-viewport"),
                        (By.CLASS_NAME, "dashboard-container"),
                        (By.CSS_SELECTOR, ".logout-button"),
                        (By.CSS_SELECTOR, "[class*='user-profile']"),
                        (By.CSS_SELECTOR, ".main-content"),
                        (By.XPATH, "//span[contains(text(), 'Log out')]"),
                        (By.XPATH, "//div[contains(text(), 'Dashboard')]")
                    ]
                    
                    for selector_type, selector in post_login_selectors:
                        try:
                            element = WebDriverWait(self.driver, 3).until(
                                EC.presence_of_element_located((selector_type, selector))
                            )
                            self.logger.info(f"Found post-login element: {selector}")
                            successful_login = True
                            break
                        except Exception:
                            continue
                except Exception as e:
                    self.logger.warning(f"Error while checking for post-login elements: {str(e)}")
            
            # If we still can't confirm login, take a screenshot and check for key text in page
            if not successful_login:
                try:
                    # Save screenshot for debugging
                    self.driver.save_screenshot("screenshots/login_result.png")
                    self.logger.info("Saved screenshot of post-login page to screenshots/login_result.png")
                    
                    # Check if page source contains any indication of successful login
                    page_source = self.driver.page_source.lower()
                    login_indicators = ["logout", "welcome", "dashboard", "profile", "interpreter portal"]
                    
                    for indicator in login_indicators:
                        if indicator in page_source:
                            self.logger.info(f"Found login indicator in page source: '{indicator}'")
                            successful_login = True
                            break
                except Exception as e:
                    self.logger.warning(f"Error while taking screenshot: {str(e)}")
            
            # Always try to navigate to interpreter portal, which is where we need to be
            if successful_login or "/login" not in current_url:
                try:
                    # Navigate to the interpreter portal explicitly
                    portal_url = f"{BASE_URL}/scheduler/#/interpreter-portal"
                    self.logger.info(f"Login appears successful. Navigating to interpreter portal: {portal_url}")
                    self.driver.get(portal_url)
                    time.sleep(5)  # Wait for portal to load
                    
                    # Save portal page source for debugging
                    with open("data/portal_after_login.html", "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                    self.logger.info("Saved portal page source to data/portal_after_login.html")
                    
                    return True
                except Exception as e:
                    self.logger.error(f"Error navigating to interpreter portal: {str(e)}")
                    return False
            else:
                self.logger.error("Login failed: Still on login page or not redirected properly")
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

    async def process_new_jobs(self, jobs: List[Dict]):
        """Process and notify about new jobs."""
        self.logger.info(f"Processing {len(jobs)} new jobs")
        
        for job in jobs:
            self.logger.info(f"Processing job: {job}")
            
            # Convert legacy format if needed
            job_data = self._normalize_job_format(job)
            
            # Create a detailed notification message
            subject = f"New Job Available: {job_data['client_name']}"
            
            message = (
                f"<b>Client:</b> {job_data['client_name']}\n"
                f"<b>Time:</b> {job_data['appointment_time']}\n"
                f"<b>Duration:</b> {job_data['duration']}\n"
                f"<b>Location:</b> {job_data['location']}\n\n"
                f"<b>Job ID:</b> {job_data['id']}"
            )
            
            # Try to send notification with extra retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.logger.info(f"Sending notification for job (attempt {attempt+1}/{max_retries})")
                    notification_sent = await self.notification_manager.notify(subject, message)
                    
                    if notification_sent:
                        self.logger.info(f"Notification sent for job: {job_data['id']}")
                        break
                    else:
                        self.logger.warning(f"Failed to send notification, attempt {attempt+1}/{max_retries}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)  # Wait before retry
                except Exception as e:
                    self.logger.error(f"Error sending notification: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)  # Wait before retry
            else:
                self.logger.error(f"All attempts to send notification failed for job: {job_data['id']}")
    
    def _normalize_job_format(self, job):
        """Normalize job data from different formats to a standard format"""
        # Initialize with default empty values
        normalized_job = {
            "id": "",
            "client_name": "",
            "appointment_time": "",
            "duration": "",
            "location": "",
            "description": ""
        }
        
        # Check what format the job data is in and convert appropriately
        if isinstance(job, dict):
            # If job already has the expected keys, use them directly
            for key in normalized_job:
                if key in job:
                    normalized_job[key] = job[key]
            
            # Handle legacy format with different key names
            if "client" in job and not normalized_job["client_name"]:
                normalized_job["client_name"] = job["client"]
            
            if "title" in job:
                if not normalized_job["description"]:
                    normalized_job["description"] = job["title"]
            
            if "date" in job and not normalized_job["appointment_time"]:
                normalized_job["appointment_time"] = job["date"]
                
            # Ensure we have an ID
            if not normalized_job["id"] and "id" in job:
                normalized_job["id"] = job["id"]
            elif not normalized_job["id"]:
                # Generate a random ID if none exists
                import random
                normalized_job["id"] = f"job-{random.randint(1000, 9999)}"
        
        # Ensure we have at least basic info for the notification
        if not normalized_job["client_name"]:
            normalized_job["client_name"] = "Unknown Client"
            
        if not normalized_job["description"]:
            normalized_job["description"] = "Job details not available"
        
        return normalized_job

    async def run(self):
        """Main execution loop."""
        # Verify notification systems on startup
        await self._verify_notification_systems()
        
        # Send startup notification
        await self.notification_manager.send_telegram("LSP Job Notifier: Application has started and is now monitoring for new job postings.")
        
        # Track runs for periodic cleanup
        run_count = 0
        
        while True:
            try:
                # Increment run counter
                run_count += 1
                
                # Periodic cleanup (every 10 runs)
                if CLEANUP_OLD_FILES and run_count % 10 == 0:
                    self._clean_old_files()
                
                # Login
                if not await self.login():
                    self.logger.error("Failed to login, retrying in 60 seconds...")
                    await asyncio.sleep(60)
                    continue

                # Check for new jobs using the direct DOM navigation approach
                self.logger.info("Checking for new jobs...")
                new_jobs = await self.check_jobs_direct()
                
                if new_jobs:
                    self.logger.info(f"Found {len(new_jobs)} new jobs")
                    await self.process_new_jobs(new_jobs)
                else:
                    self.logger.info("No new jobs found")

                # Wait before next check
                await asyncio.sleep(30)  # 30 seconds instead of 300 (5 minutes)

            except Exception as e:
                self.logger.error(f"Error in main loop: {str(e)}")
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def cleanup(self):
        """Clean up resources."""
        try:
            # Send shutdown notification
            await self.notification_manager.send_telegram("LSP Job Notifier: Application has closed.")
            self.logger.info("Sent application shutdown notification")
        except Exception as e:
            self.logger.error(f"Error sending shutdown notification: {str(e)}")
        
        await self._close_session()
        self._close_selenium()
        self.logger.info("Application resources cleaned up")

    async def _verify_notification_systems(self):
        """Verify Telegram notification system on startup"""
        self.logger.info("Verifying Telegram notification system...")
        return await self.notification_manager.verify_telegram_bot()
    
    async def check_jobs_direct(self) -> List[Dict]:
        """Check for open jobs by directly navigating the DOM structure."""
        try:
            self._init_selenium()
            
            # Navigate to the interpreter portal first - this is where we landed after login
            portal_url = f"{BASE_URL}/scheduler/#/interpreter-portal"
            self.logger.info(f"Navigating to interpreter portal: {portal_url}")
            self.driver.get(portal_url)
            
            # Wait for page to load
            self.logger.info("Waiting for interpreter portal to load...")
            time.sleep(5)
            
            # Save screenshot for debugging
            screenshot_path = os.path.join("data", "portal_screen.png")
            self.driver.save_screenshot(screenshot_path)
            self.logger.info(f"Saved portal screenshot to {screenshot_path}")

            # Save page source for debugging
            with open(os.path.join("data", "portal_direct.html"), "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            self.logger.info("Saved portal page source")
            
            # First, find the Open Jobs tab
            self.logger.info("Looking for 'Open Jobs' tab...")
            try:
                # Try different selectors for the Open Jobs tab
                selectors = [
                    "//span[text()='Open Jobs']",
                    "//div[contains(text(), 'Open Jobs')]", 
                    "//a[contains(text(), 'Open Jobs')]",
                    "//span[contains(@class, 'tab-text') and text()='Open Jobs']",
                    "//li[contains(@class, 'mat-tab-label')]//span[contains(text(), 'Open Jobs')]"
                ]
                
                tab_found = False
                for selector in selectors:
                    try:
                        self.logger.info(f"Trying selector: {selector}")
                        open_jobs_tab = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        self.logger.info(f"Found 'Open Jobs' tab with selector: {selector}")
                        
                        # Take screenshot before click
                        self.driver.save_screenshot(os.path.join("data", "before_tab_click.png"))
                        
                        # Try to click the tab
                        self.logger.info(f"Clicking tab element: {open_jobs_tab.text}")
                        self.driver.execute_script("arguments[0].click();", open_jobs_tab)
                        tab_found = True
                        self.logger.info("Clicked on 'Open Jobs' tab")
                        
                        # Take screenshot after click
                        time.sleep(2)
                        self.driver.save_screenshot(os.path.join("data", "after_tab_click.png"))
                        break
                    except Exception as tab_ex:
                        self.logger.warning(f"Error with selector {selector}: {str(tab_ex)}")
                        continue
                
                if not tab_found:
                    self.logger.warning("Could not find 'Open Jobs' tab, attempting to continue anyway")
            except Exception as e:
                self.logger.warning(f"Error finding/clicking 'Open Jobs' tab: {str(e)}")
            
            # Wait after tab click
            time.sleep(3)
            
            # Save page source after clicking tab
            with open(os.path.join("data", "after_tab_click.html"), "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            
            # Try multiple approaches to find jobs
            
            # Approach 1: Find any grid component
            self.logger.info("Approach 1: Looking for any grid component...")
            try:
                # Look for ag-grid components
                grid_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                                                     "ag-grid-angular, .ag-root, [role='grid'], table.grid")
                
                if grid_elements:
                    self.logger.info(f"Found {len(grid_elements)} grid elements")
                    # Take screenshot of the grid
                    self.driver.save_screenshot(os.path.join("data", "grid_screen.png"))
                    
                    new_jobs = []
                    # For each grid, try to extract rows
                    for idx, grid in enumerate(grid_elements):
                        try:
                            # Try to find rows with various selectors
                            rows = grid.find_elements(By.CSS_SELECTOR, 
                                                  "div[role='row'], .ag-row, tr")
                            
                            self.logger.info(f"Grid {idx} has {len(rows)} rows")
                            
                            # Process each row to extract job information
                            for row in rows:
                                try:
                                    # Skip header rows
                                    if "header" in row.get_attribute("class").lower():
                                        continue
                                        
                                    # Get row text for logging
                                    row_text = row.text.strip()
                                    
                                    # Only process if row has content
                                    if not row_text:
                                        continue
                                        
                                    self.logger.info(f"Processing row: {row_text}")
                                    
                                    # Extract job ID
                                    job_id = row.get_attribute("row-id") or f"job-{idx}-{rows.index(row)}"
                                    
                                    # Find cells
                                    cells = row.find_elements(By.CSS_SELECTOR, 
                                                          "div[role='gridcell'], .ag-cell, td")
                                    
                                    # If no job details but row has text, create a simple job entry
                                    if len(cells) < 2 and row_text:
                                        # Create job with the row text
                                        job_details = {
                                            "id": job_id,
                                            "client_name": row_text,
                                            "appointment_time": "",
                                            "duration": "",
                                            "location": "",
                                            "description": row_text
                                        }
                                        new_jobs.append(job_details)
                                        self.logger.info(f"Added simplified job: {job_details}")
                                        continue
                                    
                                    # Normal job extraction with cells
                                    job_details = self._extract_job_details_from_cells(job_id, cells)
                                    
                                    # Check if job is already seen
                                    if job_details["id"] not in self.seen_jobs:
                                        new_jobs.append(job_details)
                                        self.seen_jobs.add(job_details["id"])
                                except Exception as row_ex:
                                    self.logger.warning(f"Error processing row: {str(row_ex)}")
                        except Exception as grid_ex:
                            self.logger.warning(f"Error processing grid {idx}: {str(grid_ex)}")
                    
                    return new_jobs
            except Exception as e:
                self.logger.warning(f"Error in approach 1: {str(e)}")
            
            # Approach 2: Look for any tables or list elements that might contain jobs
            self.logger.info("Approach 2: Looking for any tables or job lists...")
            try:
                job_containers = self.driver.find_elements(By.CSS_SELECTOR, 
                                                       "table, ul.job-list, div.job-container")
                
                if job_containers:
                    self.logger.info(f"Found {len(job_containers)} potential job containers")
                    # Further processing logic here
            except Exception as e:
                self.logger.warning(f"Error in approach 2: {str(e)}")
            
            # If we couldn't find jobs with either approach, return empty list
            return []
            
        except Exception as e:
            self.logger.error(f"Error checking for jobs: {str(e)}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return []
    
    def _extract_job_details_from_cells(self, job_id, cells):
        """Extract job details from cells in a grid row"""
        # Default values
        job_details = {
            "id": job_id,
            "client_name": "",
            "appointment_time": "",
            "duration": "",
            "location": "",
            "description": ""
        }
        
        # Check for col-id attribute in cells
        for idx, cell in enumerate(cells):
            try:
                col_id = cell.get_attribute("col-id")
                cell_text = cell.text.strip()
                
                self.logger.info(f"Cell {idx} col-id: {col_id}, text: {cell_text}")
                
                # Map cell to job details based on col-id or position
                if col_id:
                    if col_id == "requestID":
                        job_details["id"] = cell_text or job_id
                    elif col_id == "customerName" or col_id == "customer":
                        job_details["client_name"] = cell_text
                    elif col_id == "interpretationTime" or col_id == "scheduledTime":
                        job_details["appointment_time"] = cell_text
                    elif col_id == "estimateDuration" or col_id == "duration":
                        job_details["duration"] = cell_text
                    elif col_id == "address" or col_id == "location":
                        job_details["location"] = cell_text
                else:
                    # If no col-id, use position-based mapping
                    if idx == 0:
                        job_details["id"] = cell_text or job_id
                    elif idx == 1:
                        job_details["client_name"] = cell_text
                    elif idx == 2:
                        job_details["appointment_time"] = cell_text
                    elif idx == 3:
                        job_details["duration"] = cell_text
                    elif idx == 4:
                        job_details["location"] = cell_text
            except Exception as e:
                self.logger.warning(f"Error processing cell {idx}: {str(e)}")
        
        # Create description from available details
        job_details["description"] = (
            f"Client: {job_details['client_name']}\n"
            f"Time: {job_details['appointment_time']}\n"
            f"Duration: {job_details['duration']}\n"
            f"Location: {job_details['location']}"
        )
        
        return job_details

    def _clean_old_files(self):
        """Clean up old data and screenshot files to prevent disk space issues."""
        try:
            # Clean HTML data files
            data_files = glob.glob('data/*.html')
            if len(data_files) > MAX_DATA_FILES:
                # Sort by modified time (oldest first)
                data_files.sort(key=lambda x: os.path.getmtime(x))
                # Remove oldest files, keeping only MAX_DATA_FILES
                for file_to_remove in data_files[:-MAX_DATA_FILES]:
                    try:
                        os.remove(file_to_remove)
                        self.logger.info(f"Removed old data file: {file_to_remove}")
                    except Exception as e:
                        self.logger.warning(f"Failed to remove old data file {file_to_remove}: {str(e)}")
            
            # Clean screenshot files
            screenshot_files = glob.glob('screenshots/*.png')
            if len(screenshot_files) > MAX_SCREENSHOT_FILES:
                # Sort by modified time (oldest first)
                screenshot_files.sort(key=lambda x: os.path.getmtime(x))
                # Remove oldest files, keeping only MAX_SCREENSHOT_FILES
                for file_to_remove in screenshot_files[:-MAX_SCREENSHOT_FILES]:
                    try:
                        os.remove(file_to_remove)
                        self.logger.info(f"Removed old screenshot: {file_to_remove}")
                    except Exception as e:
                        self.logger.warning(f"Failed to remove old screenshot {file_to_remove}: {str(e)}")
                        
        except Exception as e:
            self.logger.error(f"Error during file cleanup: {str(e)}")



if __name__ == "__main__":
    import signal
    import sys
    
    scraper = LSPScraper()
    loop = asyncio.get_event_loop()
    
    # Set up signal handlers for graceful shutdown
    def shutdown_handler(sig, frame):
        print("Shutting down...")
        loop.run_until_complete(scraper.cleanup())
        loop.stop()
        sys.exit(0)
    
    # Register shutdown handlers
    signal.signal(signal.SIGINT, shutdown_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, shutdown_handler)  # Termination signal
    
    try:
        loop.run_until_complete(scraper.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(scraper.cleanup())
        loop.close() 