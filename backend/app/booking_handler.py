"""Booking handler for reservation flow."""
import logging
from typing import Dict, Optional, List
from playwright.async_api import Page

from app.form_utils import FormUtils
from app.network_capture import NetworkCapture

logger = logging.getLogger(__name__)


class BookingHandler:
    """Handles the booking/reservation flow."""
    
    def __init__(self, enable_network_capture: bool = False):
        """
        Initialize booking handler.
        
        Args:
            enable_network_capture: If True, capture network requests during booking
                                   (useful for reverse-engineering API endpoints)
        """
        self.enable_network_capture = enable_network_capture
        self.network_capture: Optional[NetworkCapture] = None
    
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
        # Start network capture if enabled
        if self.enable_network_capture:
            self.network_capture = NetworkCapture()
            await self.network_capture.start_capture(page)
            logger.info("🎯 Network capture enabled for booking flow")
        
        try:
            if slots_clicked_flag != 1:
                logger.info(
                    f"Slots clicked flag is {slots_clicked_flag} - no slots were clicked, skipping '予約' button click"
                )
                return False

            logger.info(
                f"Slots clicked flag is 1 - clicking '予約' button to proceed to reservation page (found {len(slots)} slot(s))..."
            )
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

                        if 'gRsvWOpeReservedApplyAction' in onclick or (
                                '予約' in button_text
                                and 'gRsvWInstUseruleRsvApplyAction'
                                not in onclick):
                            reserve_button = button
                            logger.info(
                                f"Found correct '予約' button with onclick: {onclick[:100] if onclick else 'none'}"
                            )
                            break
                except:
                    continue

            if not reserve_button:
                reserve_button = await page.query_selector('#btn-go')
                if reserve_button:
                    onclick = await reserve_button.get_attribute('onclick'
                                                                 ) or ''
                    logger.info(
                        f"Using #btn-go button with onclick: {onclick[:100] if onclick else 'none'}"
                    )

            if reserve_button:
                is_disabled = await reserve_button.get_attribute('disabled')
                if not is_disabled:
                    await reserve_button.scroll_into_view_if_needed()
                    await page.wait_for_timeout(500)
                    await reserve_button.click()
                    logger.info(
                        "Successfully clicked '予約' button - navigating to reservation page"
                    )

                    await page.wait_for_load_state('networkidle',
                                                   timeout=30000)
                    await page.wait_for_timeout(2000)
                    logger.info("Navigation to reservation page completed")

                    # Handle Terms of Use page and reservation confirmation
                    await self._handle_terms_of_use_page(page)
                    await self._handle_reservation_confirmation_page(page)
                    await self._handle_reservation_completion_page(page)
                    
                    # Stop network capture and save results
                    if self.enable_network_capture and self.network_capture:
                        self.network_capture.stop_capture()
                        self.network_capture.save_to_file('booking_requests.json')
                        self.network_capture.print_summary()
                        self.network_capture.save_api_template('booking_api_template.py')
                    
                    return True
                else:
                    logger.warning(
                        "'予約' button is disabled - cannot proceed to reservation"
                    )
                    return False
            else:
                logger.warning("'予約' button (#btn-go) not found on page")
                return False
        except Exception as e:
            logger.warning(
                f"Error clicking '予約' button or handling Terms of Use page: {e}"
            )
            import traceback
            logger.warning(traceback.format_exc())
            
            # Stop network capture even on error
            if self.enable_network_capture and self.network_capture:
                self.network_capture.stop_capture()
                self.network_capture.save_to_file('booking_requests_error.json')
            
            return False

    async def _handle_terms_of_use_page(self, page: Page) -> bool:
        """Handle Terms of Use agreement page.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            current_url = page.url
            page_title = await page.title()
            if 'rsvWOpeReservedApplyAction' in current_url or '利用規約' in page_title:
                logger.info(
                    "Detected Terms of Use page - handling agreement..."
                )

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
                            tag_name = await element.evaluate(
                                'el => el.tagName.toLowerCase()')
                            if tag_name == 'label':
                                await element.scroll_into_view_if_needed(
                                )
                                await page.wait_for_timeout(300)
                                await element.click()
                                logger.info(
                                    f"Clicked agreement label using selector: {selector}"
                                )
                            else:
                                await element.scroll_into_view_if_needed(
                                )
                                await page.wait_for_timeout(300)
                                await element.check()
                                logger.info(
                                    f"Checked agreement input using selector: {selector}"
                                )
                            await page.wait_for_timeout(500)
                            agreement_clicked = True
                            break
                    except Exception as e:
                        logger.debug(
                            f"Failed to click agreement with selector {selector}: {e}"
                        )
                        continue

                if not agreement_clicked:
                    logger.warning(
                        "Could not find/click agreement option, trying to proceed anyway"
                    )

                # Click "確認" button
                logger.info("Clicking '確認' button...")
                confirm_clicked = False
                confirm_selectors = [
                    '#btn-go', 'button#btn-go',
                    'button:has-text("確認")',
                    'button[type="submit"]:has-text("確認")',
                    'button[onclick*="gRsvWInstUseruleRsvApplyAction"]'
                ]

                for selector in confirm_selectors:
                    try:
                        confirm_button = await page.query_selector(
                            selector)
                        if confirm_button:
                            is_disabled = await confirm_button.get_attribute(
                                'disabled')
                            if not is_disabled:
                                await confirm_button.scroll_into_view_if_needed(
                                )
                                await page.wait_for_timeout(500)
                                await confirm_button.click()
                                logger.info(
                                    f"Clicked '確認' button using selector: {selector}"
                                )

                                await page.wait_for_load_state(
                                    'networkidle', timeout=30000)
                                await page.wait_for_timeout(2000)
                                confirm_clicked = True
                                logger.info(
                                    "Successfully handled Terms of Use page"
                                )
                                break
                    except Exception as e:
                        logger.debug(
                            f"Failed to click confirm with selector {selector}: {e}"
                        )
                        continue

                if not confirm_clicked:
                    logger.warning(
                        "Could not find/click '確認' button on Terms of Use page"
                    )
                
                return confirm_clicked
            return True
        except Exception as e:
            logger.error(f"Error handling Terms of Use page: {e}")
            return False

    async def _handle_reservation_confirmation_page(self, page: Page) -> bool:
        """Handle reservation confirmation page (fill user count, click final reserve button).
        
        Args:
            page: Playwright page object
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            await page.wait_for_load_state('networkidle',
                                           timeout=30000)
            await page.wait_for_timeout(2000)
            current_url_after_confirm = page.url
            page_title_after_confirm = await page.title()

            if 'rsvWInstUseruleRsvApplyAction' in current_url_after_confirm or 'rsvWInstRsvApplyAction' in current_url_after_confirm or '予約内容確認' in page_title_after_confirm:
                logger.info(
                    "Detected reservation confirmation page - filling in number of users for each reservation slot..."
                )

                # Fill in "利用人数" (Number of Users) for each reservation slot
                # Default number of users: 2 (as requested by user)
                default_user_count = 2

                # Use FormUtils to fill user count inputs
                await FormUtils.fill_user_count_inputs(page, default_user_count)

                await page.wait_for_timeout(500)

                logger.info(
                    "Filled user count fields - clicking final '予約' button..."
                )

                final_reserve_clicked = False
                final_reserve_selectors = [
                    '#btn-go', 'button#btn-go',
                    'button:has-text("予約")',
                    'button[onclick*="gRsvWInstRsvApplyAction"]',
                    'button[onclick*="checkTextValue"]'
                ]

                for selector in final_reserve_selectors:
                    try:
                        final_button = await page.query_selector(
                            selector)
                        if final_button:
                            button_onclick = await final_button.get_attribute(
                                'onclick') or ''
                            button_text = await final_button.inner_text(
                            )

                            if 'gRsvWInstRsvApplyAction' in button_onclick or (
                                    '予約' in button_text
                                    and 'checkTextValue'
                                    in button_onclick):
                                is_disabled = await final_button.get_attribute(
                                    'disabled')
                                if not is_disabled:
                                    await final_button.scroll_into_view_if_needed(
                                    )
                                    await page.wait_for_timeout(500)

                                    dialog_handled = False

                                    async def handle_dialog(
                                            dialog):
                                        nonlocal dialog_handled
                                        dialog_message = dialog.message
                                        logger.info(
                                            f"JavaScript dialog detected: {dialog_message}"
                                        )
                                        if "予約申込処理を行います" in dialog_message or "よろしいですか" in dialog_message:
                                            logger.info(
                                                "Accepting reservation confirmation dialog..."
                                            )
                                            await dialog.accept()
                                            dialog_handled = True
                                        else:
                                            logger.warning(
                                                f"Unexpected dialog message: {dialog_message}, accepting anyway"
                                            )
                                            await dialog.accept()
                                            dialog_handled = True

                                    page.on(
                                        'dialog', handle_dialog)

                                    try:
                                        await final_button.click()
                                        logger.info(
                                            f"Clicked final '予約' button on reservation confirmation page using selector: {selector}"
                                        )

                                        await page.wait_for_timeout(
                                            1000)

                                        if dialog_handled:
                                            logger.info(
                                                "Dialog was handled successfully"
                                            )
                                        else:
                                            logger.warning(
                                                "Dialog handler was set but dialog may not have appeared"
                                            )

                                        await page.wait_for_load_state(
                                            'networkidle',
                                            timeout=30000)
                                        await page.wait_for_timeout(
                                            2000)
                                        final_reserve_clicked = True
                                        logger.info(
                                            "Successfully clicked final '予約' button and handled dialog - booking should be completed"
                                        )
                                        break
                                    except Exception as click_error:
                                        logger.warning(
                                            f"Error clicking button or handling dialog: {click_error}"
                                        )
                                        try:
                                            async with page.expect_dialog(
                                            ) as dialog_info:
                                                await final_button.click(
                                                )
                                            dialog = await dialog_info.value
                                            logger.info(
                                                f"Dialog appeared: {dialog.message}"
                                            )
                                            await dialog.accept()
                                            logger.info(
                                                "Accepted dialog using expect_dialog"
                                            )
                                            await page.wait_for_load_state(
                                                'networkidle',
                                                timeout=30000)
                                            await page.wait_for_timeout(
                                                2000)
                                            final_reserve_clicked = True
                                            logger.info(
                                                "Successfully clicked final '予約' button and handled dialog (alternative method) - booking should be completed"
                                            )
                                            break
                                        except Exception as alt_error:
                                            logger.warning(
                                                f"Alternative dialog handling also failed: {alt_error}"
                                            )
                                            continue
                                    finally:
                                        try:
                                            page.remove_listener(
                                                'dialog',
                                                handle_dialog)
                                        except:
                                            pass
                    except Exception as e:
                        logger.debug(
                            f"Failed to click final reserve button with selector {selector}: {e}"
                        )
                        continue

                if not final_reserve_clicked:
                    logger.warning(
                        "Could not find/click final '予約' button on reservation confirmation page"
                    )
                
                return final_reserve_clicked
            return True
        except Exception as e:
            logger.error(f"Error handling reservation confirmation page: {e}")
            return False

    async def _handle_reservation_completion_page(self, page: Page) -> bool:
        """Handle reservation completion page (click payment button, then back button).
        
        Args:
            page: Playwright page object
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            # After clicking final '予約' button, check if we're on reservation completion page
            # and click "未入金予約の確認・支払へ" button if present
            await page.wait_for_load_state('networkidle',
                                           timeout=30000)
            await page.wait_for_timeout(2000)
            current_url_after_booking = page.url
            page_title_after_booking = await page.title()

            if 'rsvWInstRsvApplyAction' in current_url_after_booking or '予約完了' in page_title_after_booking:
                logger.info(
                    "Detected reservation completion page - clicking '未入金予約の確認・支払へ' button..."
                )

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
                        payment_button = await page.query_selector(
                            selector)
                        if payment_button:
                            # Verify this is the payment button by checking onclick or text
                            button_onclick = await payment_button.get_attribute(
                                'onclick') or ''
                            button_text = await payment_button.inner_text(
                            )

                            if 'gRsvCreditInitListAction' in button_onclick or '未入金予約の確認・支払へ' in button_text:
                                is_disabled = await payment_button.get_attribute(
                                    'disabled')
                                if not is_disabled:
                                    await payment_button.scroll_into_view_if_needed(
                                    )
                                    await page.wait_for_timeout(500)
                                    await payment_button.click()
                                    logger.info(
                                        f"Clicked '未入金予約の確認・支払へ' button using selector: {selector}"
                                    )

                                    await page.wait_for_load_state(
                                        'networkidle',
                                        timeout=30000)
                                    await page.wait_for_timeout(2000)
                                    payment_button_clicked = True
                                    logger.info(
                                        "Successfully clicked '未入金予約の確認・支払へ' button - navigated to payment page"
                                    )

                                    # After clicking payment button, check if we're on the payment page
                                    # and click "もどる" (Back) button to return to home page
                                    await page.wait_for_load_state(
                                        'networkidle',
                                        timeout=30000)
                                    await page.wait_for_timeout(2000)
                                    current_url_after_payment = page.url
                                    page_title_after_payment = await page.title(
                                    )

                                    if 'rsvWRsvGetNotPaymentRsvDataListAction' in current_url_after_payment or 'rsvWCreditInitListAction' in current_url_after_payment or '未入金予約の確認・支払' in page_title_after_payment:
                                        logger.info(
                                            "Detected payment page - clicking 'もどる' (Back) button to return to home page..."
                                        )

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
                                                back_button = await page.query_selector(
                                                    back_selector)
                                                if back_button:
                                                    # Verify this is the back button by checking onclick or text
                                                    button_onclick = await back_button.get_attribute(
                                                        'onclick'
                                                    ) or ''
                                                    button_text = await back_button.inner_text(
                                                    )

                                                    if 'gRsvWOpeHomeAction' in button_onclick or 'もどる' in button_text:
                                                        is_disabled = await back_button.get_attribute(
                                                            'disabled'
                                                        )
                                                        if not is_disabled:
                                                            await back_button.scroll_into_view_if_needed(
                                                            )
                                                            await page.wait_for_timeout(
                                                                500
                                                            )
                                                            await back_button.click(
                                                            )
                                                            logger.info(
                                                                f"Clicked 'もどる' button using selector: {back_selector}"
                                                            )

                                                            await page.wait_for_load_state(
                                                                'networkidle',
                                                                timeout
                                                                =30000
                                                            )
                                                            await page.wait_for_timeout(
                                                                2000
                                                            )
                                                            back_button_clicked = True
                                                            logger.info(
                                                                "Successfully clicked 'もどる' button - returned to home page"
                                                            )
                                                            break
                                            except Exception as e:
                                                logger.debug(
                                                    f"Failed to click back button with selector {back_selector}: {e}"
                                                )
                                                continue

                                        if not back_button_clicked:
                                            logger.warning(
                                                "Could not find/click 'もどる' button on payment page"
                                            )

                                    break
                    except Exception as e:
                        logger.debug(
                            f"Failed to click payment button with selector {selector}: {e}"
                        )
                        continue

                if not payment_button_clicked:
                    logger.warning(
                        "Could not find/click '未入金予約の確認・支払へ' button on reservation completion page"
                    )
                
                return payment_button_clicked
            return True
        except Exception as e:
            logger.error(f"Error handling reservation completion page: {e}")
            return False

    async def extract_reservation_number(self, page: Page) -> Optional[str]:
        """Extract reservation number from completion page.
        
        Args:
            page: Playwright page object
            
        Returns:
            Reservation number string or None if not found
        """
        try:
            # Try multiple selectors for reservation number
            selectors = [
                'text=予約番号', 'text=予約番号:', '[class*="reservation"]',
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

