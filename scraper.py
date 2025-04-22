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
                    
                    # Send Telegram notification on successful login
                    try:
                        notification_sent = await self.notification_manager.send_telegram("LSP Job Notifier: Application has started and successfully logged in! Now monitoring for new job postings.")
                        if notification_sent:
                            self.logger.info("Login notification sent successfully")
                        else:
                            self.logger.warning("Failed to send login notification")
                    except Exception as e:
                        self.logger.error(f"Error sending login notification: {str(e)}")
                    
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
        """Process new job postings and send notifications."""
        for job in jobs:
            subject = f"New Job Available: {job['title']}"
            message = f"""
<b>New Interpretation Job Available!</b>

<b>Client:</b> {job['client']}
<b>Date:</b> {job['date']}
<b>Duration:</b> {job['duration']} minutes
<b>Location:</b> {job['location']}

<a href="{JOB_POSTINGS_URL}">View Job in Portal</a>
            """
            
            notification_sent = await self.notification_manager.notify(subject, message)
            if notification_sent:
                self.logger.info(f"Notification sent for job: {job['id']}")
            else:
                self.logger.warning(f"Failed to send notification for job: {job['id']}")

    async def run(self):
        """Main execution loop."""
        # Verify notification systems on startup
        await self._verify_notification_systems()
        
        # Send startup notification
        await self.notification_manager.send_telegram("LSP Job Notifier: Application has started and is now monitoring for new job postings.")
        
        while True:
            try:
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
            
            # First, find the Open Jobs tab
            self.logger.info("Looking for 'Open Jobs' tab...")
            try:
                # Try different selectors for the Open Jobs tab
                selectors = [
                    "//span[text()='Open Jobs']",
                    "//div[contains(text(), 'Open Jobs')]", 
                    "//a[contains(text(), 'Open Jobs')]",
                    "//span[contains(@class, 'tab-text') and text()='Open Jobs']"
                ]
                
                tab_found = False
                for selector in selectors:
                    try:
                        open_jobs_tab = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        self.logger.info(f"Found 'Open Jobs' tab with selector: {selector}")
                        
                        # Try to click the tab
                        open_jobs_tab.click()
                        tab_found = True
                        self.logger.info("Clicked on 'Open Jobs' tab")
                        break
                    except Exception:
                        continue
                
                if not tab_found:
                    self.logger.warning("Could not find 'Open Jobs' tab, attempting to continue anyway")
            except Exception as e:
                self.logger.warning(f"Error finding/clicking 'Open Jobs' tab: {str(e)}")
            
            # Wait after tab click
            time.sleep(3)
            
            # Following the DOM structure from the user's info
            # Look for the ag-Grid component
            self.logger.info("Looking for ag-Grid component...")
            
            try:
                # Following the exact structure provided:
                # 1. Find the AT-INTERPRETER-JOBS component
                interpreter_jobs = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "at-interpreter-jobs"))
                )
                self.logger.info("Found at-interpreter-jobs component")
                
                # 2. Find AG-GRID-ANGULAR element
                ag_grid = interpreter_jobs.find_element(By.TAG_NAME, "ag-grid-angular")
                self.logger.info("Found ag-grid-angular component")
                
                # 3. Navigate down to the container with the rows
                # Root wrapper
                ag_root_wrapper = ag_grid.find_element(By.CLASS_NAME, "ag-root-wrapper")
                self.logger.info("Found ag-root-wrapper")
                
                # Root wrapper body
                ag_root_wrapper_body = ag_root_wrapper.find_element(By.CLASS_NAME, "ag-root-wrapper-body")
                self.logger.info("Found ag-root-wrapper-body")
                
                # Root
                ag_root = ag_root_wrapper_body.find_element(By.CLASS_NAME, "ag-root")
                self.logger.info("Found ag-root")
                
                # Body viewport
                ag_body_viewport = ag_root.find_element(By.CLASS_NAME, "ag-body-viewport")
                self.logger.info("Found ag-body-viewport")
                
                # Center cols clipper
                ag_center_cols_clipper = ag_body_viewport.find_element(By.CLASS_NAME, "ag-center-cols-clipper")
                self.logger.info("Found ag-center-cols-clipper")
                
                # Center cols viewport
                ag_center_cols_viewport = ag_center_cols_clipper.find_element(By.CLASS_NAME, "ag-center-cols-viewport")
                self.logger.info("Found ag-center-cols-viewport")
                
                # Center cols container - this holds the rows
                ag_center_cols_container = ag_center_cols_viewport.find_element(By.CLASS_NAME, "ag-center-cols-container")
                self.logger.info("Found ag-center-cols-container")
                
                # Find all rows directly in this container
                job_rows = ag_center_cols_container.find_elements(By.CLASS_NAME, "ag-row")
                self.logger.info(f"Found {len(job_rows)} job rows in the ag-grid")
                
                # Process each job row
                new_jobs = []
                for row in job_rows:
                    try:
                        # Get row text for logging
                        row_text = row.text.strip()
                        self.logger.info(f"Job row text: {row_text}")
                        
                        # Find all cells in this row (using the direct role='gridcell' attribute)
                        cells = row.find_elements(By.CSS_SELECTOR, "div[role='gridcell']")
                        self.logger.info(f"Found {len(cells)} cells in job row")
                        
                        # Get row ID from attribute
                        job_id = row.get_attribute("row-id")
                        self.logger.info(f"Row ID: {job_id}")
                        
                        if len(cells) >= 4:
                            # Extract data from cells
                            # According to the user, we look for these specific columns
                            client_name = ""
                            appointment_time = ""
                            duration = ""
                            
                            # Check each cell for the col-id attribute
                            for cell in cells:
                                col_id = cell.get_attribute("col-id")
                                cell_text = cell.text.strip()
                                
                                self.logger.info(f"Cell col-id: {col_id}, text: {cell_text}")
                                
                                if col_id == "requestID" and not job_id:
                                    job_id = cell_text
                                elif col_id == "customerName":
                                    client_name = cell_text
                                elif col_id == "interpretationTime":
                                    appointment_time = cell_text
                                elif col_id == "estimateDuration":
                                    duration = cell_text
                            
                            # If col-id didn't work, try positional (fallback)
                            if not client_name and len(cells) > 1:
                                client_name = cells[1].text.strip()
                            if not appointment_time and len(cells) > 2:
                                appointment_time = cells[2].text.strip()
                            if not duration and len(cells) > 3:
                                duration = cells[3].text.strip()
                            
                            # Create job details
                            job_details = {
                                'id': job_id,
                                'title': f"Interpretation for {client_name}" if client_name else "Interpretation Job",
                                'client': client_name or "Unknown Client",
                                'date': appointment_time or "Unknown Time",
                                'duration': duration or "Unknown Duration",
                                'description': f"Duration: {duration} minutes\nTime: {appointment_time}\nClient: {client_name}",
                                'location': client_name or "Unknown Location"
                            }
                            
                            self.logger.info(f"Extracted job details: {job_details}")
                            
                            # Check if this is a new job we haven't seen before
                            if job_id not in self.seen_jobs:
                                self.logger.info(f"New job found: {job_id}")
                                new_jobs.append(job_details)
                                self.seen_jobs.add(job_id)
                            else:
                                self.logger.info(f"Already seen job: {job_id}")
                        else:
                            self.logger.warning(f"Not enough cells in job row: {len(cells)}")
                    except Exception as e:
                        self.logger.error(f"Error processing job row: {str(e)}")
                        self.logger.error(traceback.format_exc())
                
                if not new_jobs:
                    self.logger.info("No new jobs found in the grid")
                else:
                    self.logger.info(f"Found {len(new_jobs)} new jobs")
                
                return new_jobs
                
            except Exception as e:
                self.logger.error(f"Error navigating DOM structure: {str(e)}")
                self.logger.error(traceback.format_exc())
                return []
                
        except Exception as e:
            self.logger.error(f"Error in check_jobs_direct: {str(e)}")
            self.logger.error(traceback.format_exc())
            return []
    
###    
###    
###    
###    CHECKING CLOSED JOBS TAB
###    
###    
###    
###    
    async def check_closed_jobs(self) -> List[Dict]:
        """Check for closed job postings to help with debugging."""
        try:
            self._init_selenium()
            
            # Navigate to the interpreter portal first
            portal_url = f"{BASE_URL}/scheduler/#/interpreter-portal"
            self.logger.info(f"Navigating to interpreter portal: {portal_url}")
            self.driver.get(portal_url)
            
            # Wait for page to load
            self.logger.info("Waiting for interpreter portal to load...")
            time.sleep(5)
            
            # Save page source for debugging portal page
            with open("data/portal_page.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            self.logger.info("Saved portal page source to data/portal_page.html for debugging")
            
            # Look for the "Closed Jobs" tab or link
            self.logger.info("Looking for 'Closed Jobs' tab or section...")
            
            # Try multiple selectors for the Closed Jobs tab
            selectors = [
                "//span[contains(@class, 'tab-text') and text()='Closed Jobs']",
                "//span[text()='Closed Jobs']",
                "//a[contains(text(), 'Closed Jobs')]",
                "//div[contains(text(), 'Closed Jobs')]",
                "//button[contains(text(), 'Closed Jobs')]"
            ]
            
            tab_found = False
            for selector in selectors:
                try:
                    self.logger.info(f"Trying selector: {selector}")
                    closed_jobs_element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    self.logger.info(f"Found 'Closed Jobs' element with selector: {selector}")
                    
                    # Try to click on the element or its ancestor
                    try:
                        closed_jobs_element.click()
                        self.logger.info("Clicked directly on 'Closed Jobs' element")
                        tab_found = True
                        break
                    except Exception:
                        try:
                            # Try clicking on parent
                            parent = closed_jobs_element.find_element(By.XPATH, "./..")
                            parent.click()
                            self.logger.info("Clicked on parent of 'Closed Jobs' element")
                            tab_found = True
                            break
                        except Exception:
                            try:
                                # Try clicking via JavaScript
                                self.driver.execute_script("arguments[0].click();", closed_jobs_element)
                                self.logger.info("Clicked 'Closed Jobs' element via JavaScript")
                                tab_found = True
                                break
                            except Exception as e:
                                self.logger.warning(f"Found element but couldn't click: {str(e)}")
                except Exception:
                    continue
            
            if not tab_found:
                self.logger.error("Could not find or click on 'Closed Jobs' tab. Taking screenshot.")
                self.driver.save_screenshot("screenshots/closed_jobs_not_found.png")
                return []
            
            # Wait after tab click
            self.logger.info("Waiting for Closed Jobs content to load after navigation...")
            time.sleep(5)
            
            # Save page source after navigation
            with open("data/closed_jobs_page.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            self.logger.info("Saved closed jobs page source to data/closed_jobs_page.html for debugging")
            
            # Take a screenshot of the closed jobs tab
            self.driver.save_screenshot("screenshots/closed_jobs_tab.png")
            self.logger.info("Saved screenshot of closed jobs tab to screenshots/closed_jobs_tab.png")
            
            # Try multiple approaches to find the grid or table
            self.logger.info("Looking for job grid or table...")
            
            # We'll try to find any of these common grid/table structures
            grid_selectors = [
                (By.CLASS_NAME, "ag-root-wrapper"),
                (By.CLASS_NAME, "ag-center-cols-container"),
                (By.CSS_SELECTOR, "div[role='grid']"),
                (By.CSS_SELECTOR, "table"),
                (By.CSS_SELECTOR, ".grid"),
                (By.CSS_SELECTOR, ".table"),
                (By.CSS_SELECTOR, "[id*='grid']"),
                (By.CSS_SELECTOR, "[id*='table']"),
                (By.CSS_SELECTOR, "[class*='grid']"),
                (By.CSS_SELECTOR, "[class*='table']")
            ]
            
            grid_element = None
            for selector_type, selector in grid_selectors:
                try:
                    self.logger.info(f"Trying to find grid with {selector_type}: {selector}")
                    grid_element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((selector_type, selector))
                    )
                    self.logger.info(f"Found grid element with selector: {selector}")
                    break
                except Exception:
                    continue
            
            if not grid_element:
                self.logger.warning("Could not find any grid element. Taking screenshot for debugging.")
                self.driver.save_screenshot("screenshots/closed_jobs_debug_screenshot.png")
                self.logger.info("Saved screenshot to screenshots/closed_jobs_debug_screenshot.png")
                return []
            
            # Once we've found a grid container, look for rows
            self.logger.info("Looking for job rows...")
            
            # Try different row selectors
            row_selectors = [
                (By.CSS_SELECTOR, "div[role='row']"),
                (By.CLASS_NAME, "ag-row"),
                (By.TAG_NAME, "tr"),
                (By.CSS_SELECTOR, ".row"),
                (By.CSS_SELECTOR, "[class*='row']")
            ]
            
            job_elements = []
            for selector_type, selector in row_selectors:
                try:
                    # Try to find rows within the grid element first
                    elements = grid_element.find_elements(selector_type, selector)
                    if elements:
                        self.logger.info(f"Found {len(elements)} rows with selector {selector} within grid element")
                        job_elements = elements
                        break
                    
                    # If that fails, search the entire page
                    elements = self.driver.find_elements(selector_type, selector)
                    if elements:
                        self.logger.info(f"Found {len(elements)} rows with selector {selector} in entire page")
                        job_elements = elements
                        break
                except Exception as e:
                    self.logger.warning(f"Error finding rows with selector {selector}: {str(e)}")
            
            self.logger.info(f"Found {len(job_elements)} potential job elements in Closed Jobs tab")
            
            # If no job elements found via selectors, log an error and return empty list
            if not job_elements:
                self.logger.warning("No job rows found in Closed Jobs tab with standard selectors.")
                return []
            
            closed_jobs = []
            for job_element in job_elements[:10]:  # Process up to 10 jobs for debugging
                try:
                    # Try to get text content of the entire row first to log it
                    row_text = job_element.text.strip()
                    if row_text:
                        self.logger.info(f"Closed job row text: {row_text}")
                    
                    # Try multiple ways to extract cells from the row
                    cells = []
                    
                    # Method 1: role="gridcell"
                    cells = job_element.find_elements(By.CSS_SELECTOR, "div[role='gridcell']")
                    
                    # Method 2: ag-cell class
                    if not cells or len(cells) < 3:
                        cells = job_element.find_elements(By.CLASS_NAME, "ag-cell")
                    
                    # Method 3: td elements for table structures
                    if not cells or len(cells) < 3:
                        cells = job_element.find_elements(By.TAG_NAME, "td")
                    
                    # Method 4: any div that might be a cell
                    if not cells or len(cells) < 3:
                        cells = job_element.find_elements(By.TAG_NAME, "div")
                    
                    self.logger.info(f"Found {len(cells)} cells in closed job element")
                    
                    # Try to get a job ID
                    job_id = job_element.get_attribute("row-id") or job_element.get_attribute("id")
                    
                    # If we couldn't get an ID attribute, create one from the row content
                    if not job_id and row_text:
                        job_id = str(hash(row_text))
                    elif not job_id and cells and len(cells) > 0:
                        job_id = str(hash(cells[0].text if cells[0].text else "unknown"))
                    
                    # Parse the cells if we have enough
                    if len(cells) >= 2:  # Even with just 2 cells we might have useful info
                        # Extract cell contents
                        cell_texts = [cell.text.strip() for cell in cells]
                        self.logger.info(f"Cell texts: {cell_texts}")
                        
                        # Try to identify which cells contain what information
                        client_name = ""
                        appointment_time = ""
                        duration = ""
                        
                        # Check for col-id attributes first
                        for i, cell in enumerate(cells):
                            col_id = cell.get_attribute("col-id")
                            if col_id == "requestID" and not job_id:
                                job_id = cell.text.strip()
                            elif col_id == "customerName":
                                client_name = cell.text.strip()
                            elif col_id == "interpretationTime" or col_id == "appointmentTime":
                                appointment_time = cell.text.strip()
                            elif col_id == "estimateDuration" or col_id == "duration":
                                duration = cell.text.strip()
                        
                        # If col-id didn't work, try making educated guesses based on content
                        if not all([client_name, appointment_time]):
                            for i, text in enumerate(cell_texts):
                                # Look for date/time format for appointment time
                                if not appointment_time and ("/" in text or ":" in text or "AM" in text or "PM" in text):
                                    appointment_time = text
                                # If a cell has only digits and is short, it might be duration
                                elif not duration and text.isdigit() and len(text) <= 4:
                                    duration = text
                                # If a cell looks like a client name (not a number, not a date)
                                elif not client_name and text and not text.isdigit() and "/" not in text and ":" not in text:
                                    client_name = text
                        
                        # Fallback to positional extraction if we still don't have values
                        if not client_name and len(cell_texts) > 1:
                            client_name = cell_texts[1]  # Often the second column is client name
                        if not appointment_time and len(cell_texts) > 2:
                            appointment_time = cell_texts[2]  # Often the third column is date/time
                        if not duration and len(cell_texts) > 3:
                            duration = cell_texts[3]  # Often the fourth column is duration
                        
                        # Create job details with whatever information we could extract
                        if client_name or appointment_time:  # As long as we have some meaningful info
                            job_details = {
                                'id': job_id,
                                'title': f"Interpretation for {client_name}" if client_name else "Interpretation Job",
                                'client': client_name or "Unknown Client",
                                'date': appointment_time or "Unknown Time",
                                'duration': duration or "Unknown Duration",
                                'description': "\n".join(f"{text}" for text in cell_texts if text),
                                'location': client_name or "Unknown Location"
                            }
                            
                            self.logger.info(f"Extracted closed job details: {job_details}")
                            closed_jobs.append(job_details)
                    else:
                        self.logger.warning(f"Not enough cells found in closed job: {len(cells)} cells")
                
                except Exception as e:
                    self.logger.error(f"Error processing closed job element: {str(e)}")
                    self.logger.error(traceback.format_exc())
                    continue
            
            self.logger.info(f"Found {len(closed_jobs)} closed jobs for debugging")
            return closed_jobs
            
        except Exception as e:
            self.logger.error(f"Error checking closed jobs: {str(e)}")
            self.logger.error(f"Detailed error: {traceback.format_exc()}")
            
            # Take a screenshot for debugging
            try:
                self.driver.save_screenshot("screenshots/closed_jobs_error_screenshot.png")
                self.logger.info("Saved error screenshot to screenshots/closed_jobs_error_screenshot.png")
            except Exception:
                pass
                
            return []



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