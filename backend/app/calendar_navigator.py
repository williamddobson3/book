"""Calendar navigation utilities for weekly calendar view."""
from playwright.async_api import Page
from typing import Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class CalendarNavigator:
    """Handles navigation through weekly calendar views."""
    
    @staticmethod
    async def is_on_week_one(page: Page) -> bool:
        """Check if calendar is currently on week 1."""
        try:
            today = datetime.now().strftime('%Y%m%d')
            today_int = int(today)
            
            logger.info(f"Checking if today's date ({today}) is in the calendar table...")
            
            try:
                await page.wait_for_selector('table#week-info', state='visible', timeout=5000)
            except:
                logger.warning("Calendar table not found - cannot determine week position")
                return False
            
            all_cells = await page.query_selector_all('table#week-info td[id]')
            if not all_cells:
                logger.warning("No cells with IDs found in calendar table")
                return False
            
            for cell in all_cells:
                try:
                    cell_id = await cell.get_attribute('id')
                    if not cell_id or '_' not in cell_id:
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
            
            logger.info(f"Today's date ({today}) not found in calendar table - NOT on week 1")
            return False
        except Exception as e:
            logger.warning(f"Error checking if on week 1: {e}, assuming not on week 1")
            return False
    
    @staticmethod
    async def navigate_back_to_week_one(page: Page) -> bool:
        """Navigate backwards to week 1 using '前週' button.
        
        Keeps clicking '前週' until the button is disabled (indicating we're at week 1)
        or until we verify we're actually on week 1.
        """
        try:
            logger.info("Navigating backwards to week 1 using '前週' button...")
            max_backward_clicks = 6  # Increased to 6 to handle week 6 → week 1
            
            for click_num in range(max_backward_clicks):
                # First, check if we're already on week 1
                is_on_week_one = await CalendarNavigator.is_on_week_one(page)
                if is_on_week_one:
                    logger.info(f"Verified we're on week 1 after {click_num} backward clicks")
                    return True
                
                # Find the '前週' button
                prev_week_button = None
                prev_week_selectors = [
                    '#last-week',
                    'button#last-week',
                    'button:has-text("前週")',
                    '[onclick*="getWeekInfoAjax"][onclick*="3"]',
                    'button[onclick*="getWeekInfoAjax(3"]'
                ]
                
                for selector in prev_week_selectors:
                    try:
                        button = await page.query_selector(selector)
                        if button:
                            is_disabled = await button.get_attribute('disabled')
                            if is_disabled:
                                logger.info(f"'前週' button is disabled - already at week 1")
                                # Verify we're actually on week 1
                                is_on_week_one = await CalendarNavigator.is_on_week_one(page)
                                if is_on_week_one:
                                    return True
                                else:
                                    logger.warning("'前週' button is disabled but we're not on week 1 - calendar may be in unexpected state")
                                    return False
                            
                            is_visible = await button.evaluate(
                                'el => window.getComputedStyle(el).display !== "none"'
                            )
                            if is_visible:
                                prev_week_button = button
                                break
                    except:
                        continue
                
                if not prev_week_button:
                    logger.info(f"'前週' button not found - may already be at week 1")
                    # Verify we're actually on week 1
                    is_on_week_one = await CalendarNavigator.is_on_week_one(page)
                    if is_on_week_one:
                        return True
                    else:
                        logger.warning("'前週' button not found but we're not on week 1 - calendar may be in unexpected state")
                        return False
                
                try:
                    logger.info(f"Clicking '前週' button (click {click_num + 1} of up to {max_backward_clicks})...")
                    await prev_week_button.scroll_into_view_if_needed()
                    await page.wait_for_timeout(500)
                    await prev_week_button.click()
                    
                    # Wait for AJAX
                    try:
                        loading_indicator = await page.query_selector('#loadingweek')
                        if loading_indicator:
                            await page.wait_for_function(
                                'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                                timeout=30000)
                    except:
                        pass
                    
                    await page.wait_for_load_state('networkidle', timeout=30000)
                    await page.wait_for_timeout(2000)
                    await page.wait_for_selector('table#week-info', state='visible', timeout=15000)
                    
                    # After navigation, check if we're now on week 1
                    is_on_week_one = await CalendarNavigator.is_on_week_one(page)
                    if is_on_week_one:
                        logger.info(f"Successfully reached week 1 after {click_num + 1} backward clicks")
                        return True
                except Exception as e:
                    logger.warning(f"Error clicking '前週' button at click {click_num + 1}: {e}")
            
            # Final check after all clicks
            is_on_week_one = await CalendarNavigator.is_on_week_one(page)
            if is_on_week_one:
                logger.info("Successfully reached week 1 after maximum backward clicks")
                return True
            else:
                logger.warning("Reached maximum backward clicks but still not on week 1 - calendar may be in unexpected state")
                return False
        except Exception as e:
            logger.warning(f"Error navigating backwards to week 1: {e}")
            return False
    
    @staticmethod
    async def navigate_to_next_week(page: Page) -> bool:
        """Navigate to next week using '翌週' button."""
        try:
            next_week_selectors = [
                '#next-week',
                'button#next-week',
                'button:has-text("翌週")',
                'a:has-text("翌週")',
                'button:has(span.btn-title-pc:has-text("翌週"))',
                '[onclick*="getWeekInfoAjax"][onclick*="4"]',
            ]
            
            button_found = False
            for selector in next_week_selectors:
                try:
                    button = await page.wait_for_selector(selector, state='visible', timeout=10000)
                    if button:
                        is_disabled = await button.get_attribute('disabled')
                        if is_disabled:
                            logger.info("'翌週' button is disabled - no more weeks available")
                            return False
                        
                        is_visible = await button.evaluate(
                            'el => window.getComputedStyle(el).display !== "none"'
                        )
                        if is_visible:
                            await button.scroll_into_view_if_needed()
                            await page.wait_for_timeout(500)
                            await button.click()
                            
                            # Wait for AJAX
                            try:
                                loading_indicator = await page.query_selector('#loadingweek')
                                if loading_indicator:
                                    await page.wait_for_function(
                                        'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                                        timeout=30000)
                            except:
                                pass
                            
                            await page.wait_for_load_state('networkidle', timeout=30000)
                            await page.wait_for_timeout(2000)
                            await page.wait_for_selector('table#week-info', state='visible', timeout=15000)
                            
                            button_found = True
                            logger.info(f"Successfully navigated to next week using selector: {selector}")
                            break
                except Exception as e:
                    logger.debug(f"Button not found with selector {selector}: {e}")
                    continue
            
            return button_found
        except Exception as e:
            logger.warning(f"Error navigating to next week: {e}")
            return False
    
    @staticmethod
    async def navigate_to_previous_week(page: Page) -> bool:
        """Navigate to previous week using '前週' button."""
        try:
            prev_week_selectors = [
                '#last-week',
                'button#last-week',
                'button:has-text("前週")',
                '[onclick*="getWeekInfoAjax"][onclick*="3"]',
            ]
            
            for selector in prev_week_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        is_disabled = await button.get_attribute('disabled')
                        if is_disabled:
                            logger.info("'前週' button is disabled - reached week 1")
                            return False
                        
                        is_visible = await button.evaluate(
                            'el => window.getComputedStyle(el).display !== "none"'
                        )
                        if is_visible:
                            await button.scroll_into_view_if_needed()
                            await page.wait_for_timeout(500)
                            await button.click()
                            
                            # Wait for AJAX
                            try:
                                loading_indicator = await page.query_selector('#loadingweek')
                                if loading_indicator:
                                    await page.wait_for_function(
                                        'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                                        timeout=30000)
                            except:
                                pass
                            
                            await page.wait_for_load_state('networkidle', timeout=30000)
                            await page.wait_for_timeout(2000)
                            await page.wait_for_selector('table#week-info', state='visible', timeout=15000)
                            
                            logger.info(f"Successfully navigated to previous week using selector: {selector}")
                            return True
                except:
                    continue
            
            return False
        except Exception as e:
            logger.warning(f"Error navigating to previous week: {e}")
            return False

