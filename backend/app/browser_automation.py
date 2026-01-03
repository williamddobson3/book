"""Browser automation for booking operations."""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())



from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Dict, Optional, List
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class BrowserAutomation:
    """Handles browser automation for booking."""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.playwright = None
        self.main_page: Optional[Page] = None  # Keep main page alive to maintain session
    
    async def start(self):
        """Start browser instance."""
        self.playwright = await async_playwright().start()
        # Use headful mode to pass browser checks and execute JS fully
        self.browser = await self.playwright.chromium.launch(
            headless=False,  # Headful mode for JS-heavy pages and browser checks
            args=[
                '--disable-blink-features=AutomationControlled',  # Hide automation
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
        # More realistic browser context with proper user-agent and settings
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='ja-JP',
            timezone_id='Asia/Tokyo',
            # Additional properties to make browser look more real
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=False,
            # Set default timeout higher for JS-heavy pages
            
        )
        # Add extra headers to look more like a real browser
        await self.context.set_extra_http_headers({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        })
        logger.info("Browser started in headful mode")
    
    async def stop(self):
        """Stop browser instance."""
        # Close main page if it exists
        if self.main_page:
            try:
                await self.main_page.close()
                self.main_page = None
            except:
                pass
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser stopped")
    
    async def login(self) -> Dict[str, str]:
        """Login to the system and return cookies.
        
        Returns:
            Dictionary of cookies
        """
        if not self.context:
            await self.start()
        
        page = await self.context.new_page()
        
        try:
            # First navigate to home page to initialize session and cookies
            # The login page requires this step to avoid error page
            # Direct navigation to login URL shows error, but clicking from home works
            # Server expects: home page → session created → click login → login page
            home_url = f"{settings.base_url}/index.jsp"
            logger.info(f"Navigating to home page first: {home_url}")
            await page.goto(home_url, wait_until='networkidle', timeout=120000)
            await page.wait_for_load_state('domcontentloaded', timeout=120000)
            await page.wait_for_load_state('networkidle', timeout=120000)
            await page.wait_for_timeout(2000)  # Let JS initialize
            
            # Verify home page loaded correctly (not error page)
            home_title = await page.title()
            home_content = await page.content()
            if 'エラー' in home_title or 'pawfa1000' in home_content:
                raise Exception(f"Home page returned error. Title: {home_title}")
            logger.info(f"Home page loaded successfully. Title: {home_title}")
            
            # Click the login button from home page (this avoids the error page)
            # The server expects: home page → session created → click login → login page
            logger.info("Clicking login button from home page...")
            try:
                # Try multiple selectors for the login button
                login_selectors = [
                    'button:has-text("ログイン")',
                    'a:has-text("ログイン")',
                    'input[value*="ログイン"]',
                    '[onclick*="ログイン"]',
                    '.btn:has-text("ログイン")',
                    'a[href*="UserLogin"]'
                ]
                
                login_button = None
                for selector in login_selectors:
                    try:
                        login_button = await page.wait_for_selector(selector, state='visible', timeout=10000)
                        if login_button:
                            logger.info(f"Found login button with selector: {selector}")
                            break
                    except:
                        continue
                
                if not login_button:
                    # Debug: capture page state to understand what's available
                    html = await page.content()
                    title = await page.title()
                    logger.error(f"Could not find login button. Page title: {title}")
                    with open('home_page_debug.html', 'w', encoding='utf-8') as f:
                        f.write(html)
                    raise Exception("Could not find login button on home page. Check home_page_debug.html for page content.")
                
                # Click and wait for URL to change to login page
                login_url_pattern = f"{settings.base_url}/rsvWTransUserLoginAction.do"
                async with page.expect_navigation(wait_until='networkidle', timeout=120000):
                    await login_button.click()
                
                # Wait for page to fully load
                await page.wait_for_load_state('networkidle', timeout=120000)
                await page.wait_for_timeout(2000)
                
                # Verify we're on the login page (not error page)
                current_url = page.url
                if login_url_pattern not in current_url:
                    logger.warning(f"URL after click is not login page: {current_url}")
                
                logger.info("Successfully navigated to login page via button click")
                
                # Immediately check if we got an error page instead of login form
                current_url = page.url
                title = await page.title()
                page_content = await page.content()
                if 'エラー' in title or 'error' in title.lower() or 'pawfa1000' in page_content or 'システム異常' in page_content:
                    logger.error("Received error page instead of login form after clicking login button")
                    html = await page.content()
                    with open('login_error_page.html', 'w', encoding='utf-8') as f:
                        f.write(html)
                    raise Exception(f"Server returned error page. This indicates missing session state or invalid navigation flow. Title: {title}, URL: {current_url}")
                
            except Exception as e:
                # Check if it's already our custom error
                if "Server returned error page" in str(e):
                    raise
                logger.error(f"Could not click login button: {e}")
                # Don't fallback to direct navigation - it will always show error page
                # The server requires the proper flow: home → click → login
                raise Exception(f"Failed to navigate to login page via button click. Server requires proper navigation flow. Error: {e}")
            
            # Wait for the login form elements to be visible (not just present)
            logger.info("Waiting for login form elements...")
            try:
                # Wait with longer timeout for JS-heavy pages
                await page.wait_for_selector('#userId', state='visible', timeout=120000)
                await page.wait_for_selector('#password', state='visible', timeout=120000)
                await page.wait_for_selector('#btn-go', state='visible', timeout=120000)
                logger.info("Login form elements found")
            except Exception as e:
                # Debug: capture page state
                html = await page.content()
                title = await page.title()
                url = page.url
                logger.error(f"Login form not found. Title: {title}, URL: {url}")
                logger.error(f"Error: {e}")
                # Save HTML for debugging
                with open('login_debug.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                raise Exception(f"Login form elements not found: {e}")
            
            # Fill login form with explicit timeouts
            logger.info("Filling login form...")
            await page.fill('#userId', settings.user_id, timeout=60000)
            await page.fill('#password', settings.password, timeout=60000)
            
            # Click login button and wait for state change
            logger.info("Clicking login button...")
            # Use expect_navigation context manager - waits for navigation automatically
            async with page.expect_navigation(wait_until='networkidle', timeout=120000):
                await page.click('#btn-go', timeout=60000)
            
            # Additional wait to ensure page is fully loaded
            await page.wait_for_load_state('networkidle', timeout=120000)
            
            # Check if login was successful by checking URL, title, and page state
            current_url = page.url
            title = await page.title()
            logger.info(f"Current URL after login: {current_url}")
            logger.info(f"Page title after login: {title}")
            
            # Success indicators:
            # 1. URL contains UserAttestation (post-login redirect)
            # 2. Title contains "ホーム画面" (Home Screen)
            # 3. Check for logout button or user info (more reliable)
            page_content = await page.content()
            has_logout = 'ログアウト' in page_content or 'logout' in page_content.lower()
            has_user_info = '様' in page_content or '有効期限' in page_content
            is_home_screen = 'ホーム画面' in title or 'ホーム' in title
            
            # Check for successful login patterns
            url_success_patterns = [
                'UserAttestation',  # Post-login redirect URL
                'index.jsp',       # Alternative home page
                'pawab2000'        # Legacy pattern
            ]
            
            url_matches = any(pattern in current_url for pattern in url_success_patterns)
            
            # Login is successful if:
            # - URL matches success pattern AND (title is home screen OR logout button exists)
            # OR
            # - Logout button exists (strongest indicator of success)
            if (url_matches and (is_home_screen or has_logout)) or has_logout:
                # Get cookies
                cookies = await self.context.cookies()
                cookie_dict = {c['name']: c['value'] for c in cookies}
                logger.info("Login successful - detected home screen with user session")
                
                # CRITICAL: Do NOT navigate anywhere after login
                # The page is already on the correct logged-in page (either index.jsp or UserAttestation page)
                # Navigating away will destroy the session
                # Just keep the page as-is and use it directly
                self.main_page = page
                logger.info(f"Keeping page alive at current URL: {current_url} - DO NOT navigate to avoid session destruction")
                
                return cookie_dict
            else:
                # Debug: capture page state on failure
                html = await page.content()
                with open('login_failed_debug.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                raise Exception(f"Login failed - URL: {current_url}, Title: {title}, Has logout: {has_logout}, Has user info: {has_user_info}")
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            # Take screenshot for debugging
            try:
                await page.screenshot(path='login_error.png')
            except:
                pass
            # Only close page if login failed
            if self.main_page != page:
                await page.close()
            raise
    
    async def get_available_courts_for_park(self, page: Page, area_code: str) -> List[Dict]:
        """Get list of available tennis courts (facilities) for a park from the dropdown.
        
        Args:
            page: Playwright page object
            area_code: Area code for the park (e.g., "1200_1040")
            
        Returns:
            List of court dictionaries with 'icd' and 'name' keys
        """
        courts = []
        try:
            # Wait for facility dropdown to be available
            # The dropdown might be #iname (in search form) or #facility-select (in results view)
            facility_dropdown = None
            
            # Try #facility-select first (results page)
            facility_dropdown = await page.query_selector('#facility-select')
            if not facility_dropdown:
                # Try #iname (search form)
                facility_dropdown = await page.query_selector('#iname')
            
            if facility_dropdown:
                # Get all option elements
                options = await facility_dropdown.query_selector_all('option')
                for option in options:
                    value = await option.get_attribute('value')
                    text = await option.inner_text()
                    
                    # Skip "指定なし" (Not specified) option (value="0")
                    if value and value != '0' and '庭球場' in text:
                        courts.append({
                            'icd': value,
                            'name': text.strip()
                        })
                        logger.info(f"Found court: {text.strip()} (ICD: {value})")
            else:
                logger.warning("Facility dropdown not found - cannot get court list")
        except Exception as e:
            logger.error(f"Error getting available courts: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return courts
    
    async def search_availability_via_form(
        self,
        area_code: str,
        park_name: str = None,
        icd: str = None
    ) -> Dict:
        """Search for availability by filling out the search form in the browser.
        
        This method properly fills out the form as required by the server:
        1. Selects "1 month" (1か月) date option
        2. Selects park name from dropdown
        3. Selects "テニス" (Tennis) activity
        4. Triggers search
        
        Args:
            area_code: Area code (e.g., "1200_1040")
            park_name: Optional park name for logging
            
        Returns:
            Search results or empty dict if no results
        """
        if not self.context:
            await self.start()
        
        # Use main page if available (maintains session), otherwise create new page
        if self.main_page and not self.main_page.is_closed():
            page = self.main_page
            logger.info("Reusing main page to maintain session")
        else:
            page = await self.context.new_page()
            self.main_page = page
            logger.info("Created new page for search")
        
        try:
            # CRITICAL: Do NOT navigate if we're already on a valid logged-in page
            # Navigating will destroy the session
            current_url = page.url
            logger.info(f"Current page URL: {current_url}")
            
            # Check if we're already on a page with the search form (home page or results page)
            # The search form is available on index.jsp, UserAttestation pages, or results page
            is_valid_page = (
                'index.jsp' in current_url or 
                'UserAttestation' in current_url or
                'rsvWOpeUnreservedDailyAction.do' in current_url or
                'rsvWOpeInstSrchVacantAction.do' in current_url or  # Facility-based search results page
                'ホーム画面' in await page.title()
            )
            
            if is_valid_page:
                logger.info("Already on valid logged-in page - checking if search form needs to be expanded...")
                # Wait for page to be ready
                await page.wait_for_load_state('networkidle', timeout=30000)
                await page.wait_for_timeout(1000)
                
                # If we're on the results page, the search form might be collapsed
                # Check if form is collapsed and needs to be expanded
                # This applies to both rsvWOpeUnreservedDailyAction.do and rsvWOpeInstSrchVacantAction.do
                if 'rsvWOpeUnreservedDailyAction.do' in current_url or 'rsvWOpeInstSrchVacantAction.do' in current_url:
                    try:
                        # Check if #free-search-cond is collapsed
                        form_element = await page.query_selector('#free-search-cond')
                        if form_element:
                            # Check if it has 'collapse' class and is not showing
                            classes = await form_element.get_attribute('class') or ''
                            is_visible = await form_element.evaluate('el => window.getComputedStyle(el).display !== "none"')
                            
                            logger.info(f"Form element state: classes='{classes}', is_visible={is_visible}")
                            
                            # Check if form needs to be expanded
                            # Form is collapsed if it has 'collapse' class and doesn't have 'show' class, or if it's not visible
                            needs_expansion = (
                                ('collapse' in classes and 'show' not in classes) or 
                                not is_visible
                            )
                            
                            if needs_expansion:
                                logger.info("Search form is collapsed - clicking [条件変更] to expand it...")
                                # Click [条件変更] button to expand the form
                                change_condition_selectors = [
                                    '#change-condition',
                                    'button#change-condition',
                                    'button:has-text("条件変更")',
                                    'a:has-text("条件変更")'
                                ]
                                
                                button_clicked = False
                                for selector in change_condition_selectors:
                                    try:
                                        logger.info(f"Trying to find [条件変更] button with selector: {selector}")
                                        button = await page.query_selector(selector)
                                        if button:
                                            # Check if button is visible
                                            button_visible = await button.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                            logger.info(f"Button found with selector {selector}, visible={button_visible}")
                                            if button_visible:
                                                await button.click()
                                                # Wait for Bootstrap collapse animation
                                                await page.wait_for_timeout(1500)
                                                # Wait for form to be visible
                                                await page.wait_for_selector('#free-search-cond.show, #bname', state='visible', timeout=5000)
                                                button_clicked = True
                                                logger.info(f"Expanded search form using selector: {selector}")
                                                break
                                    except Exception as e:
                                        logger.warning(f"Failed to click [条件変更] with selector {selector}: {e}")
                                        continue
                                
                                if not button_clicked:
                                    logger.warning("Could not click [条件変更] button, form might already be expanded or button not found")
                            else:
                                logger.info("Search form is already expanded - no need to click [条件変更]")
                        else:
                            logger.warning("#free-search-cond element not found - form might not exist on this page")
                    except Exception as e:
                        logger.warning(f"Could not check/expand search form: {e}, continuing anyway")
                        import traceback
                        logger.warning(traceback.format_exc())
            else:
                # Only navigate if we're on a completely different page (shouldn't happen after login)
                logger.warning(f"Not on expected page ({current_url}), but navigating might destroy session. Attempting careful navigation...")
                home_url = f"{settings.base_url}/index.jsp"
                # Use reload instead of goto to preserve session
                try:
                    await page.reload(wait_until='networkidle', timeout=120000)
                except:
                    # If reload fails, try goto as last resort
                    await page.goto(home_url, wait_until='networkidle', timeout=120000)
                await page.wait_for_load_state('networkidle', timeout=120000)
                await page.wait_for_timeout(2000)
            
            # Step 1: Select "1 month" (1か月) - click the label, not the input
            # The actual button is: <label class="btn radiobtn" for="thismonth">1か月</label>
            logger.info("Selecting '1 month' date option...")
            try:
                # Wait for the label to be visible
                await page.wait_for_selector('label.btn.radiobtn[for="thismonth"]', state='visible', timeout=30000)
                await page.click('label.btn.radiobtn[for="thismonth"]')
                await page.wait_for_timeout(1000)  # Wait for form state to update
                logger.info("Selected '1 month' date option via label")
            except Exception as e:
                logger.warning(f"Could not select '1 month' label: {e}, trying alternative selectors...")
                # Try alternative selectors
                alternatives = [
                    'label[for="thismonth"]',  # Just the for attribute
                    'label:has-text("1か月")',  # Text-based
                    'input#thismonth',  # Fallback to input
                    'input[name="date"][value="4"]'  # Radio button value
                ]
                selected = False
                for selector in alternatives:
                    try:
                        await page.wait_for_selector(selector, state='visible', timeout=5000)
                        await page.click(selector)
                        await page.wait_for_timeout(1000)
                        logger.info(f"Selected '1 month' using alternative selector: {selector}")
                        selected = True
                        break
                    except:
                        continue
                if not selected:
                    logger.error("Failed to select date option with all selectors")
                    raise
            
            # Step 2: Select park name (どこで) - this is the dropdown
            logger.info(f"Selecting park: {park_name or area_code}...")
            try:
                # The dropdown might be #bname or a different selector
                # Wait for dropdown to be visible
                await page.wait_for_selector('select[name*="bcd"], select#bname, select[name*="area"]', state='visible', timeout=30000)
                
                # Try multiple selectors
                selectors = [
                    'select[name*="bcd"]',
                    'select#bname',
                    'select[name*="area"]',
                    'select[name*="どこ"]'
                ]
                
                dropdown_found = False
                for selector in selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            await page.select_option(selector, value=area_code)
                            await page.wait_for_timeout(1000)
                            dropdown_found = True
                            logger.info(f"Selected park using selector: {selector}")
                            break
                    except:
                        continue
                
                if not dropdown_found:
                    raise Exception("Could not find park dropdown")
                
                # If icd is provided, select specific court (facility)
                if icd:
                    logger.info(f"Selecting specific court (ICD: {icd})...")
                    try:
                        # Wait for facility dropdown to be available (might need to wait for park selection to load options)
                        await page.wait_for_timeout(1000)  # Wait for options to load
                        
                        # Try #iname (search form) first
                        facility_selectors = ['select#iname', 'select[name*="icd"]', 'select[name*="施設"]']
                        facility_selected = False
                        for selector in facility_selectors:
                            try:
                                element = await page.query_selector(selector)
                                if element:
                                    await page.select_option(selector, value=icd)
                                    await page.wait_for_timeout(1000)
                                    facility_selected = True
                                    logger.info(f"Selected court {icd} using selector: {selector}")
                                    break
                            except:
                                continue
                        
                        if not facility_selected:
                            logger.warning(f"Could not select court {icd} in search form - will try in results page")
                    except Exception as e:
                        logger.warning(f"Failed to select court in search form: {e}, will try in results page")
                    
            except Exception as e:
                logger.error(f"Failed to select park: {e}")
                raise
            
            # Step 3: Select "テニス" (Tennis) activity (何をする)
            logger.info("Selecting 'テニス' (Tennis) activity...")
            try:
                # Wait for activity dropdown
                await page.wait_for_selector('select[name*="purpose"], select#purpose, select[name*="何"]', state='visible', timeout=30000)
                
                # Try multiple selectors
                selectors = [
                    'select[name*="purpose"]',
                    'select#purpose',
                    'select[name*="何"]'
                ]
                
                dropdown_found = False
                for selector in selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            await page.select_option(selector, value='31000000_31011700')
                            await page.wait_for_timeout(1000)
                            dropdown_found = True
                            logger.info(f"Selected Tennis using selector: {selector}")
                            break
                    except:
                        continue
                
                if not dropdown_found:
                    raise Exception("Could not find activity dropdown")
                    
            except Exception as e:
                logger.error(f"Failed to select activity: {e}")
                raise
            
            # Step 4: Click search button
            logger.info("Clicking search button...")
            try:
                # Wait for search button
                search_selectors = [
                    'button:has-text("検索")',
                    'input[type="submit"][value*="検索"]',
                    'button[type="submit"]',
                    '#btn-search'
                ]
                
                button_found = False
                for selector in search_selectors:
                    try:
                        await page.wait_for_selector(selector, state='visible', timeout=10000)
                        await page.click(selector)
                        await page.wait_for_load_state('networkidle', timeout=120000)
                        button_found = True
                        logger.info(f"Clicked search button using selector: {selector}")
                        break
                    except:
                        continue
                
                if not button_found:
                    raise Exception("Could not find search button")
                
                # Wait for results to load
                await page.wait_for_load_state('networkidle', timeout=120000)
                await page.wait_for_timeout(2000)
                
                # After search, maintain "施設ごと" (By Facility) view - do NOT click "日付順"
                # The default view after search should be "施設ごと"
                logger.info("Ensuring '施設ごと' (By Facility) tab is active...")
                try:
                    # Wait for tabs to be visible
                    await page.wait_for_selector('#free-info-nav, .nav-tabs', state='visible', timeout=10000)
                    
                    # Check which tab is currently active
                    active_tab = await page.query_selector('#free-info-nav .nav-link.active, .nav-tabs .nav-link.active')
                    if active_tab:
                        tab_text = await active_tab.inner_text()
                        logger.info(f"Current active tab: {tab_text}")
                        
                        # If "日付順" is active, switch to "施設ごと"
                        if "日付順" in tab_text:
                            logger.info("日付順 tab is active - switching to 施設ごと...")
                            facility_tab_selectors = [
                                'a:has-text("施設ごと")',
                                'a:has-text("施設別")',
                                '#free-info-nav a:first-child',
                                '.nav-tabs a:first-child'
                            ]
                            for selector in facility_tab_selectors:
                                try:
                                    await page.click(selector)
                                    await page.wait_for_load_state('networkidle', timeout=30000)
                                    await page.wait_for_timeout(1000)
                                    logger.info(f"Switched to 施設ごと tab using selector: {selector}")
                                    break
                                except:
                                    continue
                        else:
                            logger.info("施設ごと tab is already active - maintaining this view")
                    else:
                        logger.warning("Could not find active tab, assuming 施設ごと is default")
                except Exception as e:
                    logger.warning(f"Could not verify/switch tab: {e}, assuming 施設ごと is default")
                
                # First check if there are results - only then check for "さらに表示" button
                logger.info("Checking if results are available...")
                
                has_results = False
                has_reservation_buttons = False
                
                try:
                    # CRITICAL: Check actual div visibility first (not just text content)
                    # The divs can have text content but be hidden with style="display: none;"
                    no_results_div = await page.query_selector('#unreserved-notfound')
                    results_list_div = await page.query_selector('#unreserved-list')
                    
                    # Check #unreserved-notfound visibility first (highest priority)
                    if no_results_div:
                        no_results_visible = await no_results_div.evaluate('el => window.getComputedStyle(el).display !== "none"')
                        if no_results_visible:
                            logger.info("No results found - #unreserved-notfound is visible (display: block)")
                            has_results = False
                            # Don't check anything else - this is definitive
                        else:
                            # #unreserved-notfound exists but is hidden, check #unreserved-list
                            if results_list_div:
                                results_list_visible = await results_list_div.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                if results_list_visible:
                                    logger.info("Results found - #unreserved-list is visible (display: block)")
                                    has_results = True
                                else:
                                    logger.info("Both divs exist but both are hidden - checking buttons as fallback")
                                    # Both divs exist but both hidden - check buttons
                                    reservation_buttons_check = await page.query_selector_all('button:has-text("予約"), td.reservation button.btn-go')
                                    has_reservation_buttons = len(reservation_buttons_check) > 0
                                    if has_reservation_buttons:
                                        logger.info(f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results")
                                        has_results = True
                                    else:
                                        logger.info("No reservation buttons found - treating as no results")
                                        has_results = False
                            else:
                                # #unreserved-notfound exists but hidden, and #unreserved-list doesn't exist
                                logger.info("#unreserved-notfound exists but hidden, #unreserved-list not found - checking buttons")
                                reservation_buttons_check = await page.query_selector_all('button:has-text("予約"), td.reservation button.btn-go')
                                has_reservation_buttons = len(reservation_buttons_check) > 0
                                if has_reservation_buttons:
                                    logger.info(f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results")
                                    has_results = True
                                else:
                                    has_results = False
                    else:
                        # #unreserved-notfound doesn't exist, check #unreserved-list
                        if results_list_div:
                            results_list_visible = await results_list_div.evaluate('el => window.getComputedStyle(el).display !== "none"')
                            if results_list_visible:
                                logger.info("Results found - #unreserved-list is visible (display: block)")
                                has_results = True
                            else:
                                logger.info("#unreserved-list exists but is hidden - checking buttons")
                                reservation_buttons_check = await page.query_selector_all('button:has-text("予約"), td.reservation button.btn-go')
                                has_reservation_buttons = len(reservation_buttons_check) > 0
                                if has_reservation_buttons:
                                    logger.info(f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results")
                                    has_results = True
                                else:
                                    has_results = False
                        else:
                            # Neither div exists - check buttons as fallback
                            logger.info("Neither div found - checking buttons as fallback")
                            reservation_buttons_check = await page.query_selector_all('button:has-text("予約"), td.reservation button.btn-go')
                            has_reservation_buttons = len(reservation_buttons_check) > 0
                            if has_reservation_buttons:
                                logger.info(f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results")
                                has_results = True
                            else:
                                has_results = False
                    
                    # If we still don't have reservation buttons but have results, check for them
                    if has_results and not has_reservation_buttons:
                        reservation_buttons_check = await page.query_selector_all('button:has-text("予約"), td.reservation button.btn-go')
                        has_reservation_buttons = len(reservation_buttons_check) > 0
                        if has_reservation_buttons:
                            logger.info(f"Found {len(reservation_buttons_check)} [予約] buttons")
                        
                except Exception as e:
                    logger.warning(f"Error checking for results: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
                    has_results = False
                
                # Log the final detection result
                if has_results:
                    logger.info(f"Results detected - bookable dates found, do NOT click '条件変更'")
                else:
                    logger.info(f"No results detected - should click '条件変更' to try another park")
                
                # Only check for "さらに表示" if there are results
                if has_results:
                    logger.info("Results found - checking for 'さらに表示' (Show More) button to load all available dates...")
                    max_load_more_clicks = 5  # Limit to prevent infinite loops
                    load_more_clicks = 0
                    
                    while load_more_clicks < max_load_more_clicks:
                        try:
                            show_more_selectors = [
                                '#unreserved-moreBtn',
                                'button#unreserved-moreBtn',
                                'button:has-text("さらに表示")',
                                'button[onclick*="loadNext"]'
                            ]
                            
                            show_more_found = False
                            for selector in show_more_selectors:
                                try:
                                    show_more_button = await page.query_selector(selector)
                                    if show_more_button:
                                        # Check if button is visible
                                        is_visible = await show_more_button.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                        if is_visible:
                                            logger.info(f"Found 'さらに表示' button (click {load_more_clicks + 1}) - clicking to load more dates...")
                                            await page.click(selector)
                                            # Wait for additional results to load
                                            await page.wait_for_load_state('networkidle', timeout=60000)
                                            await page.wait_for_timeout(2000)
                                            load_more_clicks += 1
                                            show_more_found = True
                                            break
                                except:
                                    continue
                            
                            if not show_more_found:
                                logger.info("No more 'さらに表示' button found - all dates loaded")
                                break
                        except Exception as e:
                            logger.warning(f"Error clicking 'さらに表示' button: {e}")
                            break
                    
                    if load_more_clicks > 0:
                        logger.info(f"Loaded additional dates by clicking 'さらに表示' {load_more_clicks} time(s)")
                else:
                    logger.info("No results available - skipping 'さらに表示' button check")
                
                # If icd was specified, select the court in the results page before extracting slots
                if icd:
                    logger.info(f"Selecting court (ICD: {icd}) in results page...")
                    try:
                        # Wait for facility dropdown in results page
                        await page.wait_for_selector('#facility-select', state='visible', timeout=10000)
                        await page.select_option('#facility-select', value=icd)
                        await page.wait_for_timeout(2000)  # Wait for calendar to update
                        
                        # Wait for AJAX to reload calendar
                        try:
                            loading_indicator = await page.query_selector('#loadingweek')
                            if loading_indicator:
                                await page.wait_for_function(
                                    'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                                    timeout=30000
                                )
                        except:
                            pass
                        
                        await page.wait_for_load_state('networkidle', timeout=30000)
                        await page.wait_for_timeout(2000)
                        logger.info(f"Court {icd} selected in results page, calendar should be updated")
                    except Exception as e:
                        logger.warning(f"Could not select court {icd} in results page: {e}, continuing with default court")
                
                # Extract available slots from weekly calendar view (施設ごと)
                slots = []
                slots_clicked_flag = 0  # Flag: 1 if slots were clicked, 0 if no slots found
                if has_results:
                    # Navigate through weekly calendar and extract slots
                    slots, slots_clicked_flag = await self._extract_slots_from_weekly_calendar(page)
                    logger.info(f"Extracted {len(slots)} available slots from weekly calendar")
                    logger.info(f"Slots clicked flag: {slots_clicked_flag} (1=slots clicked, 0=no slots clicked), type: {type(slots_clicked_flag)}")
                    
                    # If flag is 1 (slots were clicked), click the "予約" button to proceed to reservation page
                    # Convert to int if needed (in case it's a string or boolean)
                    flag_value = int(slots_clicked_flag) if slots_clicked_flag else 0
                    logger.info(f"Flag value after conversion: {flag_value}, comparison with 1: {flag_value == 1}")
                    logger.info(f"About to check if flag_value == 1: {flag_value == 1}")
                    
                    if flag_value == 1:
                        logger.info(f"✓ ENTERED if block: flag_value is 1, will click '予約' button")
                        logger.info(f"Slots clicked flag is 1 - clicking '予約' button to proceed to reservation page (found {len(slots)} slot(s))...")
                        try:
                            # Wait for the button to be visible
                            await page.wait_for_selector('#btn-go', state='visible', timeout=10000)
                            
                            # Find and click the correct "予約" button
                            # The button should have id="btn-go" and onclick containing "gRsvWOpeReservedApplyAction"
                            reserve_button = None
                            btn_go_selectors = [
                                '#btn-go',  # Primary selector
                                'button#btn-go',
                                'button.btn-go:has-text("予約")'
                            ]
                            
                            for selector in btn_go_selectors:
                                try:
                                    button = await page.query_selector(selector)
                                    if button:
                                        # Verify this is the correct button by checking onclick
                                        onclick = await button.get_attribute('onclick') or ''
                                        button_text = await button.inner_text()
                                        
                                        # Check if it's the reservation button (not the Terms of Use confirm button)
                                        if 'gRsvWOpeReservedApplyAction' in onclick or ('予約' in button_text and 'gRsvWInstUseruleRsvApplyAction' not in onclick):
                                            reserve_button = button
                                            logger.info(f"Found correct '予約' button with onclick: {onclick[:100] if onclick else 'none'}")
                                            break
                                except:
                                    continue
                            
                            # If we didn't find the specific button, try the generic #btn-go
                            if not reserve_button:
                                reserve_button = await page.query_selector('#btn-go')
                                if reserve_button:
                                    onclick = await reserve_button.get_attribute('onclick') or ''
                                    logger.info(f"Using #btn-go button with onclick: {onclick[:100] if onclick else 'none'}")
                            
                            if reserve_button:
                                # Check if button is enabled
                                is_disabled = await reserve_button.get_attribute('disabled')
                                if not is_disabled:
                                    await reserve_button.scroll_into_view_if_needed()
                                    await page.wait_for_timeout(500)
                                    await reserve_button.click()
                                    logger.info("Successfully clicked '予約' button - navigating to reservation page")
                                    
                                    # Wait for navigation to reservation/Terms of Use page
                                    await page.wait_for_load_state('networkidle', timeout=30000)
                                    await page.wait_for_timeout(2000)
                                    logger.info("Navigation to reservation page completed")
                                    
                                    # Check if we're on the Terms of Use page (rsvWOpeReservedApplyAction.do)
                                    current_url = page.url
                                    page_title = await page.title()
                                    if 'rsvWOpeReservedApplyAction' in current_url or '利用規約' in page_title:
                                        logger.info("Detected Terms of Use page - handling agreement...")
                                        
                                        # Click "利用規約に同意する" (Agree to Terms of Use) label
                                        logger.info("Clicking '利用規約に同意する' label...")
                                        agreement_clicked = False
                                        agreement_selectors = [
                                            'label[for="ruleFg_1"]',  # Specific selector from HTML
                                            'label.btn.radiobtn[for="ruleFg_1"]',
                                            'label:has-text("利用規約に同意する")',
                                            'input[type="radio"][value="1"][name*="rule"]',
                                            'input[type="radio"][id="ruleFg_1"]'
                                        ]
                                        
                                        for selector in agreement_selectors:
                                            try:
                                                element = await page.query_selector(selector)
                                                if element:
                                                    tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                                                    if tag_name == 'label':
                                                        await element.scroll_into_view_if_needed()
                                                        await page.wait_for_timeout(300)
                                                        await element.click()
                                                        logger.info(f"Clicked agreement label using selector: {selector}")
                                                    else:
                                                        # It's an input, check it
                                                        await element.scroll_into_view_if_needed()
                                                        await page.wait_for_timeout(300)
                                                        await element.check()
                                                        logger.info(f"Checked agreement input using selector: {selector}")
                                                    await page.wait_for_timeout(500)
                                                    agreement_clicked = True
                                                    break
                                            except Exception as e:
                                                logger.debug(f"Failed to click agreement with selector {selector}: {e}")
                                                continue
                                        
                                        if not agreement_clicked:
                                            logger.warning("Could not find/click agreement option, trying to proceed anyway")
                                        
                                        # Click "確認" (Confirm) button
                                        logger.info("Clicking '確認' button...")
                                        confirm_clicked = False
                                        confirm_selectors = [
                                            '#btn-go',  # Primary selector from HTML
                                            'button#btn-go',
                                            'button:has-text("確認")',
                                            'button[type="submit"]:has-text("確認")',
                                            'button[onclick*="gRsvWInstUseruleRsvApplyAction"]'
                                        ]
                                        
                                        for selector in confirm_selectors:
                                            try:
                                                confirm_button = await page.query_selector(selector)
                                                if confirm_button:
                                                    is_disabled = await confirm_button.get_attribute('disabled')
                                                    if not is_disabled:
                                                        await confirm_button.scroll_into_view_if_needed()
                                                        await page.wait_for_timeout(500)
                                                        await confirm_button.click()
                                                        logger.info(f"Clicked '確認' button using selector: {selector}")
                                                        
                                                        # Wait for navigation after clicking confirm
                                                        await page.wait_for_load_state('networkidle', timeout=30000)
                                                        await page.wait_for_timeout(2000)
                                                        confirm_clicked = True
                                                        logger.info("Successfully handled Terms of Use page")
                                                        break
                                            except Exception as e:
                                                logger.debug(f"Failed to click confirm with selector {selector}: {e}")
                                                continue
                                        
                                        if not confirm_clicked:
                                            logger.warning("Could not find/click '確認' button on Terms of Use page")
                                        
                                        # After clicking "確認" on Terms of Use page, we should be on reservation confirmation page
                                        # Check if we're on the reservation confirmation page (rsvWInstUseruleRsvApplyAction.do or rsvWInstRsvApplyAction.do)
                                        await page.wait_for_load_state('networkidle', timeout=30000)
                                        await page.wait_for_timeout(2000)
                                        current_url_after_confirm = page.url
                                        page_title_after_confirm = await page.title()
                                        
                                        if 'rsvWInstUseruleRsvApplyAction' in current_url_after_confirm or 'rsvWInstRsvApplyAction' in current_url_after_confirm or '予約内容確認' in page_title_after_confirm:
                                            logger.info("Detected reservation confirmation page - filling in number of users for each reservation slot...")
                                            
                                            # Fill in "利用人数" (Number of Users) for each reservation slot
                                            # Default number of users: 4 (as shown in the reservation completion page)
                                            default_user_count = 4
                                            
                                            try:
                                                # Strategy 1: Find inputs by looking for "利用人数" labels and their associated inputs
                                                user_count_inputs = []
                                                
                                                try:
                                                    labels_with_text = await page.query_selector_all('label:has-text("利用人数"), td:has-text("利用人数"), div:has-text("利用人数")')
                                                    
                                                    for label_element in labels_with_text:
                                                        try:
                                                            label_for = await label_element.get_attribute('for')
                                                            if label_for:
                                                                associated_input = await page.query_selector(f'input#{label_for}, input[name="{label_for}"]')
                                                                if associated_input:
                                                                    user_count_inputs.append(associated_input)
                                                                    continue
                                                            
                                                            parent = await label_element.evaluate_handle('el => el.closest("div, form, tr, td, table")')
                                                            if parent:
                                                                inputs_in_container = await parent.as_element().query_selector_all('input[type="text"], input[type="number"]')
                                                                for inp in inputs_in_container:
                                                                    placeholder = await inp.get_attribute('placeholder') or ''
                                                                    name_attr = await inp.get_attribute('name') or ''
                                                                    if '半角' in placeholder or 'num' in name_attr.lower() or '人数' in name_attr:
                                                                        if inp not in user_count_inputs:
                                                                            user_count_inputs.append(inp)
                                                        except Exception as e:
                                                            logger.debug(f"Error processing label element: {e}")
                                                            continue
                                                except Exception as e:
                                                    logger.debug(f"Error finding labels with '利用人数' text: {e}")
                                                
                                                # Strategy 2: Find inputs by name attributes (fallback)
                                                if not user_count_inputs:
                                                    user_count_selectors = [
                                                        'input[name*="applyNum"]',
                                                        'input[name*="人数"]',
                                                        'input[name*="userCount"]',
                                                        'input[placeholder*="半角文字で入力"]'
                                                    ]
                                                    
                                                    for selector in user_count_selectors:
                                                        try:
                                                            inputs = await page.query_selector_all(selector)
                                                            if inputs:
                                                                for inp in inputs:
                                                                    if inp not in user_count_inputs:
                                                                        user_count_inputs.append(inp)
                                                                if user_count_inputs:
                                                                    break
                                                        except Exception as e:
                                                            logger.debug(f"Error finding inputs with selector {selector}: {e}")
                                                            continue
                                                
                                                # Strategy 3: Find all inputs in reservation slot containers (No.1, No.2, etc.)
                                                if not user_count_inputs:
                                                    try:
                                                        slot_containers = await page.query_selector_all('div:has-text("No."), form:has-text("利用人数")')
                                                        for container in slot_containers:
                                                            try:
                                                                inputs_in_slot = await container.query_selector_all('input[type="text"], input[type="number"]')
                                                                for inp in inputs_in_slot:
                                                                    placeholder = await inp.get_attribute('placeholder') or ''
                                                                    name_attr = await inp.get_attribute('name') or ''
                                                                    if '半角' in placeholder or 'num' in name_attr.lower() or '人数' in name_attr:
                                                                        if inp not in user_count_inputs:
                                                                            user_count_inputs.append(inp)
                                                            except:
                                                                continue
                                                    except Exception as e:
                                                        logger.debug(f"Error finding inputs in slot containers: {e}")
                                                
                                                if user_count_inputs:
                                                    logger.info(f"Found {len(user_count_inputs)} '利用人数' input field(s) - filling with {default_user_count} users each...")
                                                    for idx, user_input in enumerate(user_count_inputs, 1):
                                                        try:
                                                            await user_input.clear()
                                                            await user_input.fill(str(default_user_count))
                                                            await page.wait_for_timeout(200)
                                                            logger.info(f"Filled '利用人数' field {idx} with {default_user_count} users")
                                                        except Exception as e:
                                                            logger.warning(f"Failed to fill user count input {idx}: {e}")
                                                            continue
                                                else:
                                                    logger.warning("Could not find '利用人数' input fields - proceeding without filling user count")
                                                
                                                await page.wait_for_timeout(500)
                                                
                                            except Exception as e:
                                                logger.warning(f"Error filling in user count fields: {e}")
                                                import traceback
                                                logger.warning(traceback.format_exc())
                                            
                                            logger.info("Filled user count fields - clicking final '予約' button...")
                                            
                                            # Click the final "予約" button on reservation confirmation page
                                            # This button has onclick="javascript:checkTextValue(document.form1, gRsvWInstRsvApplyAction, '1');"
                                            final_reserve_clicked = False
                                            final_reserve_selectors = [
                                                '#btn-go',  # Primary selector
                                                'button#btn-go',
                                                'button:has-text("予約")',
                                                'button[onclick*="gRsvWInstRsvApplyAction"]',
                                                'button[onclick*="checkTextValue"]'
                                            ]
                                            
                                            for selector in final_reserve_selectors:
                                                try:
                                                    final_button = await page.query_selector(selector)
                                                    if final_button:
                                                        # Verify this is the correct button by checking onclick
                                                        button_onclick = await final_button.get_attribute('onclick') or ''
                                                        button_text = await final_button.inner_text()
                                                        
                                                        # Check if it's the reservation confirmation button
                                                        if 'gRsvWInstRsvApplyAction' in button_onclick or ('予約' in button_text and 'checkTextValue' in button_onclick):
                                                            is_disabled = await final_button.get_attribute('disabled')
                                                            if not is_disabled:
                                                                await final_button.scroll_into_view_if_needed()
                                                                await page.wait_for_timeout(500)
                                                                
                                                                # Set up dialog handler to accept the confirmation dialog
                                                                # The dialog message is: "予約申込処理を行います。よろしいですか?"
                                                                dialog_handled = False
                                                                
                                                                async def handle_dialog(dialog):
                                                                    nonlocal dialog_handled
                                                                    dialog_message = dialog.message
                                                                    logger.info(f"JavaScript dialog detected: {dialog_message}")
                                                                    if "予約申込処理を行います" in dialog_message or "よろしいですか" in dialog_message:
                                                                        logger.info("Accepting reservation confirmation dialog...")
                                                                        await dialog.accept()
                                                                        dialog_handled = True
                                                                    else:
                                                                        logger.warning(f"Unexpected dialog message: {dialog_message}, accepting anyway")
                                                                        await dialog.accept()
                                                                        dialog_handled = True
                                                                
                                                                # Register dialog handler
                                                                page.on('dialog', handle_dialog)
                                                                
                                                                try:
                                                                    # Click the button - this will trigger the dialog
                                                                    await final_button.click()
                                                                    logger.info(f"Clicked final '予約' button on reservation confirmation page using selector: {selector}")
                                                                    
                                                                    # Wait a bit for the dialog to appear and be handled
                                                                    await page.wait_for_timeout(1000)
                                                                    
                                                                    if dialog_handled:
                                                                        logger.info("Dialog was handled successfully")
                                                                    else:
                                                                        logger.warning("Dialog handler was set but dialog may not have appeared")
                                                                    
                                                                    # Wait for navigation to complete booking
                                                                    await page.wait_for_load_state('networkidle', timeout=30000)
                                                                    await page.wait_for_timeout(2000)
                                                                    final_reserve_clicked = True
                                                                    logger.info("Successfully clicked final '予約' button and handled dialog - booking should be completed")
                                                                    break
                                                                except Exception as click_error:
                                                                    logger.warning(f"Error clicking button or handling dialog: {click_error}")
                                                                    # Try alternative: wait for dialog event explicitly
                                                                    try:
                                                                        async with page.expect_dialog() as dialog_info:
                                                                            await final_button.click()
                                                                        dialog = await dialog_info.value
                                                                        logger.info(f"Dialog appeared: {dialog.message}")
                                                                        await dialog.accept()
                                                                        logger.info("Accepted dialog using expect_dialog")
                                                                        await page.wait_for_load_state('networkidle', timeout=30000)
                                                                        await page.wait_for_timeout(2000)
                                                                        final_reserve_clicked = True
                                                                        logger.info("Successfully clicked final '予約' button and handled dialog (alternative method) - booking should be completed")
                                                                        break
                                                                    except Exception as alt_error:
                                                                        logger.warning(f"Alternative dialog handling also failed: {alt_error}")
                                                                        continue
                                                                finally:
                                                                    # Remove dialog handler to avoid conflicts
                                                                    try:
                                                                        page.remove_listener('dialog', handle_dialog)
                                                                    except:
                                                                        pass
                                                except Exception as e:
                                                    logger.debug(f"Failed to click final reserve button with selector {selector}: {e}")
                                                    continue
                                            
                                            if not final_reserve_clicked:
                                                logger.warning("Could not find/click final '予約' button on reservation confirmation page")
                                            
                                            # After clicking final '予約' button, check if we're on reservation completion page
                                            # and click "未入金予約の確認・支払へ" button if present
                                            await page.wait_for_load_state('networkidle', timeout=30000)
                                            await page.wait_for_timeout(2000)
                                            current_url_after_booking = page.url
                                            page_title_after_booking = await page.title()
                                            
                                            if 'rsvWInstRsvApplyAction' in current_url_after_booking or '予約完了' in page_title_after_booking:
                                                logger.info("Detected reservation completion page - clicking '未入金予約の確認・支払へ' button...")
                                                
                                                payment_button_clicked = False
                                                payment_button_selectors = [
                                                    '#btn-go',  # Primary selector
                                                    'button#btn-go',
                                                    'button:has-text("未入金予約の確認・支払へ")',
                                                    'button[onclick*="gRsvCreditInitListAction"]',
                                                    'button[onclick*="doAction"][onclick*="gRsvCreditInitListAction"]'
                                                ]
                                                
                                                for selector in payment_button_selectors:
                                                    try:
                                                        payment_button = await page.query_selector(selector)
                                                        if payment_button:
                                                            # Verify this is the payment button by checking onclick or text
                                                            button_onclick = await payment_button.get_attribute('onclick') or ''
                                                            button_text = await payment_button.inner_text()
                                                            
                                                            if 'gRsvCreditInitListAction' in button_onclick or '未入金予約の確認・支払へ' in button_text:
                                                                is_disabled = await payment_button.get_attribute('disabled')
                                                                if not is_disabled:
                                                                    await payment_button.scroll_into_view_if_needed()
                                                                    await page.wait_for_timeout(500)
                                                                    await payment_button.click()
                                                                    logger.info(f"Clicked '未入金予約の確認・支払へ' button using selector: {selector}")
                                                                    
                                                                    await page.wait_for_load_state('networkidle', timeout=30000)
                                                                    await page.wait_for_timeout(2000)
                                                                    payment_button_clicked = True
                                                                    logger.info("Successfully clicked '未入金予約の確認・支払へ' button - navigated to payment page")
                                                                    
                                                                    # After clicking payment button, check if we're on the payment page
                                                                    # and click "もどる" (Back) button to return to home page
                                                                    await page.wait_for_load_state('networkidle', timeout=30000)
                                                                    await page.wait_for_timeout(2000)
                                                                    current_url_after_payment = page.url
                                                                    page_title_after_payment = await page.title()
                                                                    
                                                                    if 'rsvWRsvGetNotPaymentRsvDataListAction' in current_url_after_payment or 'rsvWCreditInitListAction' in current_url_after_payment or '未入金予約の確認・支払' in page_title_after_payment:
                                                                        logger.info("Detected payment page - clicking 'もどる' (Back) button to return to home page...")
                                                                        
                                                                        back_button_clicked = False
                                                                        back_button_selectors = [
                                                                            'button.btn-back:has-text("もどる")',
                                                                            'button:has-text("もどる")',
                                                                            'button[onclick*="gRsvWOpeHomeAction"]',
                                                                            'button[onclick*="doAction"][onclick*="gRsvWOpeHomeAction"]',
                                                                            '.btn-back',
                                                                            'button.btn-back'
                                                                        ]
                                                                        
                                                                        for back_selector in back_button_selectors:
                                                                            try:
                                                                                back_button = await page.query_selector(back_selector)
                                                                                if back_button:
                                                                                    # Verify this is the back button by checking onclick or text
                                                                                    button_onclick = await back_button.get_attribute('onclick') or ''
                                                                                    button_text = await back_button.inner_text()
                                                                                    
                                                                                    if 'gRsvWOpeHomeAction' in button_onclick or 'もどる' in button_text:
                                                                                        is_disabled = await back_button.get_attribute('disabled')
                                                                                        if not is_disabled:
                                                                                            await back_button.scroll_into_view_if_needed()
                                                                                            await page.wait_for_timeout(500)
                                                                                            await back_button.click()
                                                                                            logger.info(f"Clicked 'もどる' button using selector: {back_selector}")
                                                                                            
                                                                                            await page.wait_for_load_state('networkidle', timeout=30000)
                                                                                            await page.wait_for_timeout(2000)
                                                                                            back_button_clicked = True
                                                                                            logger.info("Successfully clicked 'もどる' button - returned to home page")
                                                                                            break
                                                                            except Exception as e:
                                                                                logger.debug(f"Failed to click back button with selector {back_selector}: {e}")
                                                                                continue
                                                                        
                                                                        if not back_button_clicked:
                                                                            logger.warning("Could not find/click 'もどる' button on payment page")
                                                                    
                                                                    break
                                                    except Exception as e:
                                                        logger.debug(f"Failed to click payment button with selector {selector}: {e}")
                                                        continue
                                                
                                                if not payment_button_clicked:
                                                    logger.warning("Could not find/click '未入金予約の確認・支払へ' button on reservation completion page")
                                    else:
                                        logger.info("Not on Terms of Use page - continuing normally")
                                else:
                                    logger.warning("'予約' button is disabled - cannot proceed to reservation")
                            else:
                                logger.warning("'予約' button (#btn-go) not found on page")
                        except Exception as e:
                            logger.warning(f"Error clicking '予約' button or handling Terms of Use page: {e}")
                            import traceback
                            logger.warning(traceback.format_exc())
                            # Continue even if button click fails - return slots anyway
                    else:
                        logger.info(f"Slots clicked flag is 0 - no slots were clicked, skipping '予約' button click")
                
                # Return success indicator with extracted slots
                return {'success': True, 'message': 'Search completed via form', 'page': page, 'slots': slots}
                
            except Exception as e:
                logger.error(f"Failed to trigger search: {e}")
                raise
                
        except Exception as e:
            logger.error(f"Error in search_availability_via_form: {e}")
            raise
        # Don't close the page - keep it alive to maintain session
        # The page will be closed when stop() is called
    
    async def click_reservation_button_if_slots_found(self, page: Page, slots_clicked_flag: int, slots: List[Dict]) -> bool:
        """Click the '予約' button if slots were found and clicked.
        
        This is a helper method to handle the reservation button clicking logic
        that can be reused when slots are found in subsequent courts.
        
        Args:
            page: Playwright page object
            slots_clicked_flag: Flag indicating if slots were clicked (1) or not (0)
            slots: List of slots that were found
            
        Returns:
            True if button was clicked successfully, False otherwise
        """
        if slots_clicked_flag != 1:
            logger.info(f"Slots clicked flag is {slots_clicked_flag} - no slots were clicked, skipping '予約' button click")
            return False
        
        logger.info(f"Slots clicked flag is 1 - clicking '予約' button to proceed to reservation page (found {len(slots)} slot(s))...")
        try:
            # Wait for the button to be visible
            await page.wait_for_selector('#btn-go', state='visible', timeout=10000)
            
            # Find and click the correct "予約" button
            reserve_button = None
            btn_go_selectors = [
                '#btn-go',  # Primary selector
                'button#btn-go',
                'button.btn-go:has-text("予約")'
            ]
            
            for selector in btn_go_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        onclick = await button.get_attribute('onclick') or ''
                        button_text = await button.inner_text()
                        
                        if 'gRsvWOpeReservedApplyAction' in onclick or ('予約' in button_text and 'gRsvWInstUseruleRsvApplyAction' not in onclick):
                            reserve_button = button
                            logger.info(f"Found correct '予約' button with onclick: {onclick[:100] if onclick else 'none'}")
                            break
                except:
                    continue
            
            if not reserve_button:
                reserve_button = await page.query_selector('#btn-go')
                if reserve_button:
                    onclick = await reserve_button.get_attribute('onclick') or ''
                    logger.info(f"Using #btn-go button with onclick: {onclick[:100] if onclick else 'none'}")
            
            if reserve_button:
                is_disabled = await reserve_button.get_attribute('disabled')
                if not is_disabled:
                    await reserve_button.scroll_into_view_if_needed()
                    await page.wait_for_timeout(500)
                    await reserve_button.click()
                    logger.info("Successfully clicked '予約' button - navigating to reservation page")
                    
                    await page.wait_for_load_state('networkidle', timeout=30000)
                    await page.wait_for_timeout(2000)
                    logger.info("Navigation to reservation page completed")
                    
                    # Handle Terms of Use page and reservation confirmation (same logic as in search_availability_via_form)
                    current_url = page.url
                    page_title = await page.title()
                    if 'rsvWOpeReservedApplyAction' in current_url or '利用規約' in page_title:
                        logger.info("Detected Terms of Use page - handling agreement...")
                        
                        # Click "利用規約に同意する"
                        logger.info("Clicking '利用規約に同意する' label...")
                        agreement_clicked = False
                        agreement_selectors = [
                            'label[for="ruleFg_1"]',
                            'label.btn.radiobtn[for="ruleFg_1"]',
                            'label:has-text("利用規約に同意する")',
                            'input[type="radio"][value="1"][name*="rule"]',
                            'input[type="radio"][id="ruleFg_1"]'
                        ]
                        
                        for selector in agreement_selectors:
                            try:
                                element = await page.query_selector(selector)
                                if element:
                                    tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                                    if tag_name == 'label':
                                        await element.scroll_into_view_if_needed()
                                        await page.wait_for_timeout(300)
                                        await element.click()
                                        logger.info(f"Clicked agreement label using selector: {selector}")
                                    else:
                                        await element.scroll_into_view_if_needed()
                                        await page.wait_for_timeout(300)
                                        await element.check()
                                        logger.info(f"Checked agreement input using selector: {selector}")
                                    await page.wait_for_timeout(500)
                                    agreement_clicked = True
                                    break
                            except Exception as e:
                                logger.debug(f"Failed to click agreement with selector {selector}: {e}")
                                continue
                        
                        if not agreement_clicked:
                            logger.warning("Could not find/click agreement option, trying to proceed anyway")
                        
                        # Click "確認" button
                        logger.info("Clicking '確認' button...")
                        confirm_clicked = False
                        confirm_selectors = [
                            '#btn-go',
                            'button#btn-go',
                            'button:has-text("確認")',
                            'button[type="submit"]:has-text("確認")',
                            'button[onclick*="gRsvWInstUseruleRsvApplyAction"]'
                        ]
                        
                        for selector in confirm_selectors:
                            try:
                                confirm_button = await page.query_selector(selector)
                                if confirm_button:
                                    is_disabled = await confirm_button.get_attribute('disabled')
                                    if not is_disabled:
                                        await confirm_button.scroll_into_view_if_needed()
                                        await page.wait_for_timeout(500)
                                        await confirm_button.click()
                                        logger.info(f"Clicked '確認' button using selector: {selector}")
                                        
                                        await page.wait_for_load_state('networkidle', timeout=30000)
                                        await page.wait_for_timeout(2000)
                                        confirm_clicked = True
                                        logger.info("Successfully handled Terms of Use page")
                                        break
                            except Exception as e:
                                logger.debug(f"Failed to click confirm with selector {selector}: {e}")
                                continue
                        
                        if not confirm_clicked:
                            logger.warning("Could not find/click '確認' button on Terms of Use page")
                        
                        # Handle reservation confirmation page
                        await page.wait_for_load_state('networkidle', timeout=30000)
                        await page.wait_for_timeout(2000)
                        current_url_after_confirm = page.url
                        page_title_after_confirm = await page.title()
                        
                        if 'rsvWInstUseruleRsvApplyAction' in current_url_after_confirm or 'rsvWInstRsvApplyAction' in current_url_after_confirm or '予約内容確認' in page_title_after_confirm:
                            logger.info("Detected reservation confirmation page - filling in number of users for each reservation slot...")
                            
                            # Fill in "利用人数" (Number of Users) for each reservation slot
                            # Default number of users: 4 (as shown in the reservation completion page)
                            default_user_count = 4
                            
                            try:
                                # Strategy 1: Find inputs by looking for "利用人数" labels and their associated inputs
                                user_count_inputs = []
                                
                                # Find all elements containing "利用人数" text (labels or text nodes)
                                try:
                                    # Use XPath or text-based search to find "利用人数" labels
                                    # Then find the input field that follows or is associated with each label
                                    labels_with_text = await page.query_selector_all('label:has-text("利用人数"), td:has-text("利用人数"), div:has-text("利用人数")')
                                    
                                    for label_element in labels_with_text:
                                        try:
                                            # Try to find associated input using 'for' attribute
                                            label_for = await label_element.get_attribute('for')
                                            if label_for:
                                                associated_input = await page.query_selector(f'input#{label_for}, input[name="{label_for}"]')
                                                if associated_input:
                                                    user_count_inputs.append(associated_input)
                                                    continue
                                            
                                            # If no 'for' attribute, find input in the same container or nearby
                                            # Get parent container
                                            parent = await label_element.evaluate_handle('el => el.closest("div, form, tr, td, table")')
                                            if parent:
                                                # Find input in the same container
                                                inputs_in_container = await parent.as_element().query_selector_all('input[type="text"], input[type="number"]')
                                                for inp in inputs_in_container:
                                                    # Check if this input has placeholder indicating it's for user count
                                                    placeholder = await inp.get_attribute('placeholder') or ''
                                                    name_attr = await inp.get_attribute('name') or ''
                                                    if '半角' in placeholder or 'num' in name_attr.lower() or '人数' in name_attr:
                                                        if inp not in user_count_inputs:
                                                            user_count_inputs.append(inp)
                                        except Exception as e:
                                            logger.debug(f"Error processing label element: {e}")
                                            continue
                                except Exception as e:
                                    logger.debug(f"Error finding labels with '利用人数' text: {e}")
                                
                                # Strategy 2: Find inputs by name attributes (fallback)
                                if not user_count_inputs:
                                    user_count_selectors = [
                                        'input[name*="applyNum"]',
                                        'input[name*="人数"]',
                                        'input[name*="userCount"]',
                                        'input[placeholder*="半角文字で入力"]'
                                    ]
                                    
                                    for selector in user_count_selectors:
                                        try:
                                            inputs = await page.query_selector_all(selector)
                                            if inputs:
                                                for inp in inputs:
                                                    if inp not in user_count_inputs:
                                                        user_count_inputs.append(inp)
                                                if user_count_inputs:
                                                    break
                                        except Exception as e:
                                            logger.debug(f"Error finding inputs with selector {selector}: {e}")
                                            continue
                                
                                # Strategy 3: Find all inputs in reservation slot containers (No.1, No.2, etc.)
                                if not user_count_inputs:
                                    try:
                                        # Find containers that might contain reservation slots
                                        slot_containers = await page.query_selector_all('div:has-text("No."), form:has-text("利用人数")')
                                        for container in slot_containers:
                                            try:
                                                inputs_in_slot = await container.query_selector_all('input[type="text"], input[type="number"]')
                                                for inp in inputs_in_slot:
                                                    placeholder = await inp.get_attribute('placeholder') or ''
                                                    name_attr = await inp.get_attribute('name') or ''
                                                    if '半角' in placeholder or 'num' in name_attr.lower() or '人数' in name_attr:
                                                        if inp not in user_count_inputs:
                                                            user_count_inputs.append(inp)
                                            except:
                                                continue
                                    except Exception as e:
                                        logger.debug(f"Error finding inputs in slot containers: {e}")
                                
                                # Fill in the user count for each input found
                                if user_count_inputs:
                                    logger.info(f"Found {len(user_count_inputs)} '利用人数' input field(s) - filling with {default_user_count} users each...")
                                    for idx, user_input in enumerate(user_count_inputs, 1):
                                        try:
                                            # Clear existing value and fill with default
                                            await user_input.clear()
                                            await user_input.fill(str(default_user_count))
                                            await page.wait_for_timeout(200)  # Small delay between fills
                                            logger.info(f"Filled '利用人数' field {idx} with {default_user_count} users")
                                        except Exception as e:
                                            logger.warning(f"Failed to fill user count input {idx}: {e}")
                                            continue
                                else:
                                    logger.warning("Could not find '利用人数' input fields - proceeding without filling user count")
                                
                                # Wait a bit after filling all fields
                                await page.wait_for_timeout(500)
                                
                            except Exception as e:
                                logger.warning(f"Error filling in user count fields: {e}")
                                import traceback
                                logger.warning(traceback.format_exc())
                                # Continue anyway - might still be able to proceed
                            
                            logger.info("Filled user count fields - clicking final '予約' button...")
                            
                            final_reserve_clicked = False
                            final_reserve_selectors = [
                                '#btn-go',
                                'button#btn-go',
                                'button:has-text("予約")',
                                'button[onclick*="gRsvWInstRsvApplyAction"]',
                                'button[onclick*="checkTextValue"]'
                            ]
                            
                            for selector in final_reserve_selectors:
                                try:
                                    final_button = await page.query_selector(selector)
                                    if final_button:
                                        button_onclick = await final_button.get_attribute('onclick') or ''
                                        button_text = await final_button.inner_text()
                                        
                                        if 'gRsvWInstRsvApplyAction' in button_onclick or ('予約' in button_text and 'checkTextValue' in button_onclick):
                                            is_disabled = await final_button.get_attribute('disabled')
                                            if not is_disabled:
                                                await final_button.scroll_into_view_if_needed()
                                                await page.wait_for_timeout(500)
                                                
                                                dialog_handled = False
                                                
                                                async def handle_dialog(dialog):
                                                    nonlocal dialog_handled
                                                    dialog_message = dialog.message
                                                    logger.info(f"JavaScript dialog detected: {dialog_message}")
                                                    if "予約申込処理を行います" in dialog_message or "よろしいですか" in dialog_message:
                                                        logger.info("Accepting reservation confirmation dialog...")
                                                        await dialog.accept()
                                                        dialog_handled = True
                                                    else:
                                                        logger.warning(f"Unexpected dialog message: {dialog_message}, accepting anyway")
                                                        await dialog.accept()
                                                        dialog_handled = True
                                                
                                                page.on('dialog', handle_dialog)
                                                
                                                try:
                                                    await final_button.click()
                                                    logger.info(f"Clicked final '予約' button on reservation confirmation page using selector: {selector}")
                                                    
                                                    await page.wait_for_timeout(1000)
                                                    
                                                    if dialog_handled:
                                                        logger.info("Dialog was handled successfully")
                                                    else:
                                                        logger.warning("Dialog handler was set but dialog may not have appeared")
                                                    
                                                    await page.wait_for_load_state('networkidle', timeout=30000)
                                                    await page.wait_for_timeout(2000)
                                                    final_reserve_clicked = True
                                                    logger.info("Successfully clicked final '予約' button and handled dialog - booking should be completed")
                                                    break
                                                except Exception as click_error:
                                                    logger.warning(f"Error clicking button or handling dialog: {click_error}")
                                                    try:
                                                        async with page.expect_dialog() as dialog_info:
                                                            await final_button.click()
                                                        dialog = await dialog_info.value
                                                        logger.info(f"Dialog appeared: {dialog.message}")
                                                        await dialog.accept()
                                                        logger.info("Accepted dialog using expect_dialog")
                                                        await page.wait_for_load_state('networkidle', timeout=30000)
                                                        await page.wait_for_timeout(2000)
                                                        final_reserve_clicked = True
                                                        logger.info("Successfully clicked final '予約' button and handled dialog (alternative method) - booking should be completed")
                                                        break
                                                    except Exception as alt_error:
                                                        logger.warning(f"Alternative dialog handling also failed: {alt_error}")
                                                        continue
                                                finally:
                                                    try:
                                                        page.remove_listener('dialog', handle_dialog)
                                                    except:
                                                        pass
                                except Exception as e:
                                    logger.debug(f"Failed to click final reserve button with selector {selector}: {e}")
                                    continue
                            
                            if not final_reserve_clicked:
                                logger.warning("Could not find/click final '予約' button on reservation confirmation page")
                        
                        # After clicking final '予約' button, check if we're on reservation completion page
                        # and click "未入金予約の確認・支払へ" button if present
                        await page.wait_for_load_state('networkidle', timeout=30000)
                        await page.wait_for_timeout(2000)
                        current_url_after_booking = page.url
                        page_title_after_booking = await page.title()
                        
                        if 'rsvWInstRsvApplyAction' in current_url_after_booking or '予約完了' in page_title_after_booking:
                            logger.info("Detected reservation completion page - clicking '未入金予約の確認・支払へ' button...")
                            
                            payment_button_clicked = False
                            payment_button_selectors = [
                                '#btn-go',  # Primary selector
                                'button#btn-go',
                                'button:has-text("未入金予約の確認・支払へ")',
                                'button[onclick*="gRsvCreditInitListAction"]',
                                'button[onclick*="doAction"][onclick*="gRsvCreditInitListAction"]'
                            ]
                            
                            for selector in payment_button_selectors:
                                try:
                                    payment_button = await page.query_selector(selector)
                                    if payment_button:
                                        # Verify this is the payment button by checking onclick or text
                                        button_onclick = await payment_button.get_attribute('onclick') or ''
                                        button_text = await payment_button.inner_text()
                                        
                                        if 'gRsvCreditInitListAction' in button_onclick or '未入金予約の確認・支払へ' in button_text:
                                            is_disabled = await payment_button.get_attribute('disabled')
                                            if not is_disabled:
                                                await payment_button.scroll_into_view_if_needed()
                                                await page.wait_for_timeout(500)
                                                await payment_button.click()
                                                logger.info(f"Clicked '未入金予約の確認・支払へ' button using selector: {selector}")
                                                
                                                await page.wait_for_load_state('networkidle', timeout=30000)
                                                await page.wait_for_timeout(2000)
                                                payment_button_clicked = True
                                                logger.info("Successfully clicked '未入金予約の確認・支払へ' button - navigated to payment page")
                                                
                                                # After clicking payment button, check if we're on the payment page
                                                # and click "もどる" (Back) button to return to home page
                                                await page.wait_for_load_state('networkidle', timeout=30000)
                                                await page.wait_for_timeout(2000)
                                                current_url_after_payment = page.url
                                                page_title_after_payment = await page.title()
                                                
                                                if 'rsvWRsvGetNotPaymentRsvDataListAction' in current_url_after_payment or 'rsvWCreditInitListAction' in current_url_after_payment or '未入金予約の確認・支払' in page_title_after_payment:
                                                    logger.info("Detected payment page - clicking 'もどる' (Back) button to return to home page...")
                                                    
                                                    back_button_clicked = False
                                                    back_button_selectors = [
                                                        'button.btn-back:has-text("もどる")',
                                                        'button:has-text("もどる")',
                                                        'button[onclick*="gRsvWOpeHomeAction"]',
                                                        'button[onclick*="doAction"][onclick*="gRsvWOpeHomeAction"]',
                                                        '.btn-back',
                                                        'button.btn-back'
                                                    ]
                                                    
                                                    for back_selector in back_button_selectors:
                                                        try:
                                                            back_button = await page.query_selector(back_selector)
                                                            if back_button:
                                                                # Verify this is the back button by checking onclick or text
                                                                button_onclick = await back_button.get_attribute('onclick') or ''
                                                                button_text = await back_button.inner_text()
                                                                
                                                                if 'gRsvWOpeHomeAction' in button_onclick or 'もどる' in button_text:
                                                                    is_disabled = await back_button.get_attribute('disabled')
                                                                    if not is_disabled:
                                                                        await back_button.scroll_into_view_if_needed()
                                                                        await page.wait_for_timeout(500)
                                                                        await back_button.click()
                                                                        logger.info(f"Clicked 'もどる' button using selector: {back_selector}")
                                                                        
                                                                        await page.wait_for_load_state('networkidle', timeout=30000)
                                                                        await page.wait_for_timeout(2000)
                                                                        back_button_clicked = True
                                                                        logger.info("Successfully clicked 'もどる' button - returned to home page")
                                                                        break
                                                        except Exception as e:
                                                            logger.debug(f"Failed to click back button with selector {back_selector}: {e}")
                                                            continue
                                                    
                                                    if not back_button_clicked:
                                                        logger.warning("Could not find/click 'もどる' button on payment page")
                                                
                                                break
                                except Exception as e:
                                    logger.debug(f"Failed to click payment button with selector {selector}: {e}")
                                    continue
                            
                            if not payment_button_clicked:
                                logger.warning("Could not find/click '未入金予約の確認・支払へ' button on reservation completion page")
                    return True
                else:
                    logger.warning("'予約' button is disabled - cannot proceed to reservation")
                    return False
            else:
                logger.warning("'予約' button (#btn-go) not found on page")
                return False
        except Exception as e:
            logger.warning(f"Error clicking '予約' button or handling Terms of Use page: {e}")
            import traceback
            logger.warning(traceback.format_exc())
            return False
    
    async def change_park_and_search(self, next_area_code: str, next_park_name: str = None) -> Dict:
        """Change park selection and search again when no results are found.
        
        This method clicks [条件変更] button to expand the search form,
        selects a different park, and searches again.
        
        Args:
            next_area_code: Area code for the next park to try
            next_park_name: Optional park name for logging
            
        Returns:
            Search result status
        """
        if not self.main_page or self.main_page.is_closed():
            raise Exception("Main page not available for changing park")
        
        page = self.main_page
        logger.info(f"Changing park to: {next_park_name or next_area_code}")
        
        try:
            # Step 1: Click [条件変更] button to expand search form
            # The button has id="change-condition" and uses Bootstrap collapse
            logger.info("Clicking [条件変更] button to expand search form...")
            change_conditions_selectors = [
                '#change-condition',  # Primary selector from HTML
                'button#change-condition',
                'button:has-text("条件変更")',
                'a:has-text("条件変更")',
                'button:has-text("▲条件変更")',
                'a:has-text("▲条件変更")',
                'button[title*="条件変更"]',
                'a[title*="条件変更"]'
            ]
            
            button_clicked = False
            for selector in change_conditions_selectors:
                try:
                    await page.wait_for_selector(selector, state='visible', timeout=10000)
                    await page.click(selector)
                    # Wait for Bootstrap collapse animation to complete
                    await page.wait_for_timeout(1500)
                    button_clicked = True
                    logger.info(f"Clicked [条件変更] using selector: {selector}")
                    break
                except:
                    continue
            
            if not button_clicked:
                raise Exception("Could not find [条件変更] button")
            
            # Step 2: Wait for search form to be visible/expanded (#free-search-cond)
            # Check if the collapsed form is now visible
            logger.info("Waiting for search form to expand...")
            try:
                await page.wait_for_selector('#free-search-cond.show, #free-search-cond:not(.collapse)', state='visible', timeout=5000)
                logger.info("Search form expanded")
            except:
                # Form might already be visible or use different class
                try:
                    await page.wait_for_selector('#bname', state='visible', timeout=5000)
                    logger.info("Park dropdown is visible")
                except:
                    logger.warning("Could not confirm form expansion, continuing anyway")
            
            await page.wait_for_timeout(500)
            
            # Step 3: Select the new park in the dropdown (#bname)
            logger.info(f"Selecting new park: {next_park_name or next_area_code} (area_code: {next_area_code})...")
            park_selectors = [
                'select#bname',  # Primary selector from HTML
                'select[name*="bcd"]',
                'select[name*="area"]',
                'select[name*="どこ"]'
            ]
            
            park_selected = False
            for selector in park_selectors:
                try:
                    # Wait for dropdown to be visible
                    await page.wait_for_selector(selector, state='visible', timeout=10000)
                    element = await page.query_selector(selector)
                    if element:
                        # Select the new park by area code value
                        await page.select_option(selector, value=next_area_code)
                        await page.wait_for_timeout(1000)  # Wait for any JS to update
                        park_selected = True
                        logger.info(f"Selected new park {next_park_name or next_area_code} using selector: {selector}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to select park with {selector}: {e}")
                    continue
            
            if not park_selected:
                raise Exception(f"Could not select new park {next_park_name or next_area_code} in dropdown")
            
            # Step 4: Ensure "1か月" and "テニス" are still selected
            # (They should be, but verify)
            try:
                await page.click('label.btn.radiobtn[for="thismonth"]')
                await page.wait_for_timeout(500)
            except:
                try:
                    await page.click('input#thismonth')
                    await page.wait_for_timeout(500)
                except:
                    logger.warning("Could not ensure date option is selected")
            
            try:
                await page.select_option('select#purpose, select[name*="purpose"]', value='31000000_31011700')
                await page.wait_for_timeout(500)
            except:
                logger.warning("Could not ensure activity is selected")
            
            # Step 5: Click search button (再検索) - button has id="btn-search"
            logger.info("Clicking search button (再検索) to search with new park...")
            search_selectors = [
                '#btn-search',  # Primary selector from HTML
                'button#btn-search',
                'button:has-text("再検索")',
                'button:has-text("検索")',
                'input[type="submit"][value*="検索"]'
            ]
            
            search_clicked = False
            for selector in search_selectors:
                try:
                    await page.wait_for_selector(selector, state='visible', timeout=10000)
                    # Click and wait for navigation/results to load
                    async with page.expect_navigation(wait_until='networkidle', timeout=120000):
                        await page.click(selector)
                    await page.wait_for_load_state('networkidle', timeout=120000)
                    await page.wait_for_timeout(2000)
                    search_clicked = True
                    logger.info(f"Clicked search (再検索) using selector: {selector}")
                    break
                except Exception as e:
                    logger.warning(f"Failed to click search with {selector}: {e}")
                    continue
            
            if not search_clicked:
                raise Exception("Could not find search button (再検索)")
            
            # Step 6: Ensure "施設ごと" tab is active (do NOT click "日付順")
            logger.info("Ensuring '施設ごと' tab is active after park change...")
            try:
                await page.wait_for_selector('#free-info-nav, .nav-tabs', state='visible', timeout=10000)
                active_tab = await page.query_selector('#free-info-nav .nav-link.active, .nav-tabs .nav-link.active')
                if active_tab:
                    tab_text = await active_tab.inner_text()
                    if "日付順" in tab_text:
                        logger.info("Switching from 日付順 to 施設ごと...")
                        await page.click('a:has-text("施設ごと")')
                        await page.wait_for_load_state('networkidle', timeout=30000)
                        await page.wait_for_timeout(1000)
                    else:
                        logger.info("施設ごと tab is already active")
            except:
                logger.warning("Could not verify tab state, assuming 施設ごと is default")
            
            return {'success': True, 'message': f'Park changed to {next_park_name or next_area_code} and searched'}
            
        except Exception as e:
            logger.error(f"Error changing park: {e}")
            raise
    
    async def book_slot(self, slot_data: Dict, try_next_park_on_no_results: bool = True) -> Dict:
        """Book a time slot.
        
        Args:
            slot_data: Slot information from API
            
        Returns:
            Reservation details including reservation number
        """
        if not self.context:
            await self.start()
        
        # Use main page if available (maintains session), otherwise create new page
        if self.main_page and not self.main_page.is_closed():
            page = self.main_page
            logger.info("Reusing main page for booking to maintain session")
        else:
            page = await self.context.new_page()
            logger.info("Created new page for booking")
        
        try:
            # CRITICAL: First fill the search form on the current page (home page)
            # Do NOT navigate away - this will destroy the session
            current_url = page.url
            logger.info(f"Starting booking from current page: {current_url}")
            
            # If we're on the home page (index.jsp), fill the form there first
            # Then the search will navigate us to the date view page naturally
            if 'index.jsp' in current_url or 'UserAttestation' in current_url:
                logger.info("On home page - filling search form before navigating to date view")
                area_code = slot_data.get('area_code', '1400_0')
                
                # Fill search form on home page
                try:
                    # Select "1 month" date option
                    await page.wait_for_selector('label.btn.radiobtn[for="thismonth"]', state='visible', timeout=10000)
                    await page.click('label.btn.radiobtn[for="thismonth"]')
                    await page.wait_for_timeout(500)
                except:
                    try:
                        await page.click('input#thismonth')
                        await page.wait_for_timeout(500)
                    except:
                        logger.warning("Could not select date option on home page")
                
                # Select park
                await page.wait_for_selector('#bname', state='visible', timeout=10000)
                await page.select_option('#bname', value=area_code)
                await page.wait_for_timeout(500)
                
                # Select Tennis
                await page.wait_for_selector('#purpose', state='visible', timeout=10000)
                await page.select_option('#purpose', value='31000000_31011700')
                await page.wait_for_timeout(500)
                
                # Click search button - this will navigate to date view naturally (preserves session)
                logger.info("Clicking search button to navigate to date view...")
                try:
                    await page.click('button:has-text("検索")')
                except:
                    await page.click('#btn-search')
                await page.wait_for_load_state('networkidle', timeout=120000)
                await page.wait_for_timeout(2000)
            else:
                # If we're already on date view page, just proceed
                logger.info("Already on date view page or different page - proceeding with booking")
                # Navigate to date view only if we're not already there
            date_view_url = f"{settings.base_url}/rsvWOpeUnreservedDailyAction.do"
            if date_view_url not in current_url:
                logger.warning("Not on date view page - navigating (this might affect session)")
                await page.goto(date_view_url, wait_until='networkidle', timeout=120000)
                await page.wait_for_load_state('networkidle', timeout=120000)
            
                    # Fill form on date view page if needed
            area_code = slot_data.get('area_code', '1400_0')
            await page.wait_for_selector('#bname', state='visible', timeout=10000)
            await page.select_option('#bname', value=area_code)
            await page.wait_for_selector('#purpose', state='visible', timeout=10000)
            await page.select_option('#purpose', value='31000000_31011700')
            try:
                await page.click('label.btn.radiobtn[for="thismonth"]')
            except:
                await page.click('input#thismonth')
            try:
                await page.click('#btn-search')
            except:
                await page.click('button:has-text("検索")')
                await page.wait_for_load_state('networkidle', timeout=120000)
            
            # After search, ensure "施設ごと" tab is active (do NOT click "日付順")
            logger.info("Ensuring '施設ごと' tab is active for booking...")
            try:
                await page.wait_for_selector('#free-info-nav, .nav-tabs', state='visible', timeout=10000)
                active_tab = await page.query_selector('#free-info-nav .nav-link.active, .nav-tabs .nav-link.active')
                if active_tab:
                    tab_text = await active_tab.inner_text()
                    if "日付順" in tab_text:
                        logger.info("Switching from 日付順 to 施設ごと for booking...")
                        await page.click('a:has-text("施設ごと")')
                        await page.wait_for_load_state('networkidle', timeout=30000)
                        await page.wait_for_timeout(1000)
                    else:
                        logger.info("施設ごと tab is already active")
            except Exception as e:
                logger.warning(f"Could not verify tab state: {e}, assuming 施設ごと is default")
            
            # Check if results are displayed by checking actual div visibility
            logger.info("Checking if search was successful...")
            await page.wait_for_timeout(2000)  # Wait for results to render
            
            # CRITICAL: Check actual div visibility first (not just text content)
            # The divs can have text content but be hidden with style="display: none;"
            has_results = False
            has_reservation_buttons = False
            
            try:
                # Check actual div visibility first (highest priority)
                no_results_div = await page.query_selector('#unreserved-notfound')
                results_list_div = await page.query_selector('#unreserved-list')
                
                # Check #unreserved-notfound visibility first (highest priority)
                if no_results_div:
                    no_results_visible = await no_results_div.evaluate('el => window.getComputedStyle(el).display !== "none"')
                    if no_results_visible:
                        logger.info("No results found - #unreserved-notfound is visible (display: block)")
                        has_results = False
                        # Don't check anything else - this is definitive
                    else:
                        # #unreserved-notfound exists but is hidden, check #unreserved-list
                        if results_list_div:
                            results_list_visible = await results_list_div.evaluate('el => window.getComputedStyle(el).display !== "none"')
                            if results_list_visible:
                                logger.info("Results found - #unreserved-list is visible (display: block)")
                                has_results = True
                            else:
                                logger.info("Both divs exist but both are hidden - checking buttons as fallback")
                                # Both divs exist but both hidden - check buttons
                                reservation_buttons_check = await page.query_selector_all('button:has-text("予約"), td.reservation button.btn-go')
                                has_reservation_buttons = len(reservation_buttons_check) > 0
                                if has_reservation_buttons:
                                    logger.info(f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results")
                                    has_results = True
                                else:
                                    logger.info("No reservation buttons found - treating as no results")
                                    has_results = False
                        else:
                            # #unreserved-notfound exists but hidden, and #unreserved-list doesn't exist
                            logger.info("#unreserved-notfound exists but hidden, #unreserved-list not found - checking buttons")
                            reservation_buttons_check = await page.query_selector_all('button:has-text("予約"), td.reservation button.btn-go')
                            has_reservation_buttons = len(reservation_buttons_check) > 0
                            if has_reservation_buttons:
                                logger.info(f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results")
                                has_results = True
                            else:
                                has_results = False
                else:
                    # #unreserved-notfound doesn't exist, check #unreserved-list
                    if results_list_div:
                        results_list_visible = await results_list_div.evaluate('el => window.getComputedStyle(el).display !== "none"')
                        if results_list_visible:
                            logger.info("Results found - #unreserved-list is visible (display: block)")
                            has_results = True
                        else:
                            logger.info("#unreserved-list exists but is hidden - checking buttons")
                            reservation_buttons_check = await page.query_selector_all('button:has-text("予約"), td.reservation button.btn-go')
                            has_reservation_buttons = len(reservation_buttons_check) > 0
                            if has_reservation_buttons:
                                logger.info(f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results")
                                has_results = True
                            else:
                                has_results = False
                    else:
                        # Neither div exists - check buttons as fallback
                        logger.info("Neither div found - checking buttons as fallback")
                        reservation_buttons_check = await page.query_selector_all('button:has-text("予約"), td.reservation button.btn-go')
                        has_reservation_buttons = len(reservation_buttons_check) > 0
                        if has_reservation_buttons:
                            logger.info(f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results")
                            has_results = True
                        else:
                            has_results = False
                
                # If we still don't have reservation buttons but have results, check for them
                if has_results and not has_reservation_buttons:
                    reservation_buttons_check = await page.query_selector_all('button:has-text("予約"), td.reservation button.btn-go')
                    has_reservation_buttons = len(reservation_buttons_check) > 0
                    if has_reservation_buttons:
                        logger.info(f"Found {len(reservation_buttons_check)} [予約] buttons")
                        
            except Exception as e:
                logger.warning(f"Error checking for results: {e}")
                import traceback
                logger.warning(traceback.format_exc())
                has_results = False
            
            # CRITICAL: If we have bookable dates, do NOT click "条件変更" - proceed directly to booking
            if has_results or has_reservation_buttons:
                logger.info("Bookable dates found - skipping '条件変更', proceeding to click 'さらに表示' and '予約'")
                # Skip the failure handling below and go straight to booking flow
            else:
                logger.warning("Search failed - no results found. Clicking '条件変更' to select another park...")
                if try_next_park_on_no_results:
                    from app.config import settings
                    current_area_code = slot_data.get('area_code', '')
                    current_bcd = slot_data.get('bcd', '')
                    
                    # Find current park index and get next park
                    current_park_index = -1
                    for i, park in enumerate(settings.target_parks):
                        if park['area'] == current_area_code or park['bcd'] == current_bcd:
                            current_park_index = i
                            break
                    
                    # Try next park if available
                    if current_park_index >= 0 and current_park_index < len(settings.target_parks) - 1:
                        next_park = settings.target_parks[current_park_index + 1]
                        logger.info(f"No results for current park, trying next park: {next_park['name']}")
                        try:
                            # Change park and search again using [条件変更] button
                            await self.change_park_and_search(
                                next_area_code=next_park['area'],
                                next_park_name=next_park['name']
                            )
                            
                            # Wait for results to load
                            await page.wait_for_timeout(2000)
                            
                            # Check for results again using div visibility
                            no_results_div = await page.query_selector('#unreserved-notfound')
                            results_list_div = await page.query_selector('#unreserved-list')
                            
                            has_results_after_change = False
                            if no_results_div:
                                no_results_visible = await no_results_div.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                if no_results_visible:
                                    logger.warning(f"No results for {next_park['name']} either")
                                    raise Exception(f"No available slots found for park {next_park['name']} - try next park")
                                else:
                                    if results_list_div:
                                        results_list_visible = await results_list_div.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                        has_results_after_change = results_list_visible
                            elif results_list_div:
                                results_list_visible = await results_list_div.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                has_results_after_change = results_list_visible
                            
                            if has_results_after_change:
                                logger.info(f"Found results for {next_park['name']}, continuing with booking")
                            else:
                                logger.warning(f"No results for {next_park['name']} either")
                                raise Exception(f"No available slots found for park {next_park['name']} - try next park")
                                # Update slot_data with new park info
                                slot_data['area_code'] = next_park['area']
                                slot_data['bcd'] = next_park['bcd']
                                slot_data['bcd_name'] = next_park['name']
                                has_results = True
                        except Exception as e:
                            if "No available slots found" in str(e):
                                raise  # Re-raise to try next park
                            logger.error(f"Error changing park: {e}")
                            raise Exception(f"No available slots found and failed to change park: {e}")
                    else:
                        # No more parks to try
                        park_display_name = slot_data.get('bcd_name') or slot_data.get('park_name') or 'unknown'
                        raise Exception(f"No available slots found for park {park_display_name} - no more parks to try")
                else:
                    # Don't try next park, just raise exception
                    park_display_name = slot_data.get('bcd_name') or slot_data.get('park_name') or 'unknown'
                    raise Exception(f"No available slots found for park {park_display_name} - try next park")
            
            # If results found OR reservation buttons exist, proceed to click "さらに表示" and then "予約"
            # This ensures we never click "条件変更" when bookable dates are present
            if has_results or has_reservation_buttons:
                logger.info("Results found - checking for 'さらに表示' (Show More) button to load all available dates...")
                max_load_more_clicks = 5  # Limit to prevent infinite loops
                load_more_clicks = 0
                
                while load_more_clicks < max_load_more_clicks:
                    try:
                        show_more_selectors = [
                            '#unreserved-moreBtn',
                            'button#unreserved-moreBtn',
                            'button:has-text("さらに表示")',
                            'button[onclick*="loadNext"]'
                        ]
                        
                        show_more_found = False
                        for selector in show_more_selectors:
                            try:
                                show_more_button = await page.query_selector(selector)
                                if show_more_button:
                                    # Check if button is visible
                                    is_visible = await show_more_button.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                    if is_visible:
                                        logger.info(f"Found 'さらに表示' button (click {load_more_clicks + 1}) - clicking to load more dates...")
                                        await page.click(selector)
                                        # Wait for additional results to load
                                        await page.wait_for_load_state('networkidle', timeout=60000)
                                        await page.wait_for_timeout(2000)
                                        load_more_clicks += 1
                                        show_more_found = True
                                        break
                            except:
                                continue
                        
                        if not show_more_found:
                            logger.info("No more 'さらに表示' button found - all dates loaded")
                            break
                    except Exception as e:
                        logger.warning(f"Error clicking 'さらに表示' button: {e}")
                        break
                
                if load_more_clicks > 0:
                    logger.info(f"Loaded additional dates by clicking 'さらに表示' {load_more_clicks} time(s)")
            else:
                logger.info("No results available - skipping 'さらに表示' button check")
            
            # Look for [予約] buttons in the results (after loading all dates if results exist)
            reservation_buttons = await page.query_selector_all('button:has-text("予約"), a:has-text("予約")')
            
            # If no reservation buttons found after success message, something went wrong
            if not reservation_buttons or len(reservation_buttons) == 0:
                logger.warning("No [予約] buttons found despite success message - may need to wait longer or check page state")
                # Wait a bit more and try again
                await page.wait_for_timeout(3000)
                reservation_buttons = await page.query_selector_all('button:has-text("予約"), a:has-text("予約")')
                
                if not reservation_buttons or len(reservation_buttons) == 0:
                    raise Exception("No [予約] buttons found on page - cannot proceed with booking")
            
            # Find the [予約] button that matches our slot
            # The HTML structure uses row IDs like: 20260105_1020_10200020_830_0
            # Format: {use_ymd}_{bcd}_{icd}_{start_time}_{index}
            time_str = str(slot_data['start_time']).zfill(4)
            use_ymd = str(slot_data['use_ymd'])
            bcd = str(slot_data.get('bcd', ''))
            icd = str(slot_data.get('icd', ''))
            
            logger.info(f"Looking for [予約] button for date {use_ymd}, time {time_str}, bcd {bcd}, icd {icd}...")
            
            reservation_button = None
            
            # Strategy 1: Try to find button by row ID pattern
            # Row ID format: {use_ymd}_{bcd}_{icd}_{start_time}_{index}
            # Note: The index suffix can vary, so we match without it
            if bcd and icd:
                try:
                    # Match pattern without index: {use_ymd}_{bcd}_{icd}_{start_time}_
                    row_id_pattern = f"{use_ymd}_{bcd}_{icd}_{time_str}_"
                    logger.info(f"Trying to find row with ID pattern: {row_id_pattern}*")
                    
                    # First, ensure all date sections are expanded (buttons might be in collapsed sections)
                    try:
                        # Find all collapsible date headers and expand them
                        date_headers = await page.query_selector_all('h3[id^="20"] button, h3[id^="20"] a')
                        for header in date_headers:
                            try:
                                # Check if section is collapsed
                                parent = await header.evaluate_handle('el => el.closest("h3")')
                                if parent:
                                    next_sibling = await parent.evaluate_handle('el => el.nextElementSibling')
                                    if next_sibling:
                                        classes = await next_sibling.get_attribute('class') or ''
                                        # If it has 'collapse' class and not 'show', expand it
                                        if 'collapse' in classes and 'show' not in classes:
                                            await header.click()
                                            await page.wait_for_timeout(500)
                            except:
                                continue
                    except Exception as e:
                        logger.warning(f"Error expanding date sections: {e}")
                    
                    # Find all rows that match the pattern (ignore index suffix)
                    all_rows = await page.query_selector_all('tr[id^="20"]')  # Rows with IDs starting with year
                    logger.info(f"Found {len(all_rows)} rows with date IDs")
                    
                    for row in all_rows:
                        row_id = await row.get_attribute('id')
                        if not row_id:
                            continue
                        
                        # Check if row ID matches pattern (ignoring index suffix)
                        # Pattern: {use_ymd}_{bcd}_{icd}_{start_time}_{anything}
                        if row_id.startswith(row_id_pattern):
                            # Found matching row, get the button inside it
                            button = await row.query_selector('button:has-text("予約"), td.reservation button, button.btn-go')
                            if button:
                                # Check if button is visible
                                is_visible = await button.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                if is_visible:
                                    reservation_button = button
                                    logger.info(f"Found [予約] button in row {row_id}")
                                    break
                except Exception as e:
                    logger.warning(f"Error finding button by row ID: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
            
            # Strategy 2: Find button by matching date and time in the same row
            if not reservation_button:
                try:
                    logger.info("Trying to find button by matching date and time in table rows...")
                    # Find all table rows with reservation buttons (rows with IDs starting with year)
                    all_rows = await page.query_selector_all('tr[id^="20"]')
                    logger.info(f"Checking {len(all_rows)} rows for date/time match...")
                    
                    for row in all_rows:
                        try:
                            row_id = await row.get_attribute('id')
                            if not row_id:
                                continue
                            
                            # Check if row contains the date
                            row_text = await row.inner_text()
                            
                            # Check if row contains date pattern
                            # Format: YYYYMMDD -> check for "YYYY年MM月DD日" or just the numbers
                            date_match = (
                                str(use_ymd) in row_id or  # Row ID contains the date
                                f"{use_ymd[:4]}年" in row_text or
                                f"{use_ymd[4:6]}月" in row_text or
                                f"{use_ymd[6:8]}日" in row_text or
                                str(use_ymd) in row_text
                            )
                            
                            # Check if row contains the time
                            # Format: HHMM -> check for "HH時MM分" or just the numbers
                            time_hour = int(time_str[:2])
                            time_min = int(time_str[2:])
                            time_match = (
                                time_str in row_id or  # Row ID contains the time
                                f"{time_hour}時{time_min}分" in row_text or
                                f"{time_hour:02d}時{time_min:02d}分" in row_text or
                                time_str in row_text
                            )
                            
                            if date_match and time_match:
                                logger.info(f"Found matching row by date/time: {row_id}")
                                # Found matching row, get the button
                                button = await row.query_selector('button:has-text("予約"), td.reservation button, button.btn-go')
                                if button:
                                    is_visible = await button.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                    if is_visible:
                                        reservation_button = button
                                        logger.info(f"Found [予約] button by matching date/time in row {row_id}")
                                        break
                        except Exception as e:
                            logger.warning(f"Error checking row: {e}")
                            continue
                except Exception as e:
                    logger.warning(f"Error finding button by date/time match: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
            
            # Strategy 3: Click first available [予約] button if we can't find specific one
            if not reservation_button and reservation_buttons:
                logger.info(f"Could not find specific slot, trying first available [予約] button from {len(reservation_buttons)} buttons...")
                # Try to find a visible button
                for btn in reservation_buttons:
                    try:
                        is_visible = await btn.evaluate('el => window.getComputedStyle(el).display !== "none"')
                        if is_visible:
                            reservation_button = btn
                            logger.info("Using first visible [予約] button")
                            break
                    except:
                        continue
                
                # If still no button, use first one anyway
                if not reservation_button:
                    reservation_button = reservation_buttons[0]
                    logger.info("Using first [予約] button (visibility check failed)")
            
            if not reservation_button:
                # No results found - this park has no available slots
                # Return error so monitoring service can try next park
                raise Exception(f"No available slots found for park {slot_data.get('bcd_name', 'unknown')} - try next park")
            
            # Click [予約] button - this will navigate to terms agreement page
            logger.info("Clicking [予約] button...")
            try:
                # Ensure button is visible and scroll into view
                await reservation_button.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                
                # Get button info for logging
                button_text = await reservation_button.inner_text()
                button_onclick = await reservation_button.get_attribute('onclick')
                logger.info(f"Button text: {button_text}, onclick: {button_onclick[:100] if button_onclick else 'None'}")
                
                # Click the button
                async with page.expect_navigation(wait_until='networkidle', timeout=120000):
                    await reservation_button.click()
            except Exception as e:
                logger.error(f"Error clicking [予約] button: {e}")
                # Try alternative click method
                try:
                    logger.info("Trying alternative click method (JavaScript)...")
                    await reservation_button.evaluate('el => el.click()')
                    await page.wait_for_load_state('networkidle', timeout=120000)
                except Exception as e2:
                    logger.error(f"Alternative click also failed: {e2}")
                    raise
            
            await page.wait_for_load_state('networkidle', timeout=120000)
            await page.wait_for_timeout(2000)
            
            # Now we should be on terms agreement page (rsvWOpeReservedApplyAction.do)
            # Click agreement option and then [確認] button
            logger.info("Handling terms agreement page...")
            try:
                # Wait for terms agreement page elements
                await page.wait_for_selector('text=利用規約, text=利用規約に同意', timeout=30000)
                
                # Click "利用規約に同意する" (Agree to Terms of Use)
                logger.info("Clicking agreement option...")
                agreement_selectors = [
                    'input[value*="同意する"]',
                    'input[type="radio"][value="1"]',
                    'label:has-text("利用規約に同意する")',
                    'input[name*="agree"], input[name*="rule"]'
                ]
                agreement_clicked = False
                for selector in agreement_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            # If it's a label, click it; if it's an input, check it
                            tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                            if tag_name == 'label':
                                await page.click(selector)
                            else:
                                await page.check(selector)
                            await page.wait_for_timeout(500)
                            agreement_clicked = True
                            logger.info(f"Selected agreement using selector: {selector}")
                            break
                    except:
                        continue
                
                if not agreement_clicked:
                    logger.warning("Could not find agreement option, trying to proceed anyway")
                
                # Click [確認] (Confirm) button
                logger.info("Clicking [確認] button...")
                confirm_selectors = [
                    'button:has-text("確認")',
                    'input[type="submit"][value*="確認"]',
                    'button[type="submit"]:has-text("確認")',
                    '#btn-confirm, #btn-go'
                ]
                confirm_clicked = False
                for selector in confirm_selectors:
                    try:
                        await page.wait_for_selector(selector, state='visible', timeout=5000)
                        async with page.expect_navigation(wait_until='networkidle', timeout=120000):
                            await page.click(selector)
                        confirm_clicked = True
                        logger.info(f"Clicked [確認] using selector: {selector}")
                        break
                    except:
                        continue
                
                if not confirm_clicked:
                    raise Exception("Could not find [確認] button")
                
                await page.wait_for_load_state('networkidle', timeout=120000)
                await page.wait_for_timeout(2000)
                
            except Exception as e:
                logger.error(f"Error handling terms agreement page: {e}")
                raise
            
            # After clicking [確認] on terms page, we should be on confirmation/booking form
            # Fill confirmation form
            user_count_selector = 'input[name*="人数"], input[name*="applyNum"]'
            await page.wait_for_selector(user_count_selector, state='visible', timeout=60000)
            await page.fill(user_count_selector, '2')
            
            # Click final booking button and wait for navigation
            async with page.expect_navigation(wait_until='networkidle', timeout=120000):
                await page.click('button:has-text("予約")')
            
            # Extract reservation number
            reservation_number = await self._extract_reservation_number(page)
            
            if reservation_number:
                return {
                    'success': True,
                    'reservation_number': reservation_number,
                    'slot_data': slot_data
                }
            else:
                raise Exception("Could not extract reservation number")
                
        except Exception as e:
            logger.error(f"Booking error: {e}")
            # Take screenshot for debugging
            await page.screenshot(path=f"error_{slot_data.get('use_ymd', 'unknown')}.png")
            raise
        # Don't close the page if it's the main page - keep it alive to maintain session
        # Only close if it's a temporary page created just for booking
        finally:
            if self.main_page != page:
                try:
                    await page.close()
                except:
                    pass
                logger.info("Closed temporary booking page")
            else:
                logger.info("Keeping main page alive after booking")
    
    async def _is_on_week_one(self, page: Page) -> bool:
        """Check if calendar is currently on week 1.
        
        If today's date is included in the table, it is the first week.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if on week 1 (today's date is in table), False otherwise
        """
        try:
            from datetime import datetime
            
            # Get today's date in YYYYMMDD format
            today = datetime.now().strftime('%Y%m%d')
            today_int = int(today)
            
            logger.info(f"Checking if today's date ({today}) is in the calendar table to determine if on week 1...")
            
            # Wait for calendar table to be available
            try:
                await page.wait_for_selector('table#week-info', state='visible', timeout=5000)
            except:
                logger.warning("Calendar table not found - cannot determine week position")
                return False  # Assume not on week 1 if table not found
            
            # Find all cells in the calendar table
            # Cell IDs are in format: {YYYYMMDD}_{time_slot}
            # Example: "20260105_40"
            all_cells = await page.query_selector_all('table#week-info td[id]')
            
            if not all_cells:
                logger.warning("No cells with IDs found in calendar table")
                return False
            
            # Check if any cell ID starts with today's date
            for cell in all_cells:
                try:
                    cell_id = await cell.get_attribute('id')
                    if not cell_id:
                        continue
                    
                    # Cell ID format: {YYYYMMDD}_{time_slot}
                    if '_' not in cell_id:
                        continue
                    
                    date_str = cell_id.split('_')[0]
                    try:
                        cell_date = int(date_str)
                        if cell_date == today_int:
                            logger.info(f"Found today's date ({today}) in calendar table - this is week 1")
                            return True
                    except ValueError:
                        continue
                except:
                    continue
            
            # Today's date not found in table - we're NOT on week 1
            logger.info(f"Today's date ({today}) not found in calendar table - NOT on week 1")
            return False
            
        except Exception as e:
            logger.warning(f"Error checking if on week 1: {e}, assuming not on week 1")
            return False
    
    async def _navigate_back_to_week_one(self, page: Page) -> bool:
        """Navigate backwards to week 1 using '前週' (Previous Week) button.
        
        This is needed when switching courts, as the calendar may be on week 6
        from the previous court. We need to go backwards: week 6 → 5 → 4 → 3 → 2 → 1
        
        Args:
            page: Playwright page object
            
        Returns:
            True if successfully navigated to week 1, False otherwise
        """
        try:
            logger.info("Navigating backwards to week 1 using '前週' button...")
            
            # Maximum clicks needed: if we're on week 6, we need 5 clicks to get to week 1
            max_backward_clicks = 5
            
            for click_num in range(max_backward_clicks):
                # Find the "前週" (Previous Week) button
                # It's #last-week with onclick="getWeekInfoAjax(3, 0, 0)"
                prev_week_button = None
                prev_week_selectors = [
                    '#last-week',  # Primary selector
                    'button#last-week',
                    'button:has-text("前週")',
                    '[onclick*="getWeekInfoAjax"][onclick*="3"]',  # getWeekInfoAjax(3, 0, 0)
                    'button[onclick*="getWeekInfoAjax(3"]'
                ]
                
                for selector in prev_week_selectors:
                    try:
                        button = await page.query_selector(selector)
                        if button:
                            # Check if button is disabled
                            is_disabled = await button.get_attribute('disabled')
                            if is_disabled:
                                logger.info(f"'前週' button is disabled at click {click_num + 1} - likely at week 1")
                                return True  # We're probably at week 1
                            
                            # Check if button is visible
                            is_visible = await button.evaluate('el => window.getComputedStyle(el).display !== "none"')
                            if is_visible:
                                prev_week_button = button
                                break
                    except:
                        continue
                
                if not prev_week_button:
                    logger.info(f"'前週' button not found at click {click_num + 1} - likely at week 1")
                    return True  # Button not found means we're probably at week 1
                
                # Click the "前週" button
                try:
                    logger.info(f"Clicking '前週' button (click {click_num + 1} of up to {max_backward_clicks})...")
                    await prev_week_button.scroll_into_view_if_needed()
                    await page.wait_for_timeout(500)
                    await prev_week_button.click()
                    
                    # Wait for AJAX to complete
                    try:
                        loading_indicator = await page.query_selector('#loadingweek')
                        if loading_indicator:
                            await page.wait_for_function(
                                'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                                timeout=30000
                            )
                    except:
                        pass
                    
                    await page.wait_for_load_state('networkidle', timeout=30000)
                    await page.wait_for_timeout(2000)  # Wait for calendar to update
                    
                    # Verify calendar table is still visible
                    await page.wait_for_selector('table#week-info', state='visible', timeout=15000)
                    
                except Exception as e:
                    logger.warning(f"Error clicking '前週' button at click {click_num + 1}: {e}")
                    # Continue trying - might still be able to navigate
            
            logger.info("Finished navigating backwards - should be at week 1 now")
            return True
            
        except Exception as e:
            logger.warning(f"Error navigating backwards to week 1: {e}")
            return False
    
    async def _extract_slots_from_current_week(self, page: Page, week_num: int, click_slots: bool = True) -> tuple[List[Dict], int]:
        """Extract available slots from the current week.
        
        Args:
            page: Playwright page object
            week_num: Current week number (0-based, 0=week 1, 5=week 6)
            click_slots: If True, click on slots to select them. If False, only extract info without clicking.
            
        Returns:
            Tuple of (list of slot dictionaries from current week, flag)
            Flag: 1 if at least one slot was successfully clicked/selected, 0 otherwise
        """
        week_slots = []
        slot_clicked_flag = 0  # Flag: 1 if slot clicked, 0 if not
        
        try:
            # CRITICAL: Wait for AJAX loading to complete before looking for table
            logger.info("Waiting for AJAX loading to complete...")
            try:
                loading_indicator = await page.query_selector('#loadingweek')
                if loading_indicator:
                    await page.wait_for_function(
                        'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                        timeout=30000
                    )
                    logger.info("Loading indicator disappeared - AJAX loading complete")
            except Exception as e:
                logger.debug(f"Loading indicator check: {e} (might not exist, which is fine)")
            
            # Wait for network idle
            try:
                await page.wait_for_load_state('networkidle', timeout=30000)
            except:
                logger.warning("Network idle timeout - continuing anyway")
            
            # Wait for calendar table to be visible AND have content
            logger.info("Waiting for calendar table to be visible and populated...")
            table_found = False
            try:
                await page.wait_for_selector('table#week-info', state='visible', timeout=15000)
                await page.wait_for_function(
                    '''
                    () => {
                        const table = document.querySelector('table#week-info');
                        if (!table) return false;
                        const tbody = table.querySelector('tbody');
                        if (!tbody) return false;
                        const rows = tbody.querySelectorAll('tr');
                        return rows.length > 0;
                    }
                    ''',
                    timeout=10000
                )
                table_found = True
                logger.info("✓ Calendar table found and populated with content")
            except Exception as e:
                logger.warning(f"Calendar table not found or empty in week {week_num + 1}: {e}")
                return week_slots
            
            if not table_found:
                return week_slots
            
            # Find all available cells in current week
            available_cells = await page.query_selector_all('#weekly td.available, table.calendar td.available, table#week-info td.available')
            logger.info(f"Found {len(available_cells)} available cells in week {week_num + 1}")
            
            # Process each available cell
            for cell in available_cells:
                try:
                    cell_id = await cell.get_attribute('id')
                    if not cell_id:
                        continue
                    
                    # Parse cell ID: format is {YYYYMMDD}_{time_slot}
                    if '_' not in cell_id:
                        continue
                    
                    date_str, time_slot_str = cell_id.split('_', 1)
                    use_ymd = int(date_str)
                    time_slot = time_slot_str
                    
                    # Check if cell is already selected
                    data_selected = await cell.get_attribute('data-selected')
                    if data_selected == '1':
                        logger.debug(f"Cell {cell_id} already selected, skipping")
                        continue
                    
                    # Get onclick attribute to extract booking parameters
                    onclick = await cell.get_attribute('onclick')
                    if not onclick or 'setReserv' not in onclick:
                        logger.debug(f"Cell {cell_id} has no setReserv onclick, skipping")
                        continue
                    
                    # Parse setReserv parameters
                    import re
                    match = re.search(r'setReserv\([^,]+,\s*"(\d+)"\s*,\s*"(\d+)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', onclick)
                    if match:
                        bcd = match.group(1)
                        icd = match.group(2)
                        start_time = int(match.group(4))
                        end_time = int(match.group(5))
                        
                        # Get park and facility names from table caption
                        park_name = ""
                        facility_name = ""
                        try:
                            caption = await page.query_selector('table#week-info caption, table.calendar caption')
                            if caption:
                                caption_text = await caption.inner_text()
                                parts = caption_text.split()
                                if len(parts) >= 1:
                                    park_name = parts[0]
                                if len(parts) >= 2:
                                    facility_name = parts[1]
                        except:
                            pass
                        
                        # Click the cell to select it (only if click_slots is True)
                        if click_slots:
                            try:
                                await cell.scroll_into_view_if_needed()
                                await page.wait_for_timeout(200)
                                
                                selection_success = False
                                click_attempted = False
                                
                                # Method 1: Regular click
                                try:
                                    await cell.click()
                                    click_attempted = True
                                    await page.wait_for_timeout(500)  # Wait longer for attribute update
                                    
                                    # Check multiple ways to verify selection
                                    new_data_selected = await cell.get_attribute('data-selected')
                                    cell_class = await cell.get_attribute('class') or ''
                                    
                                    if new_data_selected == '1':
                                        selection_success = True
                                        logger.info(f"Cell {cell_id} selected successfully (method: regular click, data-selected=1)")
                                    elif 'selected' in cell_class.lower() or 'active' in cell_class.lower():
                                        selection_success = True
                                        logger.info(f"Cell {cell_id} selected successfully (method: regular click, class indicates selection)")
                                    else:
                                        # Even if verification fails, we clicked the cell - set flag to 1
                                        logger.info(f"Cell {cell_id} clicked but data-selected check failed (value: {new_data_selected}, class: {cell_class[:50]})")
                                except Exception as e:
                                    logger.debug(f"Method 1 (regular click) failed for cell {cell_id}: {e}")
                                    pass
                                
                                # Method 2: JavaScript click
                                if not selection_success:
                                    try:
                                        await cell.evaluate('el => el.click()')
                                        click_attempted = True
                                        await page.wait_for_timeout(500)
                                        
                                        new_data_selected = await cell.get_attribute('data-selected')
                                        cell_class = await cell.get_attribute('class') or ''
                                        
                                        if new_data_selected == '1':
                                            selection_success = True
                                            logger.info(f"Cell {cell_id} selected successfully (method: JS click, data-selected=1)")
                                        elif 'selected' in cell_class.lower() or 'active' in cell_class.lower():
                                            selection_success = True
                                            logger.info(f"Cell {cell_id} selected successfully (method: JS click, class indicates selection)")
                                        else:
                                            logger.info(f"Cell {cell_id} clicked via JS but data-selected check failed (value: {new_data_selected})")
                                    except Exception as e:
                                        logger.debug(f"Method 2 (JS click) failed for cell {cell_id}: {e}")
                                        pass
                                
                                # Method 3: Trigger onclick directly
                                if not selection_success and onclick:
                                    try:
                                        await cell.evaluate(f'() => {{ {onclick} }}')
                                        click_attempted = True
                                        await page.wait_for_timeout(500)
                                        
                                        new_data_selected = await cell.get_attribute('data-selected')
                                        cell_class = await cell.get_attribute('class') or ''
                                        
                                        if new_data_selected == '1':
                                            selection_success = True
                                            logger.info(f"Cell {cell_id} selected successfully (method: direct onclick, data-selected=1)")
                                        elif 'selected' in cell_class.lower() or 'active' in cell_class.lower():
                                            selection_success = True
                                            logger.info(f"Cell {cell_id} selected successfully (method: direct onclick, class indicates selection)")
                                        else:
                                            logger.info(f"Cell {cell_id} onclick triggered but data-selected check failed (value: {new_data_selected})")
                                    except Exception as e:
                                        logger.debug(f"Method 3 (direct onclick) failed for cell {cell_id}: {e}")
                                        pass
                                
                                # Set flag to 1 when a slot is clicked to check a reservation
                                # If we attempted to click (regardless of verification), set flag to 1
                                if click_attempted:
                                    slot_clicked_flag = 1
                                    if selection_success:
                                        logger.info(f"Slot clicked flag set to 1 (cell {cell_id} successfully selected and verified)")
                                    else:
                                        logger.info(f"Slot clicked flag set to 1 (cell {cell_id} clicked - verification may have failed but click was attempted)")
                                elif selection_success:
                                    # If somehow selection succeeded but click wasn't tracked, still set flag
                                    slot_clicked_flag = 1
                                    logger.info(f"Slot clicked flag set to 1 (cell {cell_id} selection verified)")
                                else:
                                    logger.warning(f"Slot click failed for cell {cell_id} - no click method succeeded, flag remains {slot_clicked_flag}")
                            except Exception as e:
                                logger.warning(f"Error clicking cell {cell_id}: {e}, but extracting slot info anyway")
                                # If we found an available cell, we should still try to set the flag
                                # The cell exists and is available, so we attempted to interact with it
                                logger.info(f"Slot click exception for cell {cell_id} - setting flag to 1 anyway (cell was found and available)")
                                slot_clicked_flag = 1
                        else:
                            logger.debug(f"Skipping click on cell {cell_id} (backward phase - extraction only)")
                        
                        # Create slot dictionary
                        slot = {
                            'use_ymd': use_ymd,
                            'bcd': bcd,
                            'icd': icd,
                            'bcd_name': park_name or f"Park {bcd}",
                            'icd_name': facility_name or f"Facility {icd}",
                            'start_time': start_time,
                            'end_time': end_time,
                            'start_time_display': f"{start_time//100:02d}:{start_time%100:02d}",
                            'end_time_display': f"{end_time//100:02d}:{end_time%100:02d}",
                            'pps_cd': '31000000',
                            'pps_cls_cd': '31011700',
                            'field_cnt': 0,
                            'week_flg': 0,
                            'holiday_flg': 0,
                            'cell_id': cell_id,
                            'time_slot': time_slot
                        }
                        week_slots.append(slot)
                except Exception as e:
                    logger.warning(f"Error processing cell: {e}")
                    continue
        
        except Exception as e:
            logger.warning(f"Error extracting slots from week {week_num + 1}: {e}")
        
        return week_slots, slot_clicked_flag
    
    async def _extract_slots_from_weekly_calendar(self, page: Page) -> tuple[List[Dict], int]:
        """Extract available slots from weekly calendar view (施設ごと).
        
        For each court: Extract forward through all 6 weeks (1→2→3→4→5→6),
        then extract backward through all 6 weeks (6→5→4→3→2→1).
        
        Args:
            page: Playwright page object
            
        Returns:
            Tuple of (list of slot dictionaries, flag)
            Flag: 1 if at least one slot was successfully clicked/selected during forward phase, 0 otherwise
        """
        slots = []
        max_weeks = 6  # Shinagawa limit for weekly navigation - always check all 6 weeks
        slots_clicked_flag = 0  # Flag: 1 if any slot was clicked, 0 if no slots found or clicked
        
        try:
            # Wait for weekly calendar container to be visible
            logger.info("Waiting for weekly calendar container (#weekly)...")
            await page.wait_for_selector('#weekly.calendar-area, #weekly', state='visible', timeout=30000)
            
            # Verify weekly calendar is expanded
            weekly_div = await page.query_selector('#weekly')
            if weekly_div:
                classes = await weekly_div.get_attribute('class') or ''
                if 'collapse' in classes and 'show' not in classes:
                    logger.info("Weekly calendar is collapsed - expanding...")
                    expand_button = await page.query_selector('#weekly button[data-toggle="collapse"]')
                    if expand_button:
                        await expand_button.click()
                        await page.wait_for_timeout(1000)
            
            # Always start from week 1
            is_on_week_one = await self._is_on_week_one(page)
            if not is_on_week_one:
                logger.info("Not on week 1 - navigating to week 1 first")
                await self._navigate_back_to_week_one(page)
            
            # PHASE 1: Extract forward through all 6 weeks (1→2→3→4→5→6)
            # During forward phase, click on slots to select them for booking
            logger.info("PHASE 1: Extracting forward through all 6 weeks (week 1→2→3→4→5→6) - CLICKING slots")
            for week_num in range(max_weeks):
                logger.info(f"PHASE 1 - Processing week {week_num + 1} of {max_weeks} (forward)...")
                
                # Extract slots from current week and click on them
                week_slots, week_flag = await self._extract_slots_from_current_week(page, week_num, click_slots=True)
                slots.extend(week_slots)
                # Update flag if any slot was clicked in this week
                if week_flag == 1:
                    slots_clicked_flag = 1
                logger.info(f"PHASE 1 - Extracted {len(week_slots)} slots from week {week_num + 1} (total so far: {len(slots)}, flag: {slots_clicked_flag})")
                
                # Navigate to next week (if not last week)
                if week_num < max_weeks - 1:
                    # Navigate forward using "翌週" (Next Week) button
                    logger.info(f"Looking for '翌週' (Next Week) button to navigate to week {week_num + 2}...")
                    next_week_button = None
                    
                    # Try multiple selectors for "翌週" button
                    # CRITICAL: Use #next-week as primary selector (most reliable)
                    next_week_selectors = [
                        '#next-week',  # Primary selector - most reliable
                        'button#next-week',
                        'button:has-text("翌週")',
                        'a:has-text("翌週")',
                        'button:has(span.btn-title-pc:has-text("翌週"))',
                        'button:has(span:has-text("翌週"))',
                        '[onclick*="getWeekInfoAjax"][onclick*="4"]',  # Specific onclick pattern
                        '[onclick*="next"]',
                        '[onclick*="week"]',
                        'button[title*="翌週"]',
                        'a[title*="翌週"]'
                    ]
                    
                    for selector in next_week_selectors:
                        try:
                            button = await page.query_selector(selector)
                            if button:
                                # Check if button is disabled
                                is_disabled = await button.get_attribute('disabled')
                                if is_disabled:
                                    logger.info("'翌週' button is disabled - no more weeks available")
                                    return slots  # Stop navigation
                                
                                # Check if button is visible
                                is_visible = await button.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                if is_visible:
                                    next_week_button = button
                                    break
                        except:
                            continue
                    
                    if next_week_button:
                        try:
                            logger.info(f"Clicking '翌週' button to navigate to week {week_num + 2}...")
                            # Scroll button into view before clicking
                            await next_week_button.scroll_into_view_if_needed()
                            await page.wait_for_timeout(500)
                            
                            # Click the button
                            await next_week_button.click()
                            
                            # Wait for AJAX to complete (same process as initial load)
                            logger.info("Waiting for next week's calendar to load via AJAX...")
                            try:
                                # Wait for loading indicator to disappear
                                loading_indicator = await page.query_selector('#loadingweek')
                                if loading_indicator:
                                    await page.wait_for_function(
                                        'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                                        timeout=30000
                                    )
                            except:
                                pass  # Loading indicator might not appear
                            
                            # Wait for network idle
                            await page.wait_for_load_state('networkidle', timeout=30000)
                            await page.wait_for_timeout(2000)  # Wait for calendar to update
                            
                            # Verify new week loaded by checking if calendar table updated
                            # Use specific selector to avoid matching month-info table
                            await page.wait_for_selector('table#week-info', state='visible', timeout=15000)
                            
                            # Verify table has content - use specific selector
                            await page.wait_for_function(
                                '''
                                () => {
                                    // Use specific ID selector to avoid matching month-info table
                                    const table = document.querySelector('table#week-info');
                                    if (!table) return false;
                                    const tbody = table.querySelector('tbody');
                                    if (!tbody) return false;
                                    const rows = tbody.querySelectorAll('tr');
                                    return rows.length > 0;
                                }
                                ''',
                                timeout=10000
                            )
                            logger.info(f"PHASE 1 - Successfully navigated to week {week_num + 2}")
                        except Exception as e:
                            logger.warning(f"Error clicking '翌週' button or loading next week: {e}")
                            break  # Stop navigation if button click fails
                    else:
                        logger.info("'翌週' button not found - no more weeks available")
                        break  # No more weeks
            
            logger.info(f"PHASE 1 COMPLETE: Extracted {len(slots)} total slots from forward navigation (weeks 1→2→3→4→5→6)")
            
            # PHASE 2: Extract backward through all 6 weeks (6→5→4→3→2→1)
            # During backward phase, DO NOT click on slots - only extract information
            # We should now be on week 6, so we'll go backwards
            logger.info("PHASE 2: Extracting backward through all 6 weeks (week 6→5→4→3→2→1) - NO CLICKING (extraction only)")
            for week_num in range(max_weeks - 1, -1, -1):  # Reverse: 5, 4, 3, 2, 1, 0 (weeks 6, 5, 4, 3, 2, 1)
                logger.info(f"PHASE 2 - Processing week {week_num + 1} of {max_weeks} (backward)...")
                
                # Extract slots from current week WITHOUT clicking
                week_slots, _ = await self._extract_slots_from_current_week(page, week_num, click_slots=False)
                slots.extend(week_slots)
                logger.info(f"PHASE 2 - Extracted {len(week_slots)} slots from week {week_num + 1} (total so far: {len(slots)})")
                
                # Navigate to previous week (if not week 1)
                if week_num > 0:
                    # Navigate backward using "前週" (Previous Week) button
                    logger.info(f"Looking for '前週' (Previous Week) button to navigate to week {week_num}...")
                    prev_week_button = None
                    
                    prev_week_selectors = [
                        '#last-week',  # Primary selector
                        'button#last-week',
                        'button:has-text("前週")',
                        '[onclick*="getWeekInfoAjax"][onclick*="3"]',  # getWeekInfoAjax(3, 0, 0)
                        'button[onclick*="getWeekInfoAjax(3"]'
                    ]
                    
                    for selector in prev_week_selectors:
                        try:
                            button = await page.query_selector(selector)
                            if button:
                                # Check if button is disabled (means we're at week 1)
                                is_disabled = await button.get_attribute('disabled')
                                if is_disabled:
                                    logger.info("'前週' button is disabled - reached week 1, stopping backward navigation")
                                    break  # Reached week 1, stop
                                
                                # Check if button is visible
                                is_visible = await button.evaluate('el => window.getComputedStyle(el).display !== "none"')
                                if is_visible:
                                    prev_week_button = button
                                    break
                        except:
                            continue
                    
                    if prev_week_button:
                        try:
                            logger.info(f"Clicking '前週' button to navigate to week {week_num}...")
                            await prev_week_button.scroll_into_view_if_needed()
                            await page.wait_for_timeout(500)
                            await prev_week_button.click()
                            
                            # Wait for AJAX to complete
                            logger.info("Waiting for previous week's calendar to load via AJAX...")
                            try:
                                loading_indicator = await page.query_selector('#loadingweek')
                                if loading_indicator:
                                    await page.wait_for_function(
                                        'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                                        timeout=30000
                                    )
                            except:
                                pass
                            
                            await page.wait_for_load_state('networkidle', timeout=30000)
                            await page.wait_for_timeout(2000)
                            
                            # Verify calendar table is still visible
                            await page.wait_for_selector('table#week-info', state='visible', timeout=15000)
                            await page.wait_for_function(
                                '''
                                () => {
                                    const table = document.querySelector('table#week-info');
                                    if (!table) return false;
                                    const tbody = table.querySelector('tbody');
                                    if (!tbody) return false;
                                    const rows = tbody.querySelectorAll('tr');
                                    return rows.length > 0;
                                }
                                ''',
                                timeout=10000
                            )
                            logger.info(f"PHASE 2 - Successfully navigated to week {week_num}")
                        except Exception as e:
                            logger.warning(f"Error clicking '前週' button or loading previous week: {e}")
                            break  # Stop navigation if button click fails
                    else:
                        logger.info("'前週' button not found - likely reached week 1, stopping backward navigation")
                        break  # No more weeks backwards
            
            logger.info(f"PHASE 2 COMPLETE: Extracted {len(slots)} total slots from both forward and backward navigation")
            logger.info(f"COMPLETED: Checked all {max_weeks} weeks forward (1→6) and backward (6→1) for this court")
            logger.info(f"Slots clicked flag: {slots_clicked_flag} (1=slots clicked, 0=no slots clicked)")
            
        except Exception as e:
            logger.error(f"Error extracting slots from weekly calendar: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return slots, slots_clicked_flag
    
    async def _extract_slots_from_page(self, page: Page) -> List[Dict]:
        """Extract available slot information from the results page.
        
        Args:
            page: Playwright page object
            
        Returns:
            List of slot dictionaries
        """
        slots = []
        try:
            # Find all table rows with reservation buttons
            # Row IDs follow pattern: {use_ymd}_{bcd}_{icd}_{start_time}_{index}
            reservation_rows = await page.query_selector_all('tr[id^="20"]')  # Rows with IDs starting with year
            
            for row in reservation_rows:
                try:
                    row_id = await row.get_attribute('id')
                    if not row_id or '_' not in row_id:
                        continue
                    
                    # Parse row ID: {use_ymd}_{bcd}_{icd}_{start_time}_{index}
                    parts = row_id.split('_')
                    if len(parts) < 4:
                        continue
                    
                    use_ymd = int(parts[0])  # e.g., 20260105
                    bcd = parts[1]  # e.g., 1020
                    icd = parts[2]  # e.g., 10200020
                    start_time = int(parts[3])  # e.g., 830
                    
                    # Get button onclick to extract more data
                    button = await row.query_selector('button:has-text("予約"), td.reservation button')
                    if not button:
                        continue
                    
                    onclick = await button.get_attribute('onclick')
                    if not onclick or 'doReserved' not in onclick:
                        continue
                    
                    # Parse onclick: doReserved(useYmd, bcd, icd, fieldCnt, startTime, endTime, ...)
                    # Example: doReserved(20260105,'1020','10200020',10,830,1630,31000000,31011700,'','',0,'10|20|30|40','830|1030|1230|1430','1030|1230|1430|1630');
                    import re
                    match = re.search(r"doReserved\((\d+),'(\d+)','(\d+)',(\d+),(\d+),(\d+),(\d+),(\d+)", onclick)
                    if match:
                        end_time = int(match.group(6))
                        field_cnt = int(match.group(4))
                        
                        # Only include available slots (fieldCnt = 0 means available)
                        if field_cnt == 0:
                            # Get park and facility names from table cells
                            park_name = ""
                            facility_name = ""
                            try:
                                park_cell = await row.query_selector('td.mansion')
                                if park_cell:
                                    park_name = await park_cell.inner_text()
                                    park_name = park_name.strip()
                                
                                facility_cell = await row.query_selector('td.facility')
                                if facility_cell:
                                    facility_name = await facility_cell.inner_text()
                                    facility_name = facility_name.strip()
                            except:
                                pass
                            
                            slot = {
                                'use_ymd': use_ymd,
                                'bcd': bcd,
                                'icd': icd,
                                'bcd_name': park_name or f"Park {bcd}",
                                'icd_name': facility_name or f"Facility {icd}",
                                'start_time': start_time,
                                'end_time': end_time,
                                'start_time_display': f"{start_time//100:02d}:{start_time%100:02d}",
                                'end_time_display': f"{end_time//100:02d}:{end_time%100:02d}",
                                'pps_cd': match.group(7),
                                'pps_cls_cd': match.group(8),
                                'field_cnt': field_cnt,
                                'week_flg': 0,
                                'holiday_flg': 0
                            }
                            slots.append(slot)
                except Exception as e:
                    logger.warning(f"Error extracting slot from row: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting slots from page: {e}")
        
        return slots
    
    async def _extract_reservation_number(self, page: Page) -> Optional[str]:
        """Extract reservation number from completion page."""
        try:
            # Try multiple selectors for reservation number
            selectors = [
                'text=予約番号',
                'text=予約番号:',
                '[class*="reservation"]',
                'td:has-text("予約番号") + td'
            ]
            
            for selector in selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        text = await element.text_content()
                        # Extract number from text
                        import re
                        numbers = re.findall(r'\d{10}', text or '')
                        if numbers:
                            return numbers[0]
                except:
                    continue
            
            # Fallback: extract from page content
            content = await page.content()
            import re
            numbers = re.findall(r'予約番号[：:]\s*(\d{10})', content)
            if numbers:
                return numbers[0]
                
            return None
        except Exception as e:
            logger.error(f"Error extracting reservation number: {e}")
            return None

