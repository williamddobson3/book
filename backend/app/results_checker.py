"""Results checking utilities for search pages."""
import logging
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class ResultsChecker:
    """Checks if search results are available on the page."""
    
    @staticmethod
    async def check_results_available(page: Page) -> tuple[bool, bool]:
        """Check if results are available on the search results page.
        
        Args:
            page: Playwright page object
            
        Returns:
            Tuple of (has_results, has_reservation_buttons)
            - has_results: True if results div is visible
            - has_reservation_buttons: True if reservation buttons are found
        """
        has_results = False
        has_reservation_buttons = False

        try:
            # CRITICAL: Check actual div visibility first (not just text content)
            # The divs can have text content but be hidden with style="display: none;"
            no_results_div = await page.query_selector('#unreserved-notfound')
            results_list_div = await page.query_selector('#unreserved-list')

            # Check #unreserved-notfound visibility first (highest priority)
            if no_results_div:
                no_results_visible = await no_results_div.evaluate(
                    'el => window.getComputedStyle(el).display !== "none"'
                )
                if no_results_visible:
                    logger.info(
                        "No results found - #unreserved-notfound is visible (display: block)"
                    )
                    has_results = False
                    # Don't check anything else - this is definitive
                else:
                    # #unreserved-notfound exists but is hidden, check #unreserved-list
                    if results_list_div:
                        results_list_visible = await results_list_div.evaluate(
                            'el => window.getComputedStyle(el).display !== "none"'
                        )
                        if results_list_visible:
                            logger.info(
                                "Results found - #unreserved-list is visible (display: block)"
                            )
                            has_results = True
                        else:
                            logger.info(
                                "Both divs exist but both are hidden - checking buttons as fallback"
                            )
                            # Both divs exist but both hidden - check buttons
                            reservation_buttons_check = await page.query_selector_all(
                                'button:has-text("予約"), td.reservation button.btn-go'
                            )
                            has_reservation_buttons = len(
                                reservation_buttons_check) > 0
                            if has_reservation_buttons:
                                logger.info(
                                    f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results"
                                )
                                has_results = True
                            else:
                                logger.info(
                                    "No reservation buttons found - treating as no results"
                                )
                                has_results = False
                    else:
                        # #unreserved-notfound exists but hidden, and #unreserved-list doesn't exist
                        logger.info(
                            "#unreserved-notfound exists but hidden, #unreserved-list not found - checking buttons"
                        )
                        reservation_buttons_check = await page.query_selector_all(
                            'button:has-text("予約"), td.reservation button.btn-go'
                        )
                        has_reservation_buttons = len(
                            reservation_buttons_check) > 0
                        if has_reservation_buttons:
                            logger.info(
                                f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results"
                            )
                            has_results = True
                        else:
                            has_results = False
            else:
                # #unreserved-notfound doesn't exist, check #unreserved-list
                if results_list_div:
                    results_list_visible = await results_list_div.evaluate(
                        'el => window.getComputedStyle(el).display !== "none"'
                    )
                    if results_list_visible:
                        logger.info(
                            "Results found - #unreserved-list is visible (display: block)"
                        )
                        has_results = True
                    else:
                        logger.info(
                            "#unreserved-list exists but is hidden - checking buttons"
                        )
                        reservation_buttons_check = await page.query_selector_all(
                            'button:has-text("予約"), td.reservation button.btn-go'
                        )
                        has_reservation_buttons = len(
                            reservation_buttons_check) > 0
                        if has_reservation_buttons:
                            logger.info(
                                f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results"
                            )
                            has_results = True
                        else:
                            has_results = False
                else:
                    # Neither div exists - check buttons as fallback
                    logger.info(
                        "Neither div found - checking buttons as fallback"
                    )
                    reservation_buttons_check = await page.query_selector_all(
                        'button:has-text("予約"), td.reservation button.btn-go'
                    )
                    has_reservation_buttons = len(
                        reservation_buttons_check) > 0
                    if has_reservation_buttons:
                        logger.info(
                            f"Found {len(reservation_buttons_check)} [予約] buttons - treating as has results"
                        )
                        has_results = True
                    else:
                        has_results = False

            # If we still don't have reservation buttons but have results, check for them
            if has_results and not has_reservation_buttons:
                reservation_buttons_check = await page.query_selector_all(
                    'button:has-text("予約"), td.reservation button.btn-go'
                )
                has_reservation_buttons = len(
                    reservation_buttons_check) > 0
                if has_reservation_buttons:
                    logger.info(
                        f"Found {len(reservation_buttons_check)} [予約] buttons"
                    )

        except Exception as e:
            logger.warning(f"Error checking for results: {e}")
            import traceback
            logger.warning(traceback.format_exc())
            has_results = False

        # Log the final detection result
        if has_results:
            logger.info(
                f"Results detected - bookable dates found, do NOT click '条件変更'"
            )
        else:
            logger.warning(
                f"No results detected - should click '条件変更' to try another park. "
                f"Debug info: no_results_div exists={no_results_div is not None}, "
                f"results_list_div exists={results_list_div is not None}"
            )

        return has_results, has_reservation_buttons

