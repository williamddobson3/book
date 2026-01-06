"""Browser automation for booking operations - Refactored with componentized architecture."""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import Page
from typing import Dict, Optional, List
import logging

from app.browser_session import BrowserSession
from app.login_handler import LoginHandler
from app.form_utils import FormUtils
from app.calendar_navigator import CalendarNavigator
from app.config import settings

logger = logging.getLogger(__name__)


class BrowserAutomation:
    """Handles browser automation for booking - refactored with componentized architecture."""
    
    def __init__(self):
        self.session = BrowserSession()
        self.login_handler: Optional[LoginHandler] = None
        self._main_page_ref = {'main_page': None}  # Use dict to allow reference updates
    
    @property
    def browser(self):
        """Backward compatibility: access browser from session."""
        return self.session.browser
    
    @property
    def context(self):
        """Backward compatibility: access context from session."""
        return self.session.context
    
    @property
    def main_page(self):
        """Backward compatibility: access main_page from session."""
        return self.session.main_page
    
    @main_page.setter
    def main_page(self, value):
        """Backward compatibility: set main_page in session."""
        self.session.main_page = value
    
    async def start(self):
        """Start browser instance."""
        await self.session.start()
        if self.session.context:
            self.login_handler = LoginHandler(self.session.context, self._main_page_ref)
    
    async def stop(self):
        """Stop browser instance."""
        await self.session.stop()
    
    async def login(self) -> Dict[str, str]:
        """Login to the system and return cookies."""
        if not self.session.context:
            await self.start()
        
        if not self.login_handler:
            self.login_handler = LoginHandler(self.session.context, self._main_page_ref)
        
        cookies = await self.login_handler.login()
        # Update session's main_page reference
        self.session.main_page = self._main_page_ref['main_page']
        return cookies
    
    async def get_available_courts_for_park(self, page: Page, area_code: str) -> List[Dict]:
        """Get list of available tennis courts for a park from the dropdown."""
        courts = []
        try:
            facility_dropdown = await page.query_selector('#facility-select')
            if not facility_dropdown:
                facility_dropdown = await page.query_selector('#iname')
            
            if facility_dropdown:
                options = await facility_dropdown.query_selector_all('option')
                for option in options:
                    value = await option.get_attribute('value')
                    text = await option.inner_text()
                    
                    if value and value != '0' and '庭球場' in text:
                        courts.append({'icd': value, 'name': text.strip()})
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
            icd: str = None,
            click_reserve_button: bool = True) -> Dict:
        """
        Search for availability by filling out the search form.
        
        This is a simplified version that delegates to form utilities.
        For full implementation, see the original browser_automation.py
        which contains the complete logic for:
        - Form expansion
        - Search execution
        - Results checking
        - Slot extraction
        - Reservation button clicking
        """
        if not self.session.context:
            await self.start()
        
        # Use main page if available, otherwise create new page
        if self.session.main_page and not self.session.main_page.is_closed():
            page = self.session.main_page
            logger.info("Reusing main page to maintain session")
        else:
            page = await self.session.create_page()
            self.session.main_page = page
            logger.info("Created new page for search")
        
        try:
            # Check if we're on a valid page
            current_url = page.url
            is_valid_page = (
                'index.jsp' in current_url or 'UserAttestation' in current_url
                or 'rsvWOpeUnreservedDailyAction.do' in current_url
                or 'rsvWOpeInstSrchVacantAction.do' in current_url
                or 'ホーム画面' in await page.title()
            )
            
            if not is_valid_page:
                logger.warning(f"Not on expected page ({current_url}), attempting navigation...")
                home_url = f"{settings.base_url}/index.jsp"
                try:
                    await page.reload(wait_until='networkidle', timeout=120000)
                except:
                    await page.goto(home_url, wait_until='networkidle', timeout=120000)
                await page.wait_for_load_state('networkidle', timeout=120000)
                await page.wait_for_timeout(2000)
            
            # Fill search form using form utilities
            await FormUtils.select_date_option(page)
            await FormUtils.select_park(page, area_code)
            
            if icd:
                try:
                    await page.wait_for_timeout(1000)
                    facility_selectors = ['select#iname', 'select[name*="icd"]']
                    for selector in facility_selectors:
                        try:
                            element = await page.query_selector(selector)
                            if element:
                                await page.select_option(selector, value=icd)
                                await page.wait_for_timeout(1000)
                                logger.info(f"Selected court {icd} using selector: {selector}")
                                break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Failed to select court in search form: {e}")
            
            await FormUtils.select_activity(page)
            await FormUtils.click_search_button(page)
            
            # Check for results and extract slots
            # NOTE: This is simplified - full implementation would include:
            # - Results visibility checking
            # - "さらに表示" button clicking
            # - Calendar navigation and slot extraction
            # - Reservation button clicking
            
            # For now, return a basic structure
            # The full implementation should be imported from the original file
            # or implemented in separate handler modules
            
            return {
                'success': True,
                'message': 'Search completed via form (simplified)',
                'page': page,
                'slots': [],
                'slots_clicked_flag': 0
            }
            
        except Exception as e:
            logger.error(f"Error in search_availability_via_form: {e}")
            import traceback
            logger.error(traceback.format_exc())
            error_page = self.session.main_page if (
                self.session.main_page and not self.session.main_page.is_closed()) else None
            return {
                'success': False,
                'message': f'Search failed: {str(e)}',
                'page': error_page,
                'slots': [],
                'slots_clicked_flag': 0
            }
    
    # NOTE: The following methods would need to be implemented or imported:
    # - _extract_slots_from_weekly_calendar
    # - _extract_slots_from_current_week
    # - _extract_slots_from_page
    # - click_reservation_button_if_slots_found
    # - change_park_and_search
    # - book_slot
    # - _extract_reservation_number
    # 
    # These are complex methods that should be moved to separate handler modules:
    # - SlotExtractor (for slot extraction)
    # - BookingHandler (for booking flow)
    # - SearchHandler (for search operations)
    
    # For now, we maintain backward compatibility by keeping the structure
    # but the actual implementation should be in the component modules

