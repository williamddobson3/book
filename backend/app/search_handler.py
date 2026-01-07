"""Search handler for availability search operations."""
import logging
from typing import Dict, Optional, List
from playwright.async_api import Page

from app.form_utils import FormUtils
from app.results_checker import ResultsChecker
from app.slot_extractor import SlotExtractor
from app.booking_handler import BookingHandler
from app.calendar_navigator import CalendarNavigator
from app.config import settings

logger = logging.getLogger(__name__)


class SearchHandler:
    """Handles search operations for availability."""
    
    def __init__(self, main_page: Optional[Page] = None, slot_exists_checker=None):
        """Initialize search handler.
        
        Args:
            main_page: Main page to use for searches (maintains session)
            slot_exists_checker: Optional async callable that takes (use_ymd, bcd, icd, start_time) 
                                and returns bool indicating if slot exists in database.
                                If slot exists, it will be skipped (user cancelled it on site).
        """
        self.main_page = main_page
        self.results_checker = ResultsChecker()
        self.slot_extractor = SlotExtractor(slot_exists_checker=slot_exists_checker)
        self.booking_handler = BookingHandler()
    
    def set_slot_exists_checker(self, slot_exists_checker):
        """Update the slot existence checker for the slot extractor.
        
        Args:
            slot_exists_checker: Async callable that checks if slot exists in database.
        """
        self.slot_extractor.slot_exists_checker = slot_exists_checker
    
    async def search_availability_via_form(
            self,
            page: Page,
            area_code: str,
            park_name: str = None,
            icd: str = None,
            click_reserve_button: bool = True,
            skip_form_expansion: bool = False) -> Dict:
        """Search for availability by filling out the search form in the browser.
        
        This method properly fills out the form as required by the server:
        1. Selects "1 month" (1か月) date option
        2. Selects park name from dropdown
        3. Selects "テニス" (Tennis) activity
        4. Triggers search
        
        Args:
            page: Playwright page object
            area_code: Area code (e.g., "1200_1040")
            park_name: Optional park name for logging
            icd: Optional court ICD to select specific court
            click_reserve_button: If True, click "予約" button when slots are found.
                                 If False, only extract slots without clicking "予約".
                                 Default is True for backward compatibility.
            skip_form_expansion: If True, skip expanding the form (use when switching courts in same park).
                                If False, expand form when needed (use when switching parks).
                                Default is False for backward compatibility.
            
        Returns:
            Search results dictionary with 'success', 'page', 'slots', and 'slots_clicked_flag'
        """
        try:
            # CRITICAL: Do NOT navigate if we're already on a valid logged-in page
            # Navigating will destroy the session
            current_url = page.url
            logger.info(f"Current page URL: {current_url}")

            # Check if we're already on a page with the search form (home page or results page)
            # The search form is available on index.jsp, UserAttestation pages, or results page
            is_valid_page = (
                'index.jsp' in current_url or 'UserAttestation' in current_url
                or 'rsvWOpeUnreservedDailyAction.do' in current_url
                or 'rsvWOpeInstSrchVacantAction.do' in current_url
                or  # Facility-based search results page
                'ホーム画面' in await page.title())

            # Check if we're on the results page and just switching courts (same park)
            is_results_page = 'rsvWOpeInstSrchVacantAction.do' in current_url
            is_switching_courts_only = skip_form_expansion and icd and is_results_page
            
            if is_valid_page:
                logger.info(
                    "Already on valid logged-in page - checking if search form needs to be expanded..."
                )
                # Wait for page to be ready
                await page.wait_for_load_state('networkidle', timeout=30000)
                await page.wait_for_timeout(1000)

                # If we're switching courts within the same park, skip form expansion
                if is_switching_courts_only:
                    logger.info(
                        f"Skipping form expansion - switching court within same park (ICD: {icd})"
                    )
                    # Directly select court in results page dropdown
                    await self._select_court_in_results_page(page, icd)
                    # Skip form filling - go directly to slot extraction
                    # We'll handle the rest after this condition check
                elif 'rsvWOpeUnreservedDailyAction.do' in current_url or 'rsvWOpeInstSrchVacantAction.do' in current_url:
                    # Only expand form if we're switching parks (not just courts)
                    if not skip_form_expansion:
                        await self._expand_search_form_if_collapsed(page)
                    else:
                        logger.info("Skipping form expansion as requested")
            else:
                # Only navigate if we're on a completely different page (shouldn't happen after login)
                logger.warning(
                    f"Not on expected page ({current_url}), but navigating might destroy session. Attempting careful navigation..."
                )
                home_url = f"{settings.base_url}/index.jsp"
                # Use reload instead of goto to preserve session
                try:
                    await page.reload(wait_until='networkidle', timeout=120000)
                except:
                    # If reload fails, try goto as last resort
                    await page.goto(home_url,
                                    wait_until='networkidle',
                                    timeout=120000)
                await page.wait_for_load_state('networkidle', timeout=120000)
                await page.wait_for_timeout(2000)

            # If we're just switching courts within the same park, skip form filling
            if is_switching_courts_only:
                logger.info(
                    f"Court switching mode - skipping form filling, directly selecting court {icd} in results page"
                )
                # Court selection was already done above, now just proceed to slot extraction
                # Ensure "施設ごと" tab is active
                await self._ensure_facility_tab_active(page)
                
                # Check if results are available
                has_results, has_reservation_buttons = await self.results_checker.check_results_available(page)
                
                # Only check for "さらに表示" if there are results
                if has_results:
                    await self._click_load_more_button(page)
            else:
                # Normal flow: Fill search form using FormUtils
                await FormUtils.select_date_option(page)
                await FormUtils.select_park(page, area_code)
                
                if icd:
                    logger.info(f"Selecting specific court (ICD: {icd}) in search form...")
                    try:
                        await page.wait_for_timeout(1000)  # Wait for options to load
                        facility_selectors = [
                            'select#iname', 'select[name*="icd"]',
                            'select[name*="施設"]'
                        ]
                        facility_selected = False
                        for selector in facility_selectors:
                            try:
                                element = await page.query_selector(selector)
                                if element:
                                    await page.select_option(selector, value=icd)
                                    await page.wait_for_timeout(1000)
                                    facility_selected = True
                                    logger.info(
                                        f"Selected court {icd} using selector: {selector}"
                                    )
                                    break
                            except:
                                continue

                        if not facility_selected:
                            logger.warning(
                                f"Could not select court {icd} in search form - will try in results page"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to select court in search form: {e}, will try in results page"
                        )

                await FormUtils.select_activity(page)
                await FormUtils.click_search_button(page)

                # Ensure "施設ごと" (By Facility) tab is active - do NOT click "日付順"
                await self._ensure_facility_tab_active(page)

                # Check if results are available
                has_results, has_reservation_buttons = await self.results_checker.check_results_available(page)

                # Only check for "さらに表示" if there are results
                if has_results:
                    await self._click_load_more_button(page)

                # If icd was specified and not already handled, select the court in the results page before extracting slots
                if icd and not is_switching_courts_only:
                    await self._select_court_in_results_page(page, icd)

            # Extract available slots from weekly calendar view (施設ごと)
            slots = []
            slots_clicked_flag = 0
            logger.info(
                f"has_results check: {has_results} (will {'call' if has_results else 'skip'} _extract_slots_from_weekly_calendar)"
            )
            if has_results:
                # Navigate through weekly calendar and extract slots
                logger.info(
                    "Calling _extract_slots_from_weekly_calendar to navigate through weeks and click '翌週' button..."
                )
                slots, slots_clicked_flag = await self.slot_extractor.extract_slots_from_weekly_calendar(
                    page)
                logger.info(
                    f"Extracted {len(slots)} available slots from weekly calendar"
                )
                logger.info(
                    f"Slots clicked flag: {slots_clicked_flag} (1=slots clicked, 0=no slots clicked), type: {type(slots_clicked_flag)}"
                )

                # If flag is 1 (slots were clicked), click the "予約" button to proceed to reservation page
                # BUT ONLY if click_reserve_button is True (defer clicking if False to allow checking all courts)
                flag_value = int(
                    slots_clicked_flag) if slots_clicked_flag else 0
                logger.info(
                    f"Flag value after conversion: {flag_value}, comparison with 1: {flag_value == 1}"
                )
                logger.info(
                    f"About to check if flag_value == 1: {flag_value == 1}, click_reserve_button: {click_reserve_button}"
                )

                if flag_value == 1 and click_reserve_button:
                    logger.info(
                        f"✓ ENTERED if block: flag_value is 1 and click_reserve_button=True, will click '予約' button"
                    )
                    await self.booking_handler.click_reservation_button_if_slots_found(
                        page, slots_clicked_flag, slots)
                elif flag_value == 1 and not click_reserve_button:
                    logger.info(
                        f"Slots clicked flag is 1 but click_reserve_button=False - deferring '予約' click to after all courts are processed"
                    )
                else:
                    logger.info(
                        f"Slots clicked flag is 0 - no slots were clicked, skipping '予約' button click"
                    )
            else:
                # No results found
                logger.info(
                    "No results found - slots list is empty, slots_clicked_flag remains 0"
                )

            # Return success indicator with extracted slots and flag
            return {
                'success': True,
                'message': 'Search completed via form',
                'page': page,
                'slots': slots,
                'slots_clicked_flag': slots_clicked_flag
            }

        except Exception as e:
            logger.error(f"Error in search_availability_via_form: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Always return a dictionary even on error to prevent NoneType errors
            error_page = self.main_page if (
                self.main_page and not self.main_page.is_closed()) else None
            return {
                'success': False,
                'message': f'Search failed: {str(e)}',
                'page': error_page,
                'slots': [],
                'slots_clicked_flag': 0
            }

    async def _expand_search_form_if_collapsed(self, page: Page) -> bool:
        """Expand search form if it's collapsed.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if form was expanded or already expanded, False otherwise
        """
        try:
            # Check if #free-search-cond is collapsed
            form_element = await page.query_selector('#free-search-cond')
            if form_element:
                # Check if it has 'collapse' class and is not showing
                classes = await form_element.get_attribute('class') or ''
                is_visible = await form_element.evaluate(
                    'el => window.getComputedStyle(el).display !== "none"'
                )

                logger.info(
                    f"Form element state: classes='{classes}', is_visible={is_visible}"
                )

                # Check if form needs to be expanded
                needs_expansion = (('collapse' in classes
                                    and 'show' not in classes)
                                   or not is_visible)

                if needs_expansion:
                    logger.info(
                        "Search form is collapsed - clicking [条件変更] to expand it..."
                    )
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
                            logger.info(
                                f"Trying to find [条件変更] button with selector: {selector}"
                            )
                            button = await page.query_selector(selector)
                            if button:
                                # Check if button is visible
                                button_visible = await button.evaluate(
                                    'el => window.getComputedStyle(el).display !== "none"'
                                )
                                logger.info(
                                    f"Button found with selector {selector}, visible={button_visible}"
                                )
                                if button_visible:
                                    await button.click()
                                    # Wait for Bootstrap collapse animation
                                    await page.wait_for_timeout(1500)
                                    # Wait for form to be visible
                                    await page.wait_for_selector(
                                        '#free-search-cond.show, #bname',
                                        state='visible',
                                        timeout=5000)
                                    button_clicked = True
                                    logger.info(
                                        f"Expanded search form using selector: {selector}"
                                    )
                                    break
                        except Exception as e:
                            logger.warning(
                                f"Failed to click [条件変更] with selector {selector}: {e}"
                            )
                            continue

                    if not button_clicked:
                        logger.warning(
                            "Could not click [条件変更] button, form might already be expanded or button not found"
                        )
                else:
                    logger.info(
                        "Search form is already expanded - no need to click [条件変更]"
                    )
            else:
                logger.warning(
                    "#free-search-cond element not found - form might not exist on this page"
                )
            
            return True
        except Exception as e:
            logger.warning(
                f"Could not check/expand search form: {e}, continuing anyway"
            )
            import traceback
            logger.warning(traceback.format_exc())
            return False

    async def _ensure_facility_tab_active(self, page: Page) -> bool:
        """Ensure '施設ごと' (By Facility) tab is active.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if tab is active or was switched, False otherwise
        """
        try:
            logger.info("Ensuring '施設ごと' (By Facility) tab is active...")
            # Wait for tabs to be visible
            await page.wait_for_selector('#free-info-nav, .nav-tabs',
                                         state='visible',
                                         timeout=10000)

            # Check which tab is currently active
            active_tab = await page.query_selector(
                '#free-info-nav .nav-link.active, .nav-tabs .nav-link.active'
            )
            if active_tab:
                tab_text = await active_tab.inner_text()
                logger.info(f"Current active tab: {tab_text}")

                # If "日付順" is active, switch to "施設ごと"
                if "日付順" in tab_text:
                    logger.info(
                        "日付順 tab is active - switching to 施設ごと...")
                    facility_tab_selectors = [
                        'a:has-text("施設ごと")', 'a:has-text("施設別")',
                        '#free-info-nav a:first-child',
                        '.nav-tabs a:first-child'
                    ]
                    for selector in facility_tab_selectors:
                        try:
                            await page.click(selector)
                            await page.wait_for_load_state(
                                'networkidle', timeout=30000)
                            await page.wait_for_timeout(1000)
                            logger.info(
                                f"Switched to 施設ごと tab using selector: {selector}"
                            )
                            return True
                        except:
                            continue
                else:
                    logger.info(
                        "施設ごと tab is already active - maintaining this view"
                    )
                    return True
            else:
                logger.warning(
                    "Could not find active tab, assuming 施設ごと is default"
                )
                return True
        except Exception as e:
            logger.warning(
                f"Could not verify/switch tab: {e}, assuming 施設ごと is default"
            )
            return False

    async def _click_load_more_button(self, page: Page) -> int:
        """Click 'さらに表示' (Show More) button to load all available dates.
        
        Args:
            page: Playwright page object
            
        Returns:
            Number of times the button was clicked
        """
        logger.info(
            "Results found - checking for 'さらに表示' (Show More) button to load all available dates..."
        )
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
                            is_visible = await show_more_button.evaluate(
                                'el => window.getComputedStyle(el).display !== "none"'
                            )
                            if is_visible:
                                logger.info(
                                    f"Found 'さらに表示' button (click {load_more_clicks + 1}) - clicking to load more dates..."
                                )
                                await page.click(selector)
                                # Wait for additional results to load
                                await page.wait_for_load_state(
                                    'networkidle', timeout=60000)
                                await page.wait_for_timeout(2000)
                                load_more_clicks += 1
                                show_more_found = True
                                break
                    except:
                        continue

                if not show_more_found:
                    logger.info(
                        "No more 'さらに表示' button found - all dates loaded"
                    )
                    break
            except Exception as e:
                logger.warning(
                    f"Error clicking 'さらに表示' button: {e}")
                break

        if load_more_clicks > 0:
            logger.info(
                f"Loaded additional dates by clicking 'さらに表示' {load_more_clicks} time(s)"
            )
        
        return load_more_clicks

    async def _select_court_in_results_page(self, page: Page, icd: str) -> bool:
        """Select court in results page dropdown.
        
        Args:
            page: Playwright page object
            icd: Court ICD to select
            
        Returns:
            True if court was selected, False otherwise
        """
        try:
            logger.info(
                f"Selecting court (ICD: {icd}) in results page...")
            # Wait for facility dropdown in results page
            await page.wait_for_selector('#facility-select',
                                         state='visible',
                                         timeout=10000)
            await page.select_option('#facility-select', value=icd)
            await page.wait_for_timeout(2000)  # Wait for calendar to update

            # Wait for AJAX to reload calendar
            try:
                loading_indicator = await page.query_selector('#loadingweek')
                if loading_indicator:
                    await page.wait_for_function(
                        'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                        timeout=30000)
            except:
                pass

            await page.wait_for_load_state('networkidle',
                                           timeout=30000)
            await page.wait_for_timeout(2000)
            logger.info(
                f"Court {icd} selected in results page, calendar should be updated"
            )
            return True
        except Exception as e:
            logger.warning(
                f"Could not select court {icd} in results page: {e}, continuing with default court"
            )
            return False

    async def change_park_and_search(
            self,
            page: Page,
            next_area_code: str,
            next_park_name: str = None) -> Dict:
        """Change park selection and search again when no results are found.
        
        This method clicks [条件変更] button to expand the search form,
        selects a different park, and searches again.
        
        Args:
            page: Playwright page object
            next_area_code: Area code for the next park to try
            next_park_name: Optional park name for logging
            
        Returns:
            Search result status
        """
        if not page or page.is_closed():
            raise Exception("Page not available for changing park")

        logger.info(f"Changing park to: {next_park_name or next_area_code}")

        try:
            # Step 1: Click [条件変更] button to expand search form
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
                    await page.wait_for_selector(selector,
                                                 state='visible',
                                                 timeout=10000)
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
            logger.info("Waiting for search form to expand...")
            try:
                await page.wait_for_selector(
                    '#free-search-cond.show, #free-search-cond:not(.collapse)',
                    state='visible',
                    timeout=5000)
                logger.info("Search form expanded")
            except:
                # Form might already be visible or use different class
                try:
                    await page.wait_for_selector('#bname',
                                                 state='visible',
                                                 timeout=5000)
                    logger.info("Park dropdown is visible")
                except:
                    logger.warning(
                        "Could not confirm form expansion, continuing anyway")

            await page.wait_for_timeout(500)

            # Step 3: Select the new park in the dropdown (#bname)
            logger.info(
                f"Selecting new park: {next_park_name or next_area_code} (area_code: {next_area_code})..."
            )
            await FormUtils.select_park(page, next_area_code)

            # Step 4: Ensure "1か月" and "テニス" are still selected
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
                await page.select_option(
                    'select#purpose, select[name*="purpose"]',
                    value='31000000_31011700')
                await page.wait_for_timeout(500)
            except:
                logger.warning("Could not ensure activity is selected")

            # Step 5: Click search button (再検索)
            logger.info(
                "Clicking search button (再検索) to search with new park...")
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
                    await page.wait_for_selector(selector,
                                                 state='visible',
                                                 timeout=10000)
                    # Click and wait for navigation/results to load
                    async with page.expect_navigation(wait_until='networkidle',
                                                      timeout=120000):
                        await page.click(selector)
                    await page.wait_for_load_state('networkidle',
                                                   timeout=120000)
                    await page.wait_for_timeout(2000)
                    search_clicked = True
                    logger.info(
                        f"Clicked search (再検索) using selector: {selector}")
                    break
                except Exception as e:
                    logger.warning(
                        f"Failed to click search with {selector}: {e}")
                    continue

            if not search_clicked:
                raise Exception("Could not find search button (再検索)")

            # Step 6: Ensure "施設ごと" tab is active (do NOT click "日付順")
            await self._ensure_facility_tab_active(page)

            return {
                'success':
                True,
                'message':
                f'Park changed to {next_park_name or next_area_code} and searched'
            }

        except Exception as e:
            logger.error(f"Error changing park: {e}")
            raise

