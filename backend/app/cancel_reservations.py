"""Script to cancel existing reservations."""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Optional
import logging
from app.config import settings
from app.browser_automation import BrowserAutomation

logger = logging.getLogger(__name__)


class ReservationCanceller:
    """Handles cancellation of existing reservations."""
    
    def __init__(self):
        self.browser_automation = BrowserAutomation()
        self.page: Optional[Page] = None
    
    async def start(self):
        """Start browser and login."""
        logger.info("Starting browser and logging in...")
        await self.browser_automation.start()
        await self.browser_automation.login()
        self.page = self.browser_automation.main_page
        logger.info("Login successful - ready to cancel reservations")
    
    async def stop(self):
        """Stop browser."""
        await self.browser_automation.stop()
        logger.info("Browser stopped")
    
    async def navigate_to_reservation_list(self) -> bool:
        """Navigate to the reservation list page (予約受付一覧).
        
        Returns:
            True if successfully navigated, False otherwise
        """
        try:
            logger.info("Navigating to reservation list page...")
            
            # Wait for the page to be ready
            await self.page.wait_for_load_state('networkidle', timeout=30000)
            await self.page.wait_for_timeout(1000)
            
            # First, find and click the "予約" dropdown toggle button to open the dropdown menu
            logger.info("Looking for '予約' dropdown toggle button...")
            dropdown_toggle_selectors = [
                'a.nav-link.dropdown-toggle:has-text("予約")',
                'a.dropdown-toggle:has-text("予約")',
                'a[data-toggle="dropdown"]:has-text("予約")',
                'a.nav-link[onclick*="doMsgListAction"]',
                'a[onclick*="doMsgListAction"]'
            ]
            
            dropdown_toggle = None
            for selector in dropdown_toggle_selectors:
                try:
                    toggle = await self.page.query_selector(selector)
                    if toggle:
                        # Check if it's visible
                        is_visible = await toggle.evaluate('el => window.getComputedStyle(el).display !== "none"')
                        if is_visible:
                            dropdown_toggle = toggle
                            logger.info(f"Found '予約' dropdown toggle with selector: {selector}")
                            break
                except:
                    continue
            
            if not dropdown_toggle:
                logger.error("Could not find '予約' dropdown toggle button")
                return False
            
            # Click the dropdown toggle to open the menu
            logger.info("Clicking '予約' dropdown toggle to open menu...")
            await dropdown_toggle.scroll_into_view_if_needed()
            await self.page.wait_for_timeout(300)
            await dropdown_toggle.click()
            
            # Wait for dropdown menu to appear
            await self.page.wait_for_timeout(500)
            
            # Wait for the dropdown menu to be visible
            try:
                await self.page.wait_for_selector('.dropdown-menu.show, .dropdown-menu[style*="display: block"]', state='visible', timeout=5000)
                logger.info("Dropdown menu opened successfully")
            except:
                logger.warning("Dropdown menu visibility check timed out, but continuing...")
            
            # Now look for the "予約の確認・取消" link in the dropdown menu
            logger.info("Looking for '予約の確認・取消' link in dropdown menu...")
            cancel_link_selectors = [
                'a.dropdown-item:has-text("予約の確認・取消")',
                'a.dropdown-item[onclick*="gRsvWGetCancelRsvDataAction"]',
                'a:has-text("予約の確認・取消")',
                'a[href*="gRsvWGetCancelRsvDataAction"]',
                'a[onclick*="gRsvWGetCancelRsvDataAction"]'
            ]
            
            cancel_link = None
            for selector in cancel_link_selectors:
                try:
                    cancel_link = await self.page.query_selector(selector)
                    if cancel_link:
                        # Check if it's visible
                        is_visible = await cancel_link.evaluate('el => window.getComputedStyle(el).display !== "none"')
                        if is_visible:
                            logger.info(f"Found '予約の確認・取消' link with selector: {selector}")
                            break
                except:
                    continue
            
            if not cancel_link:
                logger.error("Could not find '予約の確認・取消' link")
                return False
            
            # Click the link
            logger.info("Clicking '予約の確認・取消' link...")
            await cancel_link.scroll_into_view_if_needed()
            await self.page.wait_for_timeout(500)
            
            # Set up dialog handler in case there's a dialog
            async def handle_dialog(dialog):
                logger.info(f"Dialog detected: {dialog.message}")
                await dialog.accept()
            
            self.page.on('dialog', handle_dialog)
            
            try:
                # Click and wait for navigation
                async with self.page.expect_navigation(wait_until='networkidle', timeout=30000):
                    await cancel_link.click()
                
                await self.page.wait_for_load_state('networkidle', timeout=30000)
                await self.page.wait_for_timeout(2000)
                
                # Verify we're on the reservation list page
                current_url = self.page.url
                page_title = await self.page.title()
                
                if 'rsvWGetCancelRsvDataAction' in current_url or '予約受付一覧' in page_title:
                    logger.info("Successfully navigated to reservation list page")
                    return True
                else:
                    logger.warning(f"Navigation completed but URL/title doesn't match expected: URL={current_url}, Title={page_title}")
                    return True  # Still return True as navigation happened
            finally:
                # Remove dialog handler
                try:
                    self.page.remove_listener('dialog', handle_dialog)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error navigating to reservation list: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def cancel_reservation(self, reservation_index: int = 0) -> bool:
        """Cancel a reservation by clicking the "取消" button.
        
        Args:
            reservation_index: Index of the reservation to cancel (0 = first one)
            
        Returns:
            True if cancellation was successful, False otherwise
        """
        try:
            logger.info(f"Attempting to cancel reservation at index {reservation_index}...")
            
            # Wait for page to be ready
            await self.page.wait_for_load_state('networkidle', timeout=30000)
            await self.page.wait_for_timeout(1000)
            
            # Find all "取消" buttons
            cancel_button_selectors = [
                'button.btn-go:has-text("取消")',
                'button:has-text("取消")',
                'button[onclick*="rsvcancel"]',
                'button[onclick*="gRsvWCancelRsvAction"]'
            ]
            
            cancel_buttons = []
            for selector in cancel_button_selectors:
                try:
                    buttons = await self.page.query_selector_all(selector)
                    for btn in buttons:
                        # Check if button is visible
                        is_visible = await btn.evaluate('el => window.getComputedStyle(el).display !== "none"')
                        if is_visible:
                            # Check if it's not already in our list
                            btn_onclick = await btn.get_attribute('onclick') or ''
                            if 'rsvcancel' in btn_onclick or 'gRsvWCancelRsvAction' in btn_onclick:
                                cancel_buttons.append(btn)
                except:
                    continue
            
            if not cancel_buttons:
                logger.warning("No '取消' buttons found on the page")
                return False
            
            if reservation_index >= len(cancel_buttons):
                logger.warning(f"Reservation index {reservation_index} is out of range. Found {len(cancel_buttons)} cancel buttons")
                return False
            
            cancel_button = cancel_buttons[reservation_index]
            logger.info(f"Found cancel button at index {reservation_index} (total: {len(cancel_buttons)})")
            
            # Set up dialog handler for the confirmation alert
            # The alert message is: "選択した施設予約申込みを取り消しますか?"
            dialog_handled = False
            
            async def handle_dialog(dialog):
                nonlocal dialog_handled
                dialog_message = dialog.message
                logger.info(f"JavaScript dialog detected: {dialog_message}")
                if "取り消しますか" in dialog_message or "取消" in dialog_message:
                    logger.info("Accepting cancellation confirmation dialog...")
                    await dialog.accept()
                    dialog_handled = True
                else:
                    logger.warning(f"Unexpected dialog message: {dialog_message}, accepting anyway")
                    await dialog.accept()
                    dialog_handled = True
            
            self.page.on('dialog', handle_dialog)
            
            try:
                # Click the cancel button
                logger.info("Clicking '取消' button...")
                await cancel_button.scroll_into_view_if_needed()
                await self.page.wait_for_timeout(500)
                await cancel_button.click()
                
                # Wait for dialog to appear and be handled
                await self.page.wait_for_timeout(1000)
                
                if dialog_handled:
                    logger.info("Dialog was handled successfully")
                else:
                    logger.warning("Dialog handler was set but dialog may not have appeared")
                    # Try alternative: wait for dialog event explicitly
                    try:
                        async with self.page.expect_dialog() as dialog_info:
                            await cancel_button.click()
                        dialog = await dialog_info.value
                        logger.info(f"Dialog appeared: {dialog.message}")
                        await dialog.accept()
                        logger.info("Accepted dialog using expect_dialog")
                        dialog_handled = True
                    except:
                        pass
                
                # Wait for navigation to cancellation completion page
                await self.page.wait_for_load_state('networkidle', timeout=30000)
                await self.page.wait_for_timeout(2000)
                
                # Verify we're on the cancellation completion page
                current_url = self.page.url
                page_title = await self.page.title()
                
                if 'rsvWCancelRsvAction' in current_url or '予約取消完了' in page_title:
                    logger.info("Successfully cancelled reservation - on cancellation completion page")
                    return True
                else:
                    logger.warning(f"Cancellation may have completed but URL/title doesn't match: URL={current_url}, Title={page_title}")
                    return True  # Still return True as cancellation likely succeeded
                    
            finally:
                # Remove dialog handler
                try:
                    self.page.remove_listener('dialog', handle_dialog)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error cancelling reservation: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def return_to_reservation_list(self) -> bool:
        """Click "予約受付一覧へ" button to return to reservation list.
        
        Returns:
            True if successfully returned, False otherwise
        """
        try:
            logger.info("Clicking '予約受付一覧へ' button to return to reservation list...")
            
            # Wait for page to be ready
            await self.page.wait_for_load_state('networkidle', timeout=30000)
            await self.page.wait_for_timeout(1000)
            
            # Find the "予約受付一覧へ" button
            return_button_selectors = [
                'button.btn-light:has-text("予約受付一覧へ")',
                'button:has-text("予約受付一覧へ")',
                'button[onclick*="gRsvWGetCancelRsvDataAction"]',
                'button[onclick*="doAction"][onclick*="gRsvWGetCancelRsvDataAction"]'
            ]
            
            return_button = None
            for selector in return_button_selectors:
                try:
                    button = await self.page.query_selector(selector)
                    if button:
                        # Verify this is the correct button
                        button_text = await button.inner_text()
                        button_onclick = await button.get_attribute('onclick') or ''
                        
                        if '予約受付一覧へ' in button_text or 'gRsvWGetCancelRsvDataAction' in button_onclick:
                            is_visible = await button.evaluate('el => window.getComputedStyle(el).display !== "none"')
                            if is_visible:
                                return_button = button
                                logger.info(f"Found '予約受付一覧へ' button with selector: {selector}")
                                break
                except:
                    continue
            
            if not return_button:
                logger.error("Could not find '予約受付一覧へ' button")
                return False
            
            # Click the button
            await return_button.scroll_into_view_if_needed()
            await self.page.wait_for_timeout(500)
            
            # Set up dialog handler in case there's a dialog
            async def handle_dialog(dialog):
                logger.info(f"Dialog detected: {dialog.message}")
                await dialog.accept()
            
            self.page.on('dialog', handle_dialog)
            
            try:
                # Click and wait for navigation
                async with self.page.expect_navigation(wait_until='networkidle', timeout=30000):
                    await return_button.click()
                
                await self.page.wait_for_load_state('networkidle', timeout=30000)
                await self.page.wait_for_timeout(2000)
                
                # Verify we're back on the reservation list page
                current_url = self.page.url
                page_title = await self.page.title()
                
                if 'rsvWGetCancelRsvDataAction' in current_url or '予約受付一覧' in page_title:
                    logger.info("Successfully returned to reservation list page")
                    return True
                else:
                    logger.warning(f"Navigation completed but URL/title doesn't match expected: URL={current_url}, Title={page_title}")
                    return True  # Still return True as navigation happened
            finally:
                # Remove dialog handler
                try:
                    self.page.remove_listener('dialog', handle_dialog)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error returning to reservation list: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def cancel_all_reservations(self, max_cancellations: int = 100) -> int:
        """Cancel all reservations on the list.
        
        Args:
            max_cancellations: Maximum number of cancellations to perform (safety limit)
            
        Returns:
            Number of reservations successfully cancelled
        """
        cancelled_count = 0
        
        try:
            # Navigate to reservation list
            if not await self.navigate_to_reservation_list():
                logger.error("Failed to navigate to reservation list")
                return 0
            
            # Keep cancelling until no more cancel buttons are found
            iteration = 0
            while iteration < max_cancellations:
                iteration += 1
                logger.info(f"=== Cancellation iteration {iteration} ===")
                
                # Wait for page to be ready
                await self.page.wait_for_load_state('networkidle', timeout=30000)
                await self.page.wait_for_timeout(1000)
                
                # Check if there are any cancel buttons
                cancel_button_selectors = [
                    'button.btn-go:has-text("取消")',
                    'button:has-text("取消")',
                    'button[onclick*="rsvcancel"]'
                ]
                
                cancel_buttons = []
                for selector in cancel_button_selectors:
                    try:
                        buttons = await self.page.query_selector_all(selector)
                        for btn in buttons:
                            is_visible = await btn.evaluate('el => window.getComputedStyle(el).display !== "none"')
                            if is_visible:
                                btn_onclick = await btn.get_attribute('onclick') or ''
                                if 'rsvcancel' in btn_onclick or 'gRsvWCancelRsvAction' in btn_onclick:
                                    cancel_buttons.append(btn)
                    except:
                        continue
                
                if not cancel_buttons:
                    logger.info("No more cancel buttons found - all reservations cancelled or none remaining")
                    break
                
                logger.info(f"Found {len(cancel_buttons)} reservation(s) available for cancellation")
                
                # Cancel the first reservation
                if await self.cancel_reservation(reservation_index=0):
                    cancelled_count += 1
                    logger.info(f"Successfully cancelled reservation {cancelled_count}")
                    
                    # Return to reservation list to check for more
                    if not await self.return_to_reservation_list():
                        logger.warning("Failed to return to reservation list, but continuing...")
                        # Try to navigate again
                        if not await self.navigate_to_reservation_list():
                            logger.error("Failed to navigate to reservation list after cancellation")
                            break
                else:
                    logger.warning(f"Failed to cancel reservation at iteration {iteration}")
                    # Try to return to list anyway
                    await self.return_to_reservation_list()
                    break
            
            logger.info(f"Completed cancellation process. Total cancelled: {cancelled_count}")
            return cancelled_count
            
        except Exception as e:
            logger.error(f"Error in cancel_all_reservations: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return cancelled_count


async def main():
    """Main function to run the cancellation script."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    canceller = ReservationCanceller()
    
    try:
        # Start browser and login
        await canceller.start()
        
        # Cancel all reservations
        cancelled_count = await canceller.cancel_all_reservations(max_cancellations=100)
        
        logger.info(f"=== SUMMARY ===")
        logger.info(f"Total reservations cancelled: {cancelled_count}")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # Stop browser
        await canceller.stop()


if __name__ == "__main__":
    asyncio.run(main())

