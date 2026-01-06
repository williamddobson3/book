"""Browser automation for booking operations - Componentized version."""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import Browser, BrowserContext, Page
from typing import Dict, Optional, List
import logging

from app.browser_session import BrowserSession
from app.login_handler import LoginHandler
from app.search_handler import SearchHandler
from app.slot_extractor import SlotExtractor
from app.booking_handler import BookingHandler
from app.config import settings
from app.status_tracker import status_tracker, LoginStatus

logger = logging.getLogger(__name__)


class BrowserAutomation:
    """Handles browser automation for booking - Componentized architecture."""
    
    def __init__(self):
        """Initialize browser automation with componentized architecture."""
        self.session = BrowserSession()
        self.login_handler: Optional[LoginHandler] = None
        self.search_handler: Optional[SearchHandler] = None
        self.slot_extractor = SlotExtractor()
        self.booking_handler = BookingHandler()
        self._main_page_ref = {'main_page': None}  # Use dict to allow reference updates
    
    # Backward compatibility properties
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
        self._main_page_ref['main_page'] = value
    
    async def start(self):
        """Start browser instance."""
        # Only start if browser is not already running
        if self.session.browser and self.session.browser.is_connected():
            logger.debug("Browser already running - skipping start")
            if self.session.context and not self.login_handler:
                self.login_handler = LoginHandler(self.session.context, self._main_page_ref)
                self.search_handler = SearchHandler(main_page=self.session.main_page)
            return
        
        await self.session.start()
        if self.session.context:
            self.login_handler = LoginHandler(self.session.context, self._main_page_ref)
            # Initialize search handler with main page reference
            self.search_handler = SearchHandler(main_page=self.session.main_page)
    
    async def stop(self):
        """Stop browser instance."""
        await self.session.stop()
    
    async def login(self) -> Dict[str, str]:
        """Login to the system and return cookies.
        
        Returns:
            Dictionary of cookies
        """
        if not self.session.context:
            await self.start()
        
        if not self.login_handler:
            self.login_handler = LoginHandler(self.session.context, self._main_page_ref)
        
        cookies = await self.login_handler.login()
        # Update session's main_page reference
        self.session.main_page = self._main_page_ref['main_page']
        # Update search handler with new main page
        if self.session.main_page:
            self.search_handler = SearchHandler(main_page=self.session.main_page)
        return cookies
    
    async def check_and_renew_login(self) -> bool:
        """Check if user is logged in, and re-login ONLY if already logged out.
        
        This method does NOT log out the user - it only checks status and re-logs in
        if the session has already expired or the user is already logged out.
        
        Returns:
            True if logged in (either already logged in or successfully re-logged in), False otherwise
        """
        try:
            if not self.login_handler:
                if not self.session.context:
                    await self.start()
                self.login_handler = LoginHandler(self.session.context, self._main_page_ref)
            
            # Check if we have a main page
            page = self.session.main_page
            if not page or page.is_closed():
                logger.warning("No valid page available - need to login")
                await self.login()
                status_tracker.set_login_status(LoginStatus.LOGGED_IN)
                return True
            
            # Check if currently logged in WITHOUT modifying the page state
            # This is a read-only check that doesn't navigate or close anything
            is_logged_in = await self.login_handler.is_logged_in(page)
            
            if is_logged_in:
                logger.debug("User is still logged in - no action needed")
                # Update status tracker to reflect logged in state
                status_tracker.set_login_status(LoginStatus.LOGGED_IN)
                return True
            
            # Double-check: Sometimes the login check can be incorrect immediately after login
            # Wait a moment and check again before closing the page
            import asyncio
            await asyncio.sleep(1)
            is_logged_in_retry = await self.login_handler.is_logged_in(page)
            
            if is_logged_in_retry:
                logger.debug("User is logged in (verified on retry) - no action needed")
                status_tracker.set_login_status(LoginStatus.LOGGED_IN)
                return True
            
            # Only re-login if we're actually logged out (session expired)
            # Do NOT log out - the user is already logged out
            logger.warning("Session expired or user already logged out - re-logging in...")
            status_tracker.add_activity_log("login", "Session expired - re-logging in...", {}, "warning")
            status_tracker.set_login_status(LoginStatus.NOT_LOGGED_IN)
            
            # Close the old page only if it exists and is not already closed
            # This is necessary because we need a fresh page for login
            try:
                if page and not page.is_closed():
                    logger.debug("Closing old page before re-login")
                    await page.close()
            except Exception as e:
                logger.debug(f"Error closing old page: {e}")
            
            # Re-login (creates new page)
            await self.login()
            status_tracker.set_login_status(LoginStatus.LOGGED_IN)
            status_tracker.add_activity_log("login", "Successfully re-logged in after session expiration")
            logger.info("Successfully re-logged in after session expiration")
            return True
                
        except Exception as e:
            logger.error(f"Error checking/renewing login: {e}")
            status_tracker.add_error(f"Login check/renewal failed: {str(e)}")
            return False
    
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
                        courts.append({'icd': value, 'name': text.strip()})
                        logger.info(
                            f"Found court: {text.strip()} (ICD: {value})")
            else:
                logger.warning(
                    "Facility dropdown not found - cannot get court list")
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
        """Search for availability by filling out the search form in the browser.
        
        This method properly fills out the form as required by the server:
        1. Selects "1 month" (1か月) date option
        2. Selects park name from dropdown
        3. Selects "テニス" (Tennis) activity
        4. Triggers search
        
        Args:
            area_code: Area code (e.g., "1200_1040")
            park_name: Optional park name for logging
            icd: Optional court ICD to select specific court
            click_reserve_button: If True, click "予約" button when slots are found.
                                 If False, only extract slots without clicking "予約".
                                 Default is True for backward compatibility.
            
        Returns:
            Search results dictionary with 'success', 'page', 'slots', and 'slots_clicked_flag'
        """
        if not self.session.context:
            await self.start()

        # Use main page if available (maintains session), otherwise create new page
        if self.session.main_page and not self.session.main_page.is_closed():
            page = self.session.main_page
            logger.info("Reusing main page to maintain session")
        else:
            page = await self.session.create_page()
            self.session.main_page = page
            self._main_page_ref['main_page'] = page
            logger.info("Created new page for search")
        
        # Initialize search handler if not already initialized
        if not self.search_handler:
            self.search_handler = SearchHandler(main_page=page)
        else:
            # Update search handler with current page
            self.search_handler.main_page = page
        
        # Delegate to search handler
        return await self.search_handler.search_availability_via_form(
            page, area_code, park_name, icd, click_reserve_button
        )
    
    async def click_reservation_button_if_slots_found(
            self, page: Page, slots_clicked_flag: int,
            slots: List[Dict]) -> bool:
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
        return await self.booking_handler.click_reservation_button_if_slots_found(
            page, slots_clicked_flag, slots
        )
    
    async def change_park_and_search(
            self,
            next_area_code: str,
            next_park_name: str = None) -> Dict:
        """Change park selection and search again when no results are found.
        
        This method clicks [条件変更] button to expand the search form,
        selects a different park, and searches again.
        
        Args:
            next_area_code: Area code for the next park to try
            next_park_name: Optional park name for logging
            
        Returns:
            Search result status
        """
        if not self.session.main_page or self.session.main_page.is_closed():
            raise Exception("Main page not available for changing park")
        
        if not self.search_handler:
            self.search_handler = SearchHandler(main_page=self.session.main_page)
        
        return await self.search_handler.change_park_and_search(
            self.session.main_page, next_area_code, next_park_name
        )
    
    async def book_slot(
            self,
            slot_data: Dict,
            try_next_park_on_no_results: bool = True) -> Dict:
        """Book a time slot.
        
        Args:
            slot_data: Slot information from API
            try_next_park_on_no_results: If True, try next park if no results found
            
        Returns:
            Reservation details including reservation number
        """
        if not self.session.context:
            await self.start()
        
        # Use main page if available (maintains session), otherwise create new page
        if self.session.main_page and not self.session.main_page.is_closed():
            page = self.session.main_page
            logger.info("Reusing main page for booking to maintain session")
        else:
            page = await self.session.create_page()
            logger.info("Created new page for booking")
        
        try:
            from app.form_utils import FormUtils
            from app.results_checker import ResultsChecker
            from app.config import settings
            
            # CRITICAL: First fill the search form on the current page (home page)
            # Do NOT navigate away - this will destroy the session
            current_url = page.url
            logger.info(f"Starting booking from current page: {current_url}")

            # If we're on the home page (index.jsp), fill the form there first
            if 'index.jsp' in current_url or 'UserAttestation' in current_url:
                logger.info(
                    "On home page - filling search form before navigating to date view"
                )
                area_code = slot_data.get('area_code', '1400_0')

                # Fill search form on home page
                try:
                    await FormUtils.select_date_option(page)
                    await FormUtils.select_park(page, area_code)
                    await FormUtils.select_activity(page)
                    await FormUtils.click_search_button(page)
                except Exception as e:
                    logger.warning(f"Error filling form on home page: {e}")
            else:
                # If we're already on date view page, just proceed
                logger.info(
                    "Already on date view page or different page - proceeding with booking"
                )
                # Navigate to date view only if we're not already there
                date_view_url = f"{settings.base_url}/rsvWOpeUnreservedDailyAction.do"
                if date_view_url not in current_url:
                    logger.warning(
                        "Not on date view page - navigating (this might affect session)"
                    )
                    await page.goto(date_view_url,
                                    wait_until='networkidle',
                                    timeout=120000)
                    await page.wait_for_load_state('networkidle', timeout=120000)

                    # Fill form on date view page if needed
                    area_code = slot_data.get('area_code', '1400_0')
                    await FormUtils.select_park(page, area_code)
                    await FormUtils.select_activity(page)
                    await FormUtils.select_date_option(page)
                    await FormUtils.click_search_button(page)

            # After search, ensure "施設ごと" tab is active
            if not self.search_handler:
                self.search_handler = SearchHandler(main_page=page)
            await self.search_handler._ensure_facility_tab_active(page)

            # Check if results are displayed
            logger.info("Checking if search was successful...")
            await page.wait_for_timeout(2000)  # Wait for results to render

            results_checker = ResultsChecker()
            has_results, has_reservation_buttons = await results_checker.check_results_available(page)

            # Handle no results case
            if not has_results and not has_reservation_buttons:
                logger.warning(
                    "Search failed - no results found. Clicking '条件変更' to select another park..."
                )
                if try_next_park_on_no_results:
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
                        logger.info(
                            f"No results for current park, trying next park: {next_park['name']}"
                        )
                        try:
                            # Change park and search again
                            await self.change_park_and_search(
                                next_area_code=next_park['area'],
                                next_park_name=next_park['name'])

                            # Wait for results to load
                            await page.wait_for_timeout(2000)

                            # Check for results again
                            has_results, has_reservation_buttons = await results_checker.check_results_available(page)

                            if not has_results and not has_reservation_buttons:
                                logger.warning(
                                    f"No results for {next_park['name']} either"
                                )
                                raise Exception(
                                    f"No available slots found for park {next_park['name']} - try next park"
                                )
                            
                            # Update slot_data with new park info
                            slot_data['area_code'] = next_park['area']
                            slot_data['bcd'] = next_park['bcd']
                            slot_data['bcd_name'] = next_park['name']
                            has_results = True
                        except Exception as e:
                            if "No available slots found" in str(e):
                                raise  # Re-raise to try next park
                            logger.error(f"Error changing park: {e}")
                            raise Exception(
                                f"No available slots found and failed to change park: {e}"
                            )
                    else:
                        # No more parks to try
                        park_display_name = slot_data.get(
                            'bcd_name') or slot_data.get('park_name') or 'unknown'
                        raise Exception(
                            f"No available slots found for park {park_display_name} - no more parks to try"
                        )
                else:
                    # Don't try next park, just raise exception
                    park_display_name = slot_data.get(
                        'bcd_name') or slot_data.get('park_name') or 'unknown'
                    raise Exception(
                        f"No available slots found for park {park_display_name} - try next park"
                    )

            # If results found, proceed to booking
            if has_results or has_reservation_buttons:
                logger.info(
                    "Results found - checking for 'さらに表示' (Show More) button to load all available dates..."
                )
                if not self.search_handler:
                    self.search_handler = SearchHandler(main_page=page)
                await self.search_handler._click_load_more_button(page)

            # Look for [予約] buttons in the results
            reservation_buttons = await page.query_selector_all(
                'button:has-text("予約"), a:has-text("予約")')

            # If no reservation buttons found, wait and try again
            if not reservation_buttons or len(reservation_buttons) == 0:
                logger.warning(
                    "No [予約] buttons found despite success message - may need to wait longer or check page state"
                )
                await page.wait_for_timeout(3000)
                reservation_buttons = await page.query_selector_all(
                    'button:has-text("予約"), a:has-text("予約")')

                if not reservation_buttons or len(reservation_buttons) == 0:
                    raise Exception(
                        "No [予約] buttons found on page - cannot proceed with booking"
                    )

            # Find the [予約] button that matches our slot
            time_str = str(slot_data['start_time']).zfill(4)
            use_ymd = str(slot_data['use_ymd'])
            bcd = str(slot_data.get('bcd', ''))
            icd = str(slot_data.get('icd', ''))

            logger.info(
                f"Looking for [予約] button for date {use_ymd}, time {time_str}, bcd {bcd}, icd {icd}..."
            )

            reservation_button = None

            # Strategy 1: Try to find button by row ID pattern
            if bcd and icd:
                try:
                    row_id_pattern = f"{use_ymd}_{bcd}_{icd}_{time_str}_"
                    logger.info(
                        f"Trying to find row with ID pattern: {row_id_pattern}*"
                    )

                    # Expand all date sections
                    try:
                        date_headers = await page.query_selector_all(
                            'h3[id^="20"] button, h3[id^="20"] a')
                        for header in date_headers:
                            try:
                                parent = await header.evaluate_handle(
                                    'el => el.closest("h3")')
                                if parent:
                                    next_sibling = await parent.evaluate_handle(
                                        'el => el.nextElementSibling')
                                    if next_sibling:
                                        classes = await next_sibling.get_attribute('class') or ''
                                        if 'collapse' in classes and 'show' not in classes:
                                            await header.click()
                                            await page.wait_for_timeout(500)
                            except:
                                continue
                    except Exception as e:
                        logger.warning(f"Error expanding date sections: {e}")

                    # Find all rows that match the pattern
                    all_rows = await page.query_selector_all('tr[id^="20"]')
                    logger.info(f"Found {len(all_rows)} rows with date IDs")

                    for row in all_rows:
                        row_id = await row.get_attribute('id')
                        if not row_id:
                            continue

                        if row_id.startswith(row_id_pattern):
                            button = await row.query_selector(
                                'button:has-text("予約"), td.reservation button, button.btn-go'
                            )
                            if button:
                                is_visible = await button.evaluate(
                                    'el => window.getComputedStyle(el).display !== "none"'
                                )
                                if is_visible:
                                    reservation_button = button
                                    logger.info(
                                        f"Found [予約] button in row {row_id}")
                                    break
                except Exception as e:
                    logger.warning(f"Error finding button by row ID: {e}")

            # Strategy 2: Find button by matching date and time in the same row
            if not reservation_button:
                try:
                    logger.info(
                        "Trying to find button by matching date and time in table rows..."
                    )
                    all_rows = await page.query_selector_all('tr[id^="20"]')
                    logger.info(
                        f"Checking {len(all_rows)} rows for date/time match..."
                    )

                    for row in all_rows:
                        try:
                            row_id = await row.get_attribute('id')
                            if not row_id:
                                continue

                            row_text = await row.inner_text()

                            # Check if row contains date pattern
                            date_match = (
                                str(use_ymd) in row_id
                                or f"{use_ymd[:4]}年" in row_text
                                or f"{use_ymd[4:6]}月" in row_text
                                or f"{use_ymd[6:8]}日" in row_text
                                or str(use_ymd) in row_text)

                            # Check if row contains the time
                            time_hour = int(time_str[:2])
                            time_min = int(time_str[2:])
                            time_match = (
                                time_str in row_id
                                or f"{time_hour}時{time_min}分" in row_text
                                or f"{time_hour:02d}時{time_min:02d}分" in row_text
                                or time_str in row_text)

                            if date_match and time_match:
                                logger.info(
                                    f"Found matching row by date/time: {row_id}"
                                )
                                button = await row.query_selector(
                                    'button:has-text("予約"), td.reservation button, button.btn-go'
                                )
                                if button:
                                    is_visible = await button.evaluate(
                                        'el => window.getComputedStyle(el).display !== "none"'
                                    )
                                    if is_visible:
                                        reservation_button = button
                                        logger.info(
                                            f"Found [予約] button by matching date/time in row {row_id}"
                                        )
                                        break
                        except Exception as e:
                            logger.warning(f"Error checking row: {e}")
                            continue
                except Exception as e:
                    logger.warning(f"Error finding button by date/time match: {e}")

            # Strategy 3: Click first available [予約] button if we can't find specific one
            if not reservation_button and reservation_buttons:
                logger.info(
                    f"Could not find specific slot, trying first available [予約] button from {len(reservation_buttons)} buttons..."
                )
                for btn in reservation_buttons:
                    try:
                        is_visible = await btn.evaluate(
                            'el => window.getComputedStyle(el).display !== "none"'
                        )
                        if is_visible:
                            reservation_button = btn
                            logger.info("Using first visible [予約] button")
                            break
                    except:
                        continue

                if not reservation_button:
                    reservation_button = reservation_buttons[0]
                    logger.info(
                        "Using first [予約] button (visibility check failed)")

            if not reservation_button:
                raise Exception(
                    f"No available slots found for park {slot_data.get('bcd_name', 'unknown')} - try next park"
                )

            # Click [予約] button - this will navigate to terms agreement page
            logger.info("Clicking [予約] button...")
            try:
                await reservation_button.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)

                button_text = await reservation_button.inner_text()
                button_onclick = await reservation_button.get_attribute('onclick')
                logger.info(
                    f"Button text: {button_text}, onclick: {button_onclick[:100] if button_onclick else 'None'}"
                )

                async with page.expect_navigation(wait_until='networkidle',
                                                  timeout=120000):
                    await reservation_button.click()
            except Exception as e:
                logger.error(f"Error clicking [予約] button: {e}")
                try:
                    logger.info("Trying alternative click method (JavaScript)...")
                    await reservation_button.evaluate('el => el.click()')
                    await page.wait_for_load_state('networkidle',
                                                   timeout=120000)
                except Exception as e2:
                    logger.error(f"Alternative click also failed: {e2}")
                    raise

            await page.wait_for_load_state('networkidle', timeout=120000)
            await page.wait_for_timeout(2000)

            # Handle Terms of Use page
            logger.info("Handling terms agreement page...")
            try:
                await page.wait_for_selector('text=利用規約, text=利用規約に同意',
                                             timeout=30000)

                # Click "利用規約に同意する"
                logger.info("Clicking agreement option...")
                agreement_selectors = [
                    'input[value*="同意する"]', 'input[type="radio"][value="1"]',
                    'label:has-text("利用規約に同意する")',
                    'input[name*="agree"], input[name*="rule"]'
                ]
                agreement_clicked = False
                for selector in agreement_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            tag_name = await element.evaluate(
                                'el => el.tagName.toLowerCase()')
                            if tag_name == 'label':
                                await page.click(selector)
                            else:
                                await page.check(selector)
                            await page.wait_for_timeout(500)
                            agreement_clicked = True
                            logger.info(
                                f"Selected agreement using selector: {selector}"
                            )
                            break
                    except:
                        continue

                if not agreement_clicked:
                    logger.warning(
                        "Could not find agreement option, trying to proceed anyway"
                    )

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
                        await page.wait_for_selector(selector,
                                                     state='visible',
                                                     timeout=5000)
                        async with page.expect_navigation(
                                wait_until='networkidle', timeout=120000):
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
            await page.wait_for_selector(user_count_selector,
                                         state='visible',
                                         timeout=60000)
            await page.fill(user_count_selector, '2')
            
            # Click final booking button and wait for navigation
            async with page.expect_navigation(wait_until='networkidle',
                                              timeout=120000):
                await page.click('button:has-text("予約")')
            
            # Extract reservation number
            reservation_number = await self.booking_handler.extract_reservation_number(page)
            
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
            try:
                await page.screenshot(
                    path=f"error_{slot_data.get('use_ymd', 'unknown')}.png")
            except:
                pass
            raise
        finally:
            # Don't close the page if it's the main page - keep it alive to maintain session
            # Only close if it's a temporary page created just for booking
            if self.session.main_page != page:
                try:
                    await page.close()
                except:
                    pass
                logger.info("Closed temporary booking page")
            else:
                logger.info("Keeping main page alive after booking")
    
    # Internal methods for backward compatibility (delegated to components)
    async def _is_on_week_one(self, page: Page) -> bool:
        """Check if calendar is currently on week 1.
        
        Delegated to CalendarNavigator for backward compatibility.
        """
        from app.calendar_navigator import CalendarNavigator
        return await CalendarNavigator.is_on_week_one(page)
    
    async def _navigate_back_to_week_one(self, page: Page) -> bool:
        """Navigate backwards to week 1 using '前週' (Previous Week) button.
        
        Delegated to CalendarNavigator for backward compatibility.
        """
        from app.calendar_navigator import CalendarNavigator
        return await CalendarNavigator.navigate_back_to_week_one(page)
    
    async def _extract_slots_from_weekly_calendar(
            self, page: Page) -> tuple[List[Dict], int]:
        """Extract available slots from weekly calendar view (施設ごと).
        
        Delegated to SlotExtractor for backward compatibility.
        """
        return await self.slot_extractor.extract_slots_from_weekly_calendar(page)
    
    async def _extract_slots_from_current_week(
            self,
            page: Page,
            week_num: int,
            click_slots: bool = True,
            previously_clicked_ids: List[str] = None) -> tuple[List[Dict], int, List[str]]:
        """Extract available slots from the current week.
        
        Delegated to SlotExtractor for backward compatibility.
        Returns tuple of (slots, flag, clicked_cell_ids).
        """
        return await self.slot_extractor.extract_slots_from_current_week(
            page, week_num, click_slots, previously_clicked_ids
        )
    
    async def _extract_slots_from_page(self, page: Page) -> List[Dict]:
        """Extract available slot information from the results page.
        
        Delegated to SlotExtractor for backward compatibility.
        """
        return await self.slot_extractor.extract_slots_from_page(page)
    
    async def _extract_reservation_number(self, page: Page) -> Optional[str]:
        """Extract reservation number from completion page.
        
        Delegated to BookingHandler for backward compatibility.
        """
        return await self.booking_handler.extract_reservation_number(page)
    
    async def _verify_cell_selection(
            self,
            page: Page,
            cell,
            cell_id: str,
            method_name: str) -> bool:
        """Comprehensive verification of cell selection state.
        
        Delegated to CellSelectionVerifier for backward compatibility.
        """
        from app.cell_selection_verifier import CellSelectionVerifier
        verifier = CellSelectionVerifier()
        return await verifier.verify_cell_selection(page, cell, cell_id, method_name)
