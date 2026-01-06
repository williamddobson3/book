"""Browser session management for Playwright automation."""
import sys
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Optional
import logging

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = logging.getLogger(__name__)


class BrowserSession:
    """Manages browser instance and session lifecycle."""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.playwright = None
        self.main_page: Optional[Page] = None
    
    async def start(self):
        """Start browser instance with realistic settings."""
        # Don't restart if browser is already running and connected
        if self.browser and self.browser.is_connected():
            logger.debug("Browser already running and connected - skipping start")
            return
        
        # If browser exists but is disconnected, clean it up first
        if self.browser and not self.browser.is_connected():
            logger.info("Browser exists but is disconnected - cleaning up before restart")
            try:
                await self.stop()
            except Exception as e:
                logger.debug(f"Error during cleanup: {e}")
        
        self.playwright = await async_playwright().start()
        # Use headful mode to pass browser checks and execute JS fully
        self.browser = await self.playwright.chromium.launch(
            headless=False,  # Headful mode for JS-heavy pages and browser checks
            args=[
                '--disable-blink-features=AutomationControlled',  # Hide automation
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ])
        # More realistic browser context with proper user-agent and settings
        self.context = await self.browser.new_context(
            viewport={
                'width': 1920,
                'height': 1080
            },
            user_agent=
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='ja-JP',
            timezone_id='Asia/Tokyo',
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=False,
        )
        # Add extra headers to look more like a real browser
        await self.context.set_extra_http_headers({
            'Accept':
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
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
        """Stop browser instance and clean up resources."""
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
    
    def get_or_create_page(self) -> Page:
        """Get main page or create new one if needed."""
        if self.main_page and not self.main_page.is_closed():
            return self.main_page
        if not self.context:
            raise RuntimeError("Browser context not initialized. Call start() first.")
        return None  # Will be created by caller
    
    async def create_page(self) -> Page:
        """Create a new page in the browser context."""
        if not self.context:
            await self.start()
        return await self.context.new_page()
    
    def set_main_page(self, page: Page):
        """Set the main page to maintain session."""
        self.main_page = page

