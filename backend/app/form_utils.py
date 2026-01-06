"""Form filling utilities."""
from playwright.async_api import Page
from typing import List
import logging

logger = logging.getLogger(__name__)


class FormUtils:
    """Utilities for filling forms."""
    
    @staticmethod
    async def fill_user_count_inputs(page: Page, default_user_count: int = 2) -> int:
        """
        Fill all "利用人数" (Number of Users) input fields on the page.
        
        Args:
            page: Playwright page object
            default_user_count: Number of users to fill (default: 2)
            
        Returns:
            Number of input fields filled
        """
        user_count_inputs = []
        
        # Strategy 1: Direct selectors
        direct_selectors = [
            'input[name="applyNum"]',
            'input[id^="peoples"]',
            'input[name*="applyNum"]',
            'input[type="tel"][name*="applyNum"]',
        ]
        
        for selector in direct_selectors:
            try:
                inputs = await page.query_selector_all(selector)
                if inputs:
                    for inp in inputs:
                        inp_id = await inp.get_attribute('id') or ''
                        inp_name = await inp.get_attribute('name') or ''
                        inp_key = f"{inp_id}_{inp_name}"
                        
                        # Check for duplicates
                        already_added = False
                        for existing in user_count_inputs:
                            existing_id = await existing.get_attribute('id') or ''
                            existing_name = await existing.get_attribute('name') or ''
                            if f"{existing_id}_{existing_name}" == inp_key:
                                already_added = True
                                break
                        
                        if not already_added:
                            user_count_inputs.append(inp)
                    
                    if user_count_inputs:
                        logger.info(f"Found {len(user_count_inputs)} '利用人数' input field(s) using direct selector: {selector}")
                        break
            except Exception as e:
                logger.debug(f"Error finding inputs with direct selector {selector}: {e}")
                continue
        
        # Strategy 2: Find by labels
        if not user_count_inputs:
            try:
                labels_with_text = await page.query_selector_all(
                    'label:has-text("利用人数"), td:has-text("利用人数"), div:has-text("利用人数")'
                )
                
                for label_element in labels_with_text:
                    try:
                        label_for = await label_element.get_attribute('for')
                        if label_for:
                            associated_input = await page.query_selector(
                                f'input#{label_for}, input[name="{label_for}"]'
                            )
                            if associated_input:
                                inp_id = await associated_input.get_attribute('id') or ''
                                inp_name = await associated_input.get_attribute('name') or ''
                                inp_key = f"{inp_id}_{inp_name}"
                                
                                already_added = False
                                for existing in user_count_inputs:
                                    existing_id = await existing.get_attribute('id') or ''
                                    existing_name = await existing.get_attribute('name') or ''
                                    if f"{existing_id}_{existing_name}" == inp_key:
                                        already_added = True
                                        break
                                
                                if not already_added:
                                    user_count_inputs.append(associated_input)
                                continue
                    except Exception as e:
                        logger.debug(f"Error processing label element: {e}")
                        continue
            except Exception as e:
                logger.debug(f"Error finding labels with '利用人数' text: {e}")
        
        # Fill all found inputs
        filled_count = 0
        if user_count_inputs:
            logger.info(f"Found {len(user_count_inputs)} '利用人数' input field(s) - filling with {default_user_count} users each...")
            for idx, user_input in enumerate(user_count_inputs, 1):
                try:
                    inp_id = await user_input.get_attribute('id') or ''
                    inp_name = await user_input.get_attribute('name') or ''
                    
                    if inp_id:
                        selector = f'input#{inp_id}'
                    elif inp_name:
                        selector = f'input[name="{inp_name}"]'
                    else:
                        await user_input.fill(str(default_user_count))
                        await page.wait_for_timeout(200)
                        logger.info(f"Filled '利用人数' field {idx} with {default_user_count} users (direct fill)")
                        filled_count += 1
                        continue
                    
                    await page.fill(selector, str(default_user_count))
                    await page.wait_for_timeout(200)
                    logger.info(f"Filled '利用人数' field {idx} (id={inp_id}, name={inp_name}) with {default_user_count} users")
                    filled_count += 1
                except Exception as e:
                    logger.warning(f"Failed to fill user count input {idx}: {e}")
                    try:
                        await user_input.fill(str(default_user_count))
                        await page.wait_for_timeout(200)
                        logger.info(f"Filled '利用人数' field {idx} with {default_user_count} users (fallback direct fill)")
                        filled_count += 1
                    except Exception as e2:
                        logger.warning(f"Fallback fill also failed for input {idx}: {e2}")
        else:
            logger.warning("Could not find '利用人数' input fields - proceeding without filling user count")
        
        return filled_count
    
    @staticmethod
    async def select_date_option(page: Page, option: str = "1か月"):
        """Select date option (1か月, etc.)."""
        logger.info(f"Selecting '{option}' date option...")
        try:
            await page.wait_for_selector(
                'label.btn.radiobtn[for="thismonth"]',
                state='visible',
                timeout=30000)
            await page.click('label.btn.radiobtn[for="thismonth"]')
            await page.wait_for_timeout(1000)
            logger.info("Selected '1 month' date option via label")
        except Exception as e:
            logger.warning(f"Could not select '1 month' label: {e}, trying alternatives...")
            alternatives = [
                'label[for="thismonth"]',
                'label:has-text("1か月")',
                'input#thismonth',
                'input[name="date"][value="4"]'
            ]
            selected = False
            for selector in alternatives:
                try:
                    await page.wait_for_selector(selector, state='visible', timeout=5000)
                    await page.click(selector)
                    await page.wait_for_timeout(1000)
                    logger.info(f"Selected '1 month' using alternative selector: {selector}")
                    selected = True
                    break
                except:
                    continue
            if not selected:
                logger.error("Failed to select date option with all selectors")
                raise
    
    @staticmethod
    async def select_park(page: Page, area_code: str):
        """Select park from dropdown."""
        logger.info(f"Selecting park (area_code: {area_code})...")
        selectors = [
            'select[name*="bcd"]', 'select#bname',
            'select[name*="area"]', 'select[name*="どこ"]'
        ]
        
        dropdown_found = False
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await page.select_option(selector, value=area_code)
                    await page.wait_for_timeout(1000)
                    dropdown_found = True
                    logger.info(f"Selected park using selector: {selector}")
                    break
            except:
                continue
        
        if not dropdown_found:
            raise Exception("Could not find park dropdown")
    
    @staticmethod
    async def select_activity(page: Page, activity_value: str = '31000000_31011700'):
        """Select activity (テニス)."""
        logger.info("Selecting 'テニス' (Tennis) activity...")
        selectors = [
            'select[name*="purpose"]', 'select#purpose',
            'select[name*="何"]'
        ]
        
        dropdown_found = False
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await page.select_option(selector, value=activity_value)
                    await page.wait_for_timeout(1000)
                    dropdown_found = True
                    logger.info(f"Selected Tennis using selector: {selector}")
                    break
            except:
                continue
        
        if not dropdown_found:
            raise Exception("Could not find activity dropdown")
    
    @staticmethod
    async def click_search_button(page: Page):
        """Click search button."""
        logger.info("Clicking search button...")
        try:
            await page.click('button:has-text("検索")')
            await page.wait_for_load_state('networkidle', timeout=120000)
        except Exception:
            search_selectors = [
                'button:has-text("検索")',
                'input[type="submit"][value*="検索"]',
                'button[type="submit"]', '#btn-search'
            ]
            
            button_found = False
            for selector in search_selectors:
                try:
                    await page.wait_for_selector(selector, state='visible', timeout=10000)
                    await page.click(selector)
                    await page.wait_for_load_state('networkidle', timeout=120000)
                    button_found = True
                    logger.info(f"Clicked search button using selector: {selector}")
                    break
                except:
                    continue
            
            if not button_found:
                raise Exception("Could not find search button")
            
            await page.wait_for_load_state('networkidle', timeout=120000)
            await page.wait_for_timeout(2000)

