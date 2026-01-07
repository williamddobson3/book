"""Slot extraction utilities for calendar views."""
import logging
import re
from typing import List, Dict, Tuple
from playwright.async_api import Page

from app.cell_selection_verifier import CellSelectionVerifier
from app.calendar_navigator import CalendarNavigator

logger = logging.getLogger(__name__)


class SlotExtractor:
    """Extracts available slots from calendar views."""
    
    def __init__(self, slot_exists_checker=None):
        """
        Initialize SlotExtractor.
        
        Args:
            slot_exists_checker: Optional async callable that takes (use_ymd, bcd, icd, start_time) 
                                and returns bool indicating if slot exists in database.
                                If slot exists, it will be skipped (user cancelled it on site).
        """
        self.verifier = CellSelectionVerifier()
        self.slot_exists_checker = slot_exists_checker
    
    async def extract_slots_from_current_week(
            self,
            page: Page,
            week_num: int,
            click_slots: bool = True,
            previously_clicked_ids: List[str] = None) -> Tuple[List[Dict], int, List[str]]:
        """Extract available slots from the current week.
        
        Args:
            page: Playwright page object
            week_num: Current week number (0-based, 0=week 1, 5=week 6)
            click_slots: If True, click on slots to select them. If False, only extract info without clicking.
            previously_clicked_ids: List of cell IDs that were clicked in PHASE 1 (for PHASE 2 restoration)
            
        Returns:
            Tuple of (list of slot dictionaries from current week, flag, list of clicked cell IDs)
            Flag: 1 if at least one slot was successfully clicked/selected, 0 otherwise
            List of cell IDs that were successfully clicked in this week
        """
        week_slots = []
        slot_clicked_flag = 0  # Flag: 1 if slot clicked, 0 if not
        clicked_cell_ids = []  # Track which cell IDs were successfully clicked
        if previously_clicked_ids is None:
            previously_clicked_ids = []

        try:
            # CRITICAL: Wait for AJAX loading to complete before looking for table
            logger.info("Waiting for AJAX loading to complete...")
            try:
                loading_indicator = await page.query_selector('#loadingweek')
                if loading_indicator:
                    await page.wait_for_function(
                        'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                        timeout=30000)
                    logger.info(
                        "Loading indicator disappeared - AJAX loading complete"
                    )
            except Exception as e:
                logger.debug(
                    f"Loading indicator check: {e} (might not exist, which is fine)"
                )

            # Wait for network idle
            try:
                await page.wait_for_load_state('networkidle', timeout=30000)
            except:
                logger.warning("Network idle timeout - continuing anyway")

            # Wait for calendar table to be visible AND have content
            logger.info(
                "Waiting for calendar table to be visible and populated...")
            table_found = False
            try:
                await page.wait_for_selector('table#week-info',
                                             state='visible',
                                             timeout=15000)
                await page.wait_for_function('''
                    () => {
                        const table = document.querySelector('table#week-info');
                        if (!table) return false;
                        const tbody = table.querySelector('tbody');
                        if (!tbody) return false;
                        const rows = tbody.querySelectorAll('tr');
                        return rows.length > 0;
                    }
                    ''',
                                             timeout=10000)
                table_found = True
                logger.info(
                    "✓ Calendar table found and populated with content")
            except Exception as e:
                logger.warning(
                    f"Calendar table not found or empty in week {week_num + 1}: {e}"
                )
                return week_slots, slot_clicked_flag

            if not table_found:
                return week_slots, slot_clicked_flag

            # Find all available cells in current week
            available_cells = await page.query_selector_all(
                '#weekly td.available, table.calendar td.available, table#week-info td.available'
            )
            logger.info(
                f"Found {len(available_cells)} available cells in week {week_num + 1}"
            )

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

                    # Check if cell is already selected by looking for the calendar SVG image
                    # If calendar_available_outline.svg is present, the slot is NOT selected (empty/available)
                    # If it's NOT present, the slot IS selected
                    has_available_outline = await cell.query_selector('img[src*="calendar_available_outline.svg"]') is not None
                    is_already_selected = not has_available_outline
                    
                    # In PHASE 2 (backward), check if this slot was clicked in PHASE 1 but is now unchecked
                    if not click_slots and cell_id in previously_clicked_ids and not is_already_selected:
                        # This slot was clicked in PHASE 1 but is now unchecked - re-click it
                        # CRITICAL: Double-check that slot is still not selected before clicking
                        # (Calendar uses toggle behavior - clicking selected slot unselects it)
                        # Check for calendar_available_outline.svg image - if present, slot is NOT selected
                        await page.wait_for_timeout(100)  # Small delay to ensure DOM is stable
                        
                        # Re-check the cell for the available outline image
                        cell_double_check = await page.query_selector(f'[id="{cell_id}"]')
                        if cell_double_check:
                            has_available_outline_double = await cell_double_check.query_selector('img[src*="calendar_available_outline.svg"]') is not None
                            if not has_available_outline_double:
                                logger.debug(f"Slot {cell_id} is already selected (no calendar_available_outline.svg found) - skipping click to avoid toggle")
                                is_already_selected = True
                            else:
                                logger.info(f"Slot {cell_id} was clicked in PHASE 1 but is now unchecked - re-clicking to restore selection")
                            try:
                                await cell.scroll_into_view_if_needed()
                                await page.wait_for_timeout(200)
                                
                                # Final check right before clicking - check for calendar_available_outline.svg
                                # If the image is NOT present, the slot is already selected - don't click
                                final_cell_check = await page.query_selector(f'[id="{cell_id}"]')
                                if final_cell_check:
                                    has_available_outline_final = await final_cell_check.query_selector('img[src*="calendar_available_outline.svg"]') is not None
                                    if not has_available_outline_final:
                                        logger.debug(f"Slot {cell_id} became selected just before click (no calendar_available_outline.svg) - skipping to avoid toggle")
                                        is_already_selected = True
                                    else:
                                        await cell.click()
                                        await page.wait_for_timeout(500)
                                        # Verify selection was restored - check that calendar_available_outline.svg is gone
                                        verification_cell = await page.query_selector(f'[id="{cell_id}"]')
                                        if verification_cell:
                                            has_available_outline_after = await verification_cell.query_selector('img[src*="calendar_available_outline.svg"]') is not None
                                            if not has_available_outline_after:
                                                logger.info(f"✓ Successfully restored selection for {cell_id} (calendar_available_outline.svg removed)")
                                                clicked_cell_ids.append(cell_id)
                                                slot_clicked_flag = 1
                                                # Update is_already_selected flag after re-click
                                                is_already_selected = True
                                            else:
                                                logger.warning(f"Failed to restore selection for {cell_id} - calendar_available_outline.svg still present after click")
                                        else:
                                            logger.warning(f"Could not verify selection for {cell_id} - cell not found after click")
                                else:
                                    logger.warning(f"Could not perform final check for {cell_id} - cell not found")
                            except Exception as e:
                                logger.warning(f"Error re-clicking cell {cell_id} to restore selection: {e}")
                    
                    if is_already_selected:
                        logger.debug(
                            f"Cell {cell_id} already selected")
                        # Still add to clicked_cell_ids if it was previously clicked
                        if cell_id in previously_clicked_ids:
                            clicked_cell_ids.append(cell_id)
                        # In PHASE 1, skip clicking already selected slots
                        # In PHASE 2, we still want to extract slot info even if selected
                        if click_slots:
                            continue  # Skip clicking in PHASE 1 if already selected
                        # In PHASE 2, continue to extract slot info below

                    # Get onclick attribute to extract booking parameters
                    onclick = await cell.get_attribute('onclick')
                    if not onclick or 'setReserv' not in onclick:
                        logger.debug(
                            f"Cell {cell_id} has no setReserv onclick, skipping"
                        )
                        continue

                    # Parse setReserv parameters
                    match = re.search(
                        r'setReserv\([^,]+,\s*"(\d+)"\s*,\s*"(\d+)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)',
                        onclick)
                    if match:
                        bcd = match.group(1)
                        icd = match.group(2)
                        start_time = int(match.group(4))
                        end_time = int(match.group(5))

                        # Check if slot already exists in database (user cancelled it on site)
                        # If it exists, skip clicking/extracting this slot
                        if self.slot_exists_checker:
                            try:
                                slot_exists = await self.slot_exists_checker(use_ymd, bcd, icd, start_time)
                                if slot_exists:
                                    logger.info(
                                        f"Skipping slot {cell_id} (use_ymd={use_ymd}, bcd={bcd}, icd={icd}, start_time={start_time}) - "
                                        f"already exists in database (user cancelled it on site)"
                                    )
                                    continue  # Skip this slot - user already cancelled it
                            except Exception as e:
                                logger.warning(
                                    f"Error checking if slot exists in database: {e}, continuing with slot extraction"
                                )
                                # Continue processing if check fails

                        # Get park and facility names from table caption
                        park_name = ""
                        facility_name = ""
                        try:
                            caption = await page.query_selector(
                                'table#week-info caption, table.calendar caption'
                            )
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

                                # Set up JavaScript error tracking before clicking
                                await page.evaluate('''() => {
                                    if (!window.jsErrors) {
                                        window.jsErrors = [];
                                    }
                                    const originalError = window.onerror;
                                    window.onerror = function(msg, url, line, col, error) {
                                        window.jsErrors.push({
                                            message: msg,
                                            url: url,
                                            line: line,
                                            col: col,
                                            error: error ? error.toString() : null
                                        });
                                        if (originalError) {
                                            return originalError.apply(this, arguments);
                                        }
                                        return false;
                                    };
                                }''')

                                # Method 1: Regular click
                                try:
                                    await cell.click()
                                    click_attempted = True
                                    await page.wait_for_timeout(500)

                                    # Use comprehensive verification
                                    selection_success = await self.verifier.verify_cell_selection(
                                        page, cell, cell_id, "regular click"
                                    )
                                    
                                    if not selection_success:
                                        logger.debug(
                                            f"Cell {cell_id} clicked (regular) but verification failed - will try alternative methods"
                                        )
                                except Exception as e:
                                    logger.debug(
                                        f"Method 1 (regular click) failed for cell {cell_id}: {e}"
                                    )
                                    pass

                                # Method 2: JavaScript click
                                if not selection_success:
                                    try:
                                        await cell.evaluate('el => el.click()')
                                        click_attempted = True
                                        await page.wait_for_timeout(500)

                                        # Use comprehensive verification
                                        selection_success = await self.verifier.verify_cell_selection(
                                            page, cell, cell_id, "JS click"
                                        )
                                        
                                        if not selection_success:
                                            logger.debug(
                                                f"Cell {cell_id} clicked (JS) but verification failed - will try onclick method"
                                            )
                                    except Exception as e:
                                        logger.debug(
                                            f"Method 2 (JS click) failed for cell {cell_id}: {e}"
                                        )
                                        pass

                                # Method 3: Trigger onclick directly
                                if not selection_success and onclick:
                                    try:
                                        await cell.evaluate(
                                            f'() => {{ {onclick} }}')
                                        click_attempted = True
                                        await page.wait_for_timeout(500)

                                        # Use comprehensive verification
                                        selection_success = await self.verifier.verify_cell_selection(
                                            page, cell, cell_id, "direct onclick"
                                        )
                                        
                                        if not selection_success:
                                            logger.debug(
                                                f"Cell {cell_id} onclick triggered but verification failed"
                                            )
                                    except Exception as e:
                                        logger.debug(
                                            f"Method 3 (direct onclick) failed for cell {cell_id}: {e}"
                                        )
                                        pass

                                # Check for JavaScript errors after all click attempts
                                js_errors = await page.evaluate('''() => {
                                    const errors = window.jsErrors || [];
                                    window.jsErrors = []; // Clear for next cell
                                    return errors;
                                }''')
                                if js_errors:
                                    logger.warning(
                                        f"JavaScript errors occurred while clicking {cell_id}: {js_errors}"
                                    )

                                # Verify selection using SVG image check (primary method)
                                # If calendar_available_outline.svg is NOT present, slot is selected
                                svg_verification = False
                                try:
                                    verification_cell = await page.query_selector(f'[id="{cell_id}"]')
                                    if verification_cell:
                                        has_available_outline = await verification_cell.query_selector('img[src*="calendar_available_outline.svg"]') is not None
                                        svg_verification = not has_available_outline  # Selected if outline is NOT present
                                        if svg_verification:
                                            logger.debug(f"✓ SVG verification: {cell_id} is selected (calendar_available_outline.svg removed)")
                                        else:
                                            logger.debug(f"SVG verification: {cell_id} is NOT selected (calendar_available_outline.svg still present)")
                                except Exception as e:
                                    logger.debug(f"Could not perform SVG verification for {cell_id}: {e}")

                                # Use SVG verification as primary, fallback to comprehensive verification
                                final_selection_success = svg_verification or selection_success

                                # Set flag to 1 when a slot is clicked to check a reservation
                                # If we attempted to click (regardless of verification), set flag to 1
                                if click_attempted:
                                    slot_clicked_flag = 1
                                    if final_selection_success:
                                        clicked_cell_ids.append(cell_id)  # Track successfully clicked cell
                                        logger.info(
                                            f"✓ Slot clicked flag set to 1 (cell {cell_id} successfully selected - SVG check: {svg_verification}, comprehensive: {selection_success})"
                                        )
                                    else:
                                        clicked_cell_ids.append(cell_id)  # Track even if verification inconclusive
                                        logger.info(
                                            f"Slot clicked flag set to 1 (cell {cell_id} clicked - verification inconclusive but click was attempted)"
                                        )
                                elif final_selection_success:
                                    # If somehow selection succeeded but click wasn't tracked, still set flag
                                    slot_clicked_flag = 1
                                    clicked_cell_ids.append(cell_id)  # Track successfully selected cell
                                    logger.info(
                                        f"✓ Slot clicked flag set to 1 (cell {cell_id} selection verified - SVG check: {svg_verification})"
                                    )
                                else:
                                    logger.warning(
                                        f"Slot click failed for cell {cell_id} - no click method succeeded, flag remains {slot_clicked_flag}"
                                    )
                            except Exception as e:
                                logger.warning(
                                    f"Error clicking cell {cell_id}: {e}, but extracting slot info anyway"
                                )
                                import traceback
                                logger.debug(traceback.format_exc())
                                # If we found an available cell, we should still try to set the flag
                                # The cell exists and is available, so we attempted to interact with it
                                logger.info(
                                    f"Slot click exception for cell {cell_id} - setting flag to 1 anyway (cell was found and available)"
                                )
                                slot_clicked_flag = 1
                                clicked_cell_ids.append(cell_id)  # Track even if exception occurred
                        else:
                            logger.debug(
                                f"Skipping click on cell {cell_id} (backward phase - extraction only)"
                            )

                        # Create slot dictionary
                        slot = {
                            'use_ymd': use_ymd,
                            'bcd': bcd,
                            'icd': icd,
                            'bcd_name': park_name or f"Park {bcd}",
                            'icd_name': facility_name or f"Facility {icd}",
                            'start_time': start_time,
                            'end_time': end_time,
                            'start_time_display':
                            f"{start_time//100:02d}:{start_time%100:02d}",
                            'end_time_display':
                            f"{end_time//100:02d}:{end_time%100:02d}",
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
            logger.warning(
                f"Error extracting slots from week {week_num + 1}: {e}")

        return week_slots, slot_clicked_flag, clicked_cell_ids

    async def extract_slots_from_weekly_calendar(
            self, page: Page, browser_automation=None) -> Tuple[List[Dict], int]:
        """Extract available slots from weekly calendar view (施設ごと).
        
        For each court: Extract forward through all 6 weeks (1→2→3→4→5→6),
        then extract backward through all 6 weeks (6→5→4→3→2→1).
        
        Args:
            page: Playwright page object
            browser_automation: Optional BrowserAutomation instance for session checks
            
        Returns:
            Tuple of (list of slot dictionaries, flag)
            Flag: 1 if at least one slot was successfully clicked/selected during forward phase, 0 otherwise
        """
        slots = []
        max_weeks = 6  # Shinagawa limit for weekly navigation - always check all 6 weeks
        slots_clicked_flag = 0  # Flag: 1 if any slot was clicked, 0 if no slots found or clicked
        all_clicked_slot_ids = []  # Track all cell IDs that were successfully clicked in PHASE 1

        try:
            # Wait for weekly calendar container to be visible
            logger.info("Waiting for weekly calendar container (#weekly)...")
            await page.wait_for_selector('#weekly.calendar-area, #weekly',
                                         state='visible',
                                         timeout=30000)

            # Verify weekly calendar is expanded
            weekly_div = await page.query_selector('#weekly')
            if weekly_div:
                classes = await weekly_div.get_attribute('class') or ''
                if 'collapse' in classes and 'show' not in classes:
                    logger.info("Weekly calendar is collapsed - expanding...")
                    expand_button = await page.query_selector(
                        '#weekly button[data-toggle="collapse"]')
                    if expand_button:
                        await expand_button.click()
                        await page.wait_for_timeout(1000)

            # Always start from week 1
            # After a search, the calendar might default to showing a future week (often week 6)
            # This is because the website's calendar may default to showing the furthest week
            # or remember the last viewed week from a previous session
            is_on_week_one = await CalendarNavigator.is_on_week_one(page)
            if not is_on_week_one:
                logger.info("Not on week 1 - calendar likely defaulted to a future week after search. Navigating to week 1 first...")
                await CalendarNavigator.navigate_back_to_week_one(page)
                # Verify we're now on week 1 after navigation
                is_on_week_one_after = await CalendarNavigator.is_on_week_one(page)
                if not is_on_week_one_after:
                    logger.warning("Still not on week 1 after backward navigation - calendar may be in unexpected state")
                else:
                    logger.info("Successfully navigated to week 1")

            # PHASE 1: Extract forward through all 6 weeks (1→2→3→4→5→6)
            # During forward phase, click on slots to select them for booking
            logger.info(
                "PHASE 1: Extracting forward through all 6 weeks (week 1→2→3→4→5→6) - CLICKING slots"
            )
            for week_num in range(max_weeks):
                logger.info(
                    f"PHASE 1 - Processing week {week_num + 1} of {max_weeks} (forward)..."
                )

                # Extract slots from current week and click on them
                week_slots, week_flag, week_clicked_ids = await self.extract_slots_from_current_week(
                    page, week_num, click_slots=True)
                slots.extend(week_slots)
                all_clicked_slot_ids.extend(week_clicked_ids)  # Track clicked cell IDs
                # Update flag if any slot was clicked in this week
                if week_flag == 1:
                    slots_clicked_flag = 1
                logger.info(
                    f"PHASE 1 - Extracted {len(week_slots)} slots from week {week_num + 1} (total so far: {len(slots)}, flag: {slots_clicked_flag}, clicked IDs: {len(week_clicked_ids)})"
                )

                # Navigate to next week (if not last week)
                if week_num < max_weeks - 1:
                    # Check session before navigating to next week (6-week navigation takes time, session may expire)
                    if browser_automation:
                        try:
                            is_logged_in = await browser_automation.login_handler.is_logged_in(page)
                            if not is_logged_in:
                                logger.warning(f"Session expired during week {week_num + 1} navigation - re-logging in...")
                                await browser_automation.check_and_renew_login()
                                # Get the page again after re-login
                                page = browser_automation.session.main_page
                                if not page:
                                    logger.error("Could not get page after re-login - aborting week navigation")
                                    break
                                # Need to navigate back to the search results and court selection
                                logger.warning("Session was renewed - may need to re-select court. Continuing with current page...")
                        except Exception as e:
                            logger.warning(f"Error checking session during week navigation: {e}")
                    
                    # Navigate forward using "翌週" (Next Week) button
                    logger.info(
                        f"Looking for '翌週' (Next Week) button to navigate to week {week_num + 2}..."
                    )
                    
                    success = await CalendarNavigator.navigate_to_next_week(page)
                    if not success:
                        logger.info(
                            "'翌週' button is disabled or not found - no more weeks available"
                        )
                        break  # Stop navigation

            logger.info(
                f"PHASE 1 COMPLETE: Extracted {len(slots)} total slots from forward navigation (weeks 1→2→3→4→5→6). Total clicked slots: {len(all_clicked_slot_ids)}"
            )

            # PHASE 2: Extract backward through all 6 weeks (6→5→4→3→2→1)
            # During backward phase, restore any unchecked slots that were clicked in PHASE 1
            # We should now be on week 6, so we'll go backwards
            logger.info(
                f"PHASE 2: Extracting backward through all 6 weeks (week 6→5→4→3→2→1) - RESTORING unchecked slots from PHASE 1 ({len(all_clicked_slot_ids)} slots to check)"
            )
            for week_num in range(
                    max_weeks - 1, -1,
                    -1):  # Reverse: 5, 4, 3, 2, 1, 0 (weeks 6, 5, 4, 3, 2, 1)
                logger.info(
                    f"PHASE 2 - Processing week {week_num + 1} of {max_weeks} (backward)..."
                )

                # Extract slots from current week and restore any unchecked slots that were clicked in PHASE 1
                week_slots, week_flag, week_clicked_ids = await self.extract_slots_from_current_week(
                    page, week_num, click_slots=False, previously_clicked_ids=all_clicked_slot_ids)
                slots.extend(week_slots)
                # Update flag if any slot was restored
                if week_flag == 1:
                    slots_clicked_flag = 1
                logger.info(
                    f"PHASE 2 - Extracted {len(week_slots)} slots from week {week_num + 1} (total so far: {len(slots)}, restored: {len(week_clicked_ids)})"
                )

                # Navigate to previous week (if not week 1)
                if week_num > 0:
                    # Check session before navigating to previous week (6-week navigation takes time, session may expire)
                    if browser_automation:
                        try:
                            is_logged_in = await browser_automation.login_handler.is_logged_in(page)
                            if not is_logged_in:
                                logger.warning(f"Session expired during week {week_num + 1} backward navigation - re-logging in...")
                                await browser_automation.check_and_renew_login()
                                # Get the page again after re-login
                                page = browser_automation.session.main_page
                                if not page:
                                    logger.error("Could not get page after re-login - aborting week navigation")
                                    break
                                logger.warning("Session was renewed - may need to re-select court. Continuing with current page...")
                        except Exception as e:
                            logger.warning(f"Error checking session during backward week navigation: {e}")
                    
                    # Navigate backward using "前週" (Previous Week) button
                    logger.info(
                        f"Looking for '前週' (Previous Week) button to navigate to week {week_num}..."
                    )
                    
                    success = await CalendarNavigator.navigate_to_previous_week(page)
                    if not success:
                        logger.info(
                            "'前週' button is disabled or not found - reached week 1, stopping backward navigation"
                        )
                        break  # Reached week 1, stop

            logger.info(
                f"PHASE 2 COMPLETE: Extracted {len(slots)} total slots from both forward and backward navigation"
            )
            logger.info(
                f"COMPLETED: Checked all {max_weeks} weeks forward (1→6) and backward (6→1) for this court"
            )
            logger.info(
                f"Slots clicked flag: {slots_clicked_flag} (1=slots clicked, 0=no slots clicked)"
            )

        except Exception as e:
            logger.error(f"Error extracting slots from weekly calendar: {e}")
            import traceback
            logger.error(traceback.format_exc())

        return slots, slots_clicked_flag

    async def extract_slots_from_page(self, page: Page) -> List[Dict]:
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
            reservation_rows = await page.query_selector_all(
                'tr[id^="20"]')  # Rows with IDs starting with year

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
                    button = await row.query_selector(
                        'button:has-text("予約"), td.reservation button')
                    if not button:
                        continue

                    onclick = await button.get_attribute('onclick')
                    if not onclick or 'doReserved' not in onclick:
                        continue

                    # Parse onclick: doReserved(useYmd, bcd, icd, fieldCnt, startTime, endTime, ...)
                    # Example: doReserved(20260105,'1020','10200020',10,830,1630,31000000,31011700,'','',0,'10|20|30|40','830|1030|1230|1430','1030|1230|1430|1630');
                    match = re.search(
                        r"doReserved\((\d+),'(\d+)','(\d+)',(\d+),(\d+),(\d+),(\d+),(\d+)",
                        onclick)
                    if match:
                        end_time = int(match.group(6))
                        field_cnt = int(match.group(4))

                        # Only include available slots (fieldCnt = 0 means available)
                        if field_cnt == 0:
                            # Get park and facility names from table cells
                            park_name = ""
                            facility_name = ""
                            try:
                                park_cell = await row.query_selector(
                                    'td.mansion')
                                if park_cell:
                                    park_name = await park_cell.inner_text()
                                    park_name = park_name.strip()

                                facility_cell = await row.query_selector(
                                    'td.facility')
                                if facility_cell:
                                    facility_name = await facility_cell.inner_text(
                                    )
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
                                'start_time_display':
                                f"{start_time//100:02d}:{start_time%100:02d}",
                                'end_time_display':
                                f"{end_time//100:02d}:{end_time%100:02d}",
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

