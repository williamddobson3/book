"""Login handler for authentication."""
from playwright.async_api import Page, BrowserContext
from typing import Dict
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class LoginHandler:
    """Handles user login to the booking system."""
    
    def __init__(self, context: BrowserContext, main_page_ref):
        """
        Initialize login handler.
        
        Args:
            context: Browser context for creating pages
            main_page_ref: Reference to main_page that will be set after login
        """
        self.context = context
        self.main_page_ref = main_page_ref
    
    async def login(self) -> Dict[str, str]:
        """
        Login to the system and return cookies.
        
        Returns:
            Dictionary of cookies
        """
        page = await self.context.new_page()
        
        try:
            # Navigate to home page first to initialize session
            home_url = f"{settings.base_url}/index.jsp"
            logger.info(f"Navigating to home page first: {home_url}")
            await page.goto(home_url, wait_until='networkidle', timeout=120000)
            await page.wait_for_load_state('domcontentloaded', timeout=120000)
            await page.wait_for_load_state('networkidle', timeout=120000)
            await page.wait_for_timeout(2000)
            
            # Verify home page loaded correctly
            home_title = await page.title()
            home_content = await page.content()
            if 'エラー' in home_title or 'pawfa1000' in home_content:
                raise Exception(f"Home page returned error. Title: {home_title}")
            logger.info(f"Home page loaded successfully. Title: {home_title}")
            
            # Click login button from home page
            await self._click_login_button(page)
            
            # Wait for login form
            await self._wait_for_login_form(page)
            
            # Fill and submit login form
            await self._fill_login_form(page)
            
            # Verify login success
            cookies = await self._verify_login_success(page)
            
            # Set main page to maintain session
            self.main_page_ref['main_page'] = page
            logger.info(f"Keeping page alive at current URL: {page.url} - DO NOT navigate to avoid session destruction")
            
            return cookies
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            try:
                await page.screenshot(path='login_error.png')
            except:
                pass
            if self.main_page_ref.get('main_page') != page:
                await page.close()
            raise
    
    async def _click_login_button(self, page: Page):
        """Click login button from home page."""
        logger.info("Clicking login button from home page...")
        login_selectors = [
            'button:has-text("ログイン")', 'a:has-text("ログイン")',
            'input[value*="ログイン"]', '[onclick*="ログイン"]',
            '.btn:has-text("ログイン")', 'a[href*="UserLogin"]'
        ]
        
        login_button = None
        for selector in login_selectors:
            try:
                login_button = await page.wait_for_selector(
                    selector, state='visible', timeout=10000)
                if login_button:
                    logger.info(f"Found login button with selector: {selector}")
                    break
            except:
                continue
        
        if not login_button:
            html = await page.content()
            title = await page.title()
            logger.error(f"Could not find login button. Page title: {title}")
            with open('home_page_debug.html', 'w', encoding='utf-8') as f:
                f.write(html)
            raise Exception(
                "Could not find login button on home page. Check home_page_debug.html for page content."
            )
        
        # Click and wait for navigation
        login_url_pattern = f"{settings.base_url}/rsvWTransUserLoginAction.do"
        async with page.expect_navigation(wait_until='networkidle', timeout=120000):
            await login_button.click()
        
        await page.wait_for_load_state('networkidle', timeout=120000)
        await page.wait_for_timeout(2000)
        
        # Verify we're on login page
        current_url = page.url
        if login_url_pattern not in current_url:
            logger.warning(f"URL after click is not login page: {current_url}")
        
        logger.info("Successfully navigated to login page via button click")
        
        # Check for error page
        title = await page.title()
        page_content = await page.content()
        if 'エラー' in title or 'error' in title.lower() or 'pawfa1000' in page_content or 'システム異常' in page_content:
            logger.error("Received error page instead of login form after clicking login button")
            html = await page.content()
            with open('login_error_page.html', 'w', encoding='utf-8') as f:
                f.write(html)
            raise Exception(
                f"Server returned error page. This indicates missing session state or invalid navigation flow. Title: {title}, URL: {current_url}"
            )
    
    async def _wait_for_login_form(self, page: Page):
        """Wait for login form elements to be visible."""
        logger.info("Waiting for login form elements...")
        try:
            await page.wait_for_selector('#userId', state='visible', timeout=120000)
            await page.wait_for_selector('#password', state='visible', timeout=120000)
            await page.wait_for_selector('#btn-go', state='visible', timeout=120000)
            logger.info("Login form elements found")
        except Exception as e:
            html = await page.content()
            title = await page.title()
            url = page.url
            logger.error(f"Login form not found. Title: {title}, URL: {url}")
            logger.error(f"Error: {e}")
            with open('login_debug.html', 'w', encoding='utf-8') as f:
                f.write(html)
            raise Exception(f"Login form elements not found: {e}")
    
    async def _fill_login_form(self, page: Page):
        """Fill and submit login form."""
        logger.info("Filling login form...")
        await page.fill('#userId', settings.user_id, timeout=60000)
        await page.fill('#password', settings.password, timeout=60000)
        
        logger.info("Clicking login button...")
        async with page.expect_navigation(wait_until='networkidle', timeout=120000):
            await page.click('#btn-go', timeout=60000)
        
        await page.wait_for_load_state('networkidle', timeout=120000)
    
    async def is_logged_in(self, page: Page) -> bool:
        """Check if user is currently logged in by examining page content and URL.
        
        This is a READ-ONLY check that does NOT modify the page state.
        It does NOT navigate, close, or log out - it only reads the current state.
        
        Args:
            page: Playwright page object to check
            
        Returns:
            True if logged in, False otherwise
        """
        try:
            # Check if page is valid and not closed
            if page.is_closed():
                logger.warning("Page is closed - cannot check login status")
                return False
            
            # Read current page state WITHOUT modifying it
            current_url = page.url
            title = await page.title()
            page_content = await page.content()
            
            # Check for session timeout or error pages (user is already logged out)
            if 'セッションタイムアウト' in page_content or 'Session timeout' in page_content:
                logger.warning("Session timeout detected - user is logged out")
                return False
            
            # Check for explicit error pages
            if 'エラー' in title or 'error' in title.lower():
                # But check if it's a session error vs other error
                if 'セッション' in page_content or 'Session' in page_content:
                    logger.warning(f"Session error page detected: {title}")
                    return False
                # Other errors might not mean logged out - check further
            
            # Check for login indicators (positive signs of being logged in)
            has_logout = 'ログアウト' in page_content or 'logout' in page_content.lower()
            has_user_info = '様' in page_content or '有効期限' in page_content
            is_home_screen = 'ホーム画面' in title or 'ホーム' in title
            
            # Check URL patterns that indicate logged-in state
            url_success_patterns = [
                'UserAttestation',
                'index.jsp',
                'pawab2000',
                'rsvWOpe',
                'rsvWInst',
                'rsvWGet',
                'rsvWCredit'
            ]
            url_matches = any(pattern in current_url for pattern in url_success_patterns)
            
            # Check for login form (indicates NOT logged in)
            # But be careful - login button might appear even when logged in
            has_login_form = (
                '#userId' in page_content or 
                'id="userId"' in page_content or
                'name="userId"' in page_content
            )
            
            # Check if we're on a login page URL (be specific - only actual login pages, not post-login actions)
            # UserAttestationLoginAction is the POST action after login, NOT a login page
            is_login_page = (
                'TransUserLogin' in current_url or  # Actual login page
                'UserLogin' in current_url and 'Trans' in current_url  # Login form page
            )
            
            # User is logged in if:
            # 1. Has logout button/option (strongest indicator), OR
            # 2. URL matches success patterns AND (is home screen OR has logout), OR
            # 3. Has user info AND URL matches success patterns
            # AND we're NOT on a login page or login form
            is_logged_in = (
                (has_logout or
                 (url_matches and (is_home_screen or has_logout)) or
                 (has_user_info and url_matches))
                and not has_login_form
                and not is_login_page
            )
            
            if is_logged_in:
                logger.debug(f"Login check: Logged in (URL: {current_url}, Title: {title})")
            else:
                logger.info(f"Login check: NOT logged in (URL: {current_url}, Title: {title}, Has logout: {has_logout}, URL matches: {url_matches})")
            
            return is_logged_in
            
        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            # On error, assume not logged in to be safe (will trigger re-login)
            return False
    
    async def _verify_login_success(self, page: Page) -> Dict[str, str]:
        """Verify login was successful and return cookies."""
        current_url = page.url
        title = await page.title()
        logger.info(f"Current URL after login: {current_url}")
        logger.info(f"Page title after login: {title}")
        
        page_content = await page.content()
        has_logout = 'ログアウト' in page_content or 'logout' in page_content.lower()
        has_user_info = '様' in page_content or '有効期限' in page_content
        is_home_screen = 'ホーム画面' in title or 'ホーム' in title
        
        url_success_patterns = [
            'UserAttestation',
            'index.jsp',
            'pawab2000'
        ]
        
        url_matches = any(pattern in current_url for pattern in url_success_patterns)
        
        if (url_matches and (is_home_screen or has_logout)) or has_logout:
            cookies = await self.context.cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}
            logger.info("Login successful - detected home screen with user session")
            return cookie_dict
        else:
            html = await page.content()
            with open('login_failed_debug.html', 'w', encoding='utf-8') as f:
                f.write(html)
            raise Exception(
                f"Login failed - URL: {current_url}, Title: {title}, Has logout: {has_logout}, Has user info: {has_user_info}"
            )

