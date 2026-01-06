"""Session recovery handler for handling session timeouts and errors."""
from playwright.async_api import Page
from typing import Optional
import logging
import asyncio
from app.config import settings

logger = logging.getLogger(__name__)


class SessionRecovery:
    """Handles session timeout recovery and automatic re-login."""
    
    @staticmethod
    async def is_session_timeout_page(page: Page) -> bool:
        """
        Check if the current page is a session timeout error page.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if session timeout error is detected, False otherwise
        """
        try:
            # Check page title and content for session timeout indicators
            title = await page.title()
            content = await page.content()
            current_url = page.url
            
            # Check for session timeout error indicators
            timeout_indicators = [
                'セッションタイムアウト',
                'セッションタイムアウトが発生しました',
                '再度、認証を行って下さい',
                'Session timeout',
                'session timeout'
            ]
            
            # Check if any timeout indicators are present
            has_timeout_message = any(indicator in content for indicator in timeout_indicators)
            
            # Also check URL patterns that might indicate errors
            is_error_url = 'error' in current_url.lower() or 'エラー' in current_url
            
            return has_timeout_message or is_error_url
            
        except Exception as e:
            logger.warning(f"Error checking for session timeout: {e}")
            return False
    
    @staticmethod
    async def click_home_button(page: Page) -> bool:
        """
        Click the Home button to return to the main page.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if Home button was clicked successfully, False otherwise
        """
        try:
            logger.info("Looking for Home button to return to main page...")
            
            # Try multiple selectors for the Home button
            home_selectors = [
                'button#btn-light:has-text("Home")',
                'button.btn.btn-light:has-text("Home")',
                'button.form-control.btn.btn-light:has-text("Home")',
                'button:has-text("ホームへ")',
                'button:has-text("Home")',
                'a:has-text("ホームへ")',
                'a:has-text("Home")',
                'button[onclick*="index.jsp"]',
                'button[onclick*="location.href"][onclick*="index.jsp"]'
            ]
            
            for selector in home_selectors:
                try:
                    home_button = await page.query_selector(selector)
                    if home_button:
                        is_visible = await home_button.evaluate(
                            'el => window.getComputedStyle(el).display !== "none"'
                        )
                        if is_visible:
                            logger.info(f"Found Home button with selector: {selector}")
                            await home_button.scroll_into_view_if_needed()
                            await page.wait_for_timeout(500)
                            await home_button.click()
                            await page.wait_for_load_state('networkidle', timeout=30000)
                            await page.wait_for_timeout(2000)
                            logger.info("Successfully clicked Home button - returned to main page")
                            return True
                except Exception as e:
                    logger.debug(f"Failed to click Home button with selector {selector}: {e}")
                    continue
            
            # Try JavaScript click as fallback
            try:
                await page.evaluate('''() => {
                    const buttons = Array.from(document.querySelectorAll('button, a'));
                    const homeButton = buttons.find(btn => 
                        btn.textContent.includes('Home') || 
                        btn.textContent.includes('ホームへ') ||
                        (btn.onclick && btn.onclick.toString().includes('index.jsp'))
                    );
                    if (homeButton) {
                        homeButton.click();
                        return true;
                    }
                    return false;
                }''')
                await page.wait_for_load_state('networkidle', timeout=30000)
                await page.wait_for_timeout(2000)
                logger.info("Successfully clicked Home button via JavaScript")
                return True
            except Exception as e:
                logger.debug(f"JavaScript Home button click failed: {e}")
            
            logger.warning("Could not find or click Home button")
            return False
            
        except Exception as e:
            logger.error(f"Error clicking Home button: {e}")
            return False
    
    @staticmethod
    async def recover_from_session_timeout(page: Page, login_handler) -> bool:
        """
        Recover from session timeout by clicking Home and attempting to re-login with retry.
        
        Args:
            page: Playwright page object
            login_handler: LoginHandler instance to use for re-login
            
        Returns:
            True if recovery was successful, False otherwise
        """
        try:
            logger.info("Detected session timeout - attempting recovery...")
            
            # Click Home button to return to main page
            home_clicked = await SessionRecovery.click_home_button(page)
            if not home_clicked:
                logger.warning("Could not click Home button, trying direct navigation...")
                # Try navigating to home page directly
                try:
                    home_url = f"{settings.base_url}/index.jsp"
                    await page.goto(home_url, wait_until='networkidle', timeout=120000)
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    logger.error(f"Failed to navigate to home page: {e}")
                    return False
            
            # Use ensure_logged_in_with_retry for automatic retry (never gives up)
            logger.info("Attempting to re-login after session timeout (will retry every 5 minutes if needed)...")
            success = await SessionRecovery.ensure_logged_in_with_retry(
                page=page,
                login_handler=login_handler,
                max_retries=0,  # Infinite retries - never give up
                retry_interval=300  # 5 minutes
            )
            
            if success:
                logger.info("Successfully re-logged in after session timeout")
            else:
                logger.error("Re-login failed - this should not happen with infinite retries")
            
            return success
                
        except Exception as e:
            logger.error(f"Error during session timeout recovery: {e}")
            return False
    
    @staticmethod
    async def ensure_logged_in_with_retry(page: Page, login_handler, max_retries: int = 0, retry_interval: int = 300) -> bool:
        """
        Ensure the user is logged in, with automatic retry if login fails.
        Never stops retrying (if max_retries=0) until login succeeds.
        
        Args:
            page: Playwright page object
            login_handler: LoginHandler instance to use for login
            max_retries: Maximum number of retries (0 = infinite retries, never give up)
            retry_interval: Time to wait between retries in seconds (default: 300 = 5 minutes)
            
        Returns:
            True if login was successful, False if max retries exceeded (unlikely with infinite retries)
        """
        attempt = 0
        
        while True:
            attempt += 1
            try:
                logger.info(f"Login attempt {attempt}...")
                
                # Check if we're on a session timeout page
                is_timeout = await SessionRecovery.is_session_timeout_page(page)
                if is_timeout:
                    logger.info("Session timeout detected - clicking Home button first...")
                    await SessionRecovery.click_home_button(page)
                    await asyncio.sleep(2)  # Wait for page to load
                
                # Check if we're already logged in
                try:
                    content = await page.content()
                    if 'ログアウト' in content or 'logout' in content.lower():
                        logger.info("Already logged in - no need to re-login")
                        return True
                except:
                    pass
                
                # Attempt login (this will navigate to home page and log in)
                cookies = await login_handler.login()
                logger.info(f"Login successful on attempt {attempt}")
                return True
                
            except Exception as e:
                logger.error(f"Login attempt {attempt} failed: {e}")
                
                # Check if we've exceeded max retries (if max_retries > 0)
                if max_retries > 0 and attempt >= max_retries:
                    logger.error(f"Max retries ({max_retries}) exceeded - giving up")
                    return False
                
                # Wait before retrying (default: 5 minutes)
                logger.info(f"Waiting {retry_interval} seconds before retry {attempt + 1}...")
                await asyncio.sleep(retry_interval)
                
                # Navigate to home page before retrying
                if page and not page.is_closed():
                    try:
                        home_url = f"{settings.base_url}/index.jsp"
                        await page.goto(home_url, wait_until='networkidle', timeout=120000)
                        await page.wait_for_timeout(2000)
                    except Exception as e:
                        logger.warning(f"Failed to navigate to home page before retry: {e}")

