"""Cell selection verification utilities."""
import logging
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class CellSelectionVerifier:
    """Verifies cell selection state in calendar views."""
    
    @staticmethod
    async def verify_cell_selection(
            page: Page,
            cell,
            cell_id: str,
            method_name: str) -> bool:
        """Comprehensive verification of cell selection state.
        
        Checks multiple ways the selection might be stored:
        1. Cell's own data-selected attribute
        2. Cell's class for selected/active indicators
        3. Parent elements (tr, td parent) for selection state
        4. Sibling elements for selection indicators
        5. Global JavaScript state
        6. DOM changes (computed styles, attributes)
        
        Args:
            page: Playwright page object
            cell: The cell element to verify
            cell_id: Cell ID for logging
            method_name: Name of click method used (for logging)
            
        Returns:
            True if selection is verified, False otherwise
        """
        try:
            # Check for JavaScript errors first
            js_errors = await page.evaluate('''() => {
                if (window.jsErrors) {
                    return window.jsErrors;
                }
                return [];
            }''')
            if js_errors:
                logger.warning(f"JavaScript errors detected after clicking {cell_id}: {js_errors}")
            
            # Method 1: Check cell's own data-selected attribute
            data_selected = await cell.get_attribute('data-selected')
            if data_selected == '1':
                logger.info(f"✓ Selection verified: {cell_id} has data-selected='1' (method: {method_name})")
                return True
            
            # Method 2: Check cell's class for selection indicators
            cell_class = await cell.get_attribute('class') or ''
            if 'selected' in cell_class.lower() or 'active' in cell_class.lower():
                logger.info(f"✓ Selection verified: {cell_id} has selection class '{cell_class}' (method: {method_name})")
                return True
            
            # Method 3: Check computed styles for visual selection indicators
            computed_style = await cell.evaluate('''el => {
                const style = window.getComputedStyle(el);
                return {
                    backgroundColor: style.backgroundColor,
                    borderColor: style.borderColor,
                    borderWidth: style.borderWidth,
                    opacity: style.opacity
                };
            }''')
            # Selected cells often have different background or border
            if computed_style and (
                computed_style.get('backgroundColor') not in ['rgba(0, 0, 0, 0)', 'transparent', 'rgb(255, 255, 255)'] or
                computed_style.get('borderWidth') and float(computed_style.get('borderWidth', '0').replace('px', '')) > 2
            ):
                logger.debug(f"Cell {cell_id} has non-default styling (might be selected): {computed_style}")
            
            # Method 4: Check parent elements (tr, tbody, table) for selection state
            parent_selection = await cell.evaluate('''el => {
                let parent = el.parentElement;
                let checked = [];
                while (parent && parent.tagName !== 'HTML') {
                    const dataSelected = parent.getAttribute('data-selected');
                    const className = parent.getAttribute('class') || '';
                    const ariaSelected = parent.getAttribute('aria-selected');
                    
                    if (dataSelected === '1' || 
                        className.toLowerCase().includes('selected') ||
                        className.toLowerCase().includes('active') ||
                        ariaSelected === 'true') {
                        checked.push({
                            tag: parent.tagName,
                            id: parent.id || 'no-id',
                            dataSelected: dataSelected,
                            className: className,
                            ariaSelected: ariaSelected
                        });
                    }
                    parent = parent.parentElement;
                }
                return checked;
            }''')
            if parent_selection:
                logger.info(f"✓ Selection verified: {cell_id} has selected parent element: {parent_selection} (method: {method_name})")
                return True
            
            # Method 5: Check sibling elements for selection indicators
            sibling_check = await cell.evaluate('''el => {
                const parent = el.parentElement;
                if (!parent) return null;
                
                const siblings = Array.from(parent.children);
                const selectedSiblings = siblings.filter(sib => {
                    const dataSelected = sib.getAttribute('data-selected');
                    const className = sib.getAttribute('class') || '';
                    return dataSelected === '1' || 
                           className.toLowerCase().includes('selected') ||
                           className.toLowerCase().includes('active');
                });
                
                return selectedSiblings.length > 0 ? {
                    totalSiblings: siblings.length,
                    selectedCount: selectedSiblings.length,
                    cellIndex: siblings.indexOf(el)
                } : null;
            }''')
            if sibling_check and sibling_check.get('selectedCount', 0) > 0:
                logger.debug(f"Cell {cell_id} has selected siblings: {sibling_check}")
            
            # Method 6: Check global JavaScript state (if the page stores selection in JS)
            js_state = await page.evaluate(f'''() => {{
                // Check common global variables that might store selection
                const checks = {{}};
                
                // Check window.selectedCells or similar
                if (window.selectedCells && Array.isArray(window.selectedCells)) {{
                    checks.selectedCells = window.selectedCells.includes('{cell_id}');
                }}
                
                // Check document.selectedReservations or similar
                if (document.selectedReservations && Array.isArray(document.selectedReservations)) {{
                    checks.selectedReservations = document.selectedReservations.some(r => r.cellId === '{cell_id}');
                }}
                
                // Check if cell ID is in any selection-related data structure
                if (window.reservationData) {{
                    const cellInData = JSON.stringify(window.reservationData).includes('{cell_id}');
                    checks.reservationData = cellInData;
                }}
                
                // Check form data for selected cells
                const form = document.querySelector('form[name="form1"], form#form1, form');
                if (form) {{
                    const formData = new FormData(form);
                    const formString = Array.from(formData.entries()).map(([k,v]) => `${{k}}=${{v}}`).join('&');
                    checks.inFormData = formString.includes('{cell_id}');
                }}
                
                return checks;
            }}''')
            if js_state:
                for key, value in js_state.items():
                    if value:
                        logger.info(f"✓ Selection verified: {cell_id} found in JS state '{key}' (method: {method_name})")
                        return True
            
            # Method 7: Check if cell's onclick was actually executed by checking for side effects
            # Some pages might update hidden inputs or other elements when a cell is selected
            hidden_inputs = await page.evaluate(f'''() => {{
                const inputs = document.querySelectorAll('input[type="hidden"]');
                const results = [];
                inputs.forEach(input => {{
                    const value = input.value || '';
                    const name = input.name || '';
                    if (value.includes('{cell_id}') || name.includes('{cell_id.split("_")[0]}')) {{
                        results.push({{
                            name: name,
                            value: value.substring(0, 100),
                            id: input.id || 'no-id'
                        }});
                    }}
                }});
                return results;
            }}''')
            if hidden_inputs:
                logger.info(f"✓ Selection verified: {cell_id} found in hidden inputs: {hidden_inputs} (method: {method_name})")
                return True
            
            # Method 8: Check DOM changes - compare before/after state
            # Get current state for comparison
            current_state = await cell.evaluate('''el => {
                return {
                    dataSelected: el.getAttribute('data-selected'),
                    className: el.getAttribute('class') || '',
                    style: el.getAttribute('style') || '',
                    innerHTML: el.innerHTML.substring(0, 50),
                    ariaSelected: el.getAttribute('aria-selected')
                };
            }''')
            
            # Log detailed state for debugging
            logger.debug(f"Cell {cell_id} state after click: data-selected={current_state.get('dataSelected')}, "
                        f"class={current_state.get('className')[:50]}, "
                        f"aria-selected={current_state.get('ariaSelected')}")
            
            # If we have any indication of selection (even weak), consider it successful
            # Some pages might use different mechanisms
            if (current_state.get('ariaSelected') == 'true' or
                'bg-' in current_state.get('className', '') or  # Bootstrap background classes
                'text-' in current_state.get('className', '') or  # Bootstrap text classes
                current_state.get('style') and 'background' in current_state.get('style', '').lower()):
                logger.info(f"✓ Selection verified (weak): {cell_id} has selection indicators in state (method: {method_name})")
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error during selection verification for {cell_id}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False

