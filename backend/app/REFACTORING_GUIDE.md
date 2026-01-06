# Browser Automation Refactoring Guide

## Overview

The `browser_automation.py` file (4882 lines) has been **fully componentized** into smaller, focused modules for better maintainability and testability.

## ✅ Completed Component Structure

### 1. `browser_session.py` - Browser Session Management
**Purpose**: Manages browser lifecycle (start/stop) and session state.

**Key Classes**:
- `BrowserSession`: Handles browser initialization, context creation, and page management

**Key Methods**:
- `start()`: Initialize browser with realistic settings
- `stop()`: Clean up browser resources
- `create_page()`: Create new page in context
- `get_or_create_page()`: Get or create main page

### 2. `login_handler.py` - Authentication
**Purpose**: Handles user login flow.

**Key Classes**:
- `LoginHandler`: Manages login process

**Key Methods**:
- `login()`: Main login method
- `_click_login_button()`: Navigate to login page
- `_wait_for_login_form()`: Wait for form elements
- `_fill_login_form()`: Fill credentials
- `_verify_login_success()`: Verify login and return cookies

### 3. `form_utils.py` - Form Filling Utilities
**Purpose**: Reusable utilities for filling forms.

**Key Classes**:
- `FormUtils`: Static utility methods for form operations

**Key Methods**:
- `fill_user_count_inputs()`: Fill "利用人数" fields
- `select_date_option()`: Select date option (1か月, etc.)
- `select_park()`: Select park from dropdown
- `select_activity()`: Select activity (テニス)
- `click_search_button()`: Click search button

### 4. `calendar_navigator.py` - Calendar Navigation
**Purpose**: Handles navigation through weekly calendar views.

**Key Classes**:
- `CalendarNavigator`: Static methods for calendar navigation

**Key Methods**:
- `is_on_week_one()`: Check if currently on week 1
- `navigate_back_to_week_one()`: Navigate backwards to week 1
- `navigate_to_next_week()`: Navigate to next week
- `navigate_to_previous_week()`: Navigate to previous week

### 5. ✅ `cell_selection_verifier.py` - Cell Selection Verification
**Purpose**: Verifies cell selection state in calendar views.

**Key Classes**:
- `CellSelectionVerifier`: Static methods for verifying cell selection

**Key Methods**:
- `verify_cell_selection()`: Comprehensive verification of cell selection state
  - Checks data-selected attribute
  - Checks CSS classes
  - Checks computed styles
  - Checks parent/sibling elements
  - Checks global JavaScript state
  - Checks hidden form inputs
  - Checks DOM changes

### 6. ✅ `results_checker.py` - Results Checking
**Purpose**: Checks if search results are available on the page.

**Key Classes**:
- `ResultsChecker`: Static methods for checking results

**Key Methods**:
- `check_results_available()`: Check if results are available
  - Verifies div visibility (#unreserved-notfound, #unreserved-list)
  - Checks for reservation buttons
  - Returns tuple of (has_results, has_reservation_buttons)

### 7. ✅ `slot_extractor.py` - Slot Extraction
**Purpose**: Extracts available slots from calendar views and pages.

**Key Classes**:
- `SlotExtractor`: Handles slot extraction from calendar

**Key Methods**:
- `extract_slots_from_current_week()`: Extract slots from current week
- `extract_slots_from_weekly_calendar()`: Extract slots from all 6 weeks (forward and backward)
- `extract_slots_from_page()`: Extract slots from results page

### 8. ✅ `booking_handler.py` - Booking Flow
**Purpose**: Handles the complete booking/reservation flow.

**Key Classes**:
- `BookingHandler`: Handles booking operations

**Key Methods**:
- `click_reservation_button_if_slots_found()`: Click '予約' button if slots found
- `_handle_terms_of_use_page()`: Handle Terms of Use agreement
- `_handle_reservation_confirmation_page()`: Handle reservation confirmation (fill user count, click final reserve)
- `_handle_reservation_completion_page()`: Handle completion page (payment button, back button)
- `extract_reservation_number()`: Extract reservation number from completion page

### 9. ✅ `search_handler.py` - Search Operations
**Purpose**: Handles complete search operations for availability.

**Key Classes**:
- `SearchHandler`: Handles search operations

**Key Methods**:
- `search_availability_via_form()`: Complete search via form
- `change_park_and_search()`: Change park and search again
- `_expand_search_form_if_collapsed()`: Expand search form if collapsed
- `_ensure_facility_tab_active()`: Ensure '施設ごと' tab is active
- `_click_load_more_button()`: Click 'さらに表示' button
- `_select_court_in_results_page()`: Select court in results page

## ✅ Refactored `browser_automation.py`

The main `BrowserAutomation` class now:
- Uses `BrowserSession` for session management
- Uses `LoginHandler` for login operations
- Uses `SearchHandler` for search operations
- Uses `SlotExtractor` for slot extraction
- Uses `BookingHandler` for booking operations
- **Maintains full backward compatibility** - all public methods work the same way

**Key Features**:
- All original public methods are preserved
- Internal methods delegate to components
- Backward compatible with existing code
- Reduced from 4882 lines to ~600 lines (87% reduction)

## Usage Example

### Using Components Directly

```python
from app.browser_session import BrowserSession
from app.login_handler import LoginHandler
from app.form_utils import FormUtils
from app.calendar_navigator import CalendarNavigator
from app.search_handler import SearchHandler
from app.slot_extractor import SlotExtractor

# Initialize session
session = BrowserSession()
await session.start()

# Login
main_page_ref = {'main_page': None}
login_handler = LoginHandler(session.context, main_page_ref)
cookies = await login_handler.login()
session.main_page = main_page_ref['main_page']

# Use form utilities
page = session.main_page
await FormUtils.select_date_option(page)
await FormUtils.select_park(page, "1200_1040")
await FormUtils.select_activity(page)
await FormUtils.click_search_button(page)

# Navigate calendar
if not await CalendarNavigator.is_on_week_one(page):
    await CalendarNavigator.navigate_back_to_week_one(page)

await CalendarNavigator.navigate_to_next_week(page)

# Use search handler
search_handler = SearchHandler(main_page=page)
result = await search_handler.search_availability_via_form(
    page, "1200_1040", park_name="しながわ区民公園", click_reserve_button=False
)

# Use slot extractor
slot_extractor = SlotExtractor()
slots, flag = await slot_extractor.extract_slots_from_weekly_calendar(page)
```

### Using BrowserAutomation (Backward Compatible)

```python
from app.browser_automation import BrowserAutomation

# Initialize (same as before)
browser = BrowserAutomation()
await browser.start()
cookies = await browser.login()

# Search (same API as before)
result = await browser.search_availability_via_form(
    "1200_1040", park_name="しながわ区民公園", click_reserve_button=False
)

# All original methods still work
courts = await browser.get_available_courts_for_park(browser.main_page, "1200_1040")
await browser.change_park_and_search("1400_1010", "しながわ中央公園")
```

## Benefits

1. **Maintainability**: Reduced from 4882 lines to ~600 lines (87% reduction). Smaller, focused files are easier to understand and modify
2. **Testability**: Components can be tested independently
3. **Reusability**: Utilities can be reused across different handlers
4. **Separation of Concerns**: Each module has a single responsibility
5. **Easier Debugging**: Issues can be isolated to specific components
6. **Better Organization**: Related functionality is grouped together
7. **Easier to Extend**: New features can be added to specific components without touching others

## Backward Compatibility

✅ **The refactored `BrowserAutomation` class maintains the same public API**, ensuring backward compatibility with existing code that uses it.

All existing code using `BrowserAutomation` will continue to work without any changes:
- `browser.start()`
- `browser.stop()`
- `browser.login()`
- `browser.search_availability_via_form()`
- `browser.book_slot()`
- `browser.change_park_and_search()`
- `browser.get_available_courts_for_park()`
- All internal methods (prefixed with `_`) are still available for backward compatibility

## File Size Comparison

| File | Lines | Purpose |
|------|-------|---------|
| `browser_automation.py` (original) | 4882 | Monolithic file |
| `browser_automation.py` (refactored) | ~600 | Orchestrator using components |
| `browser_session.py` | ~100 | Session management |
| `login_handler.py` | ~200 | Login operations |
| `form_utils.py` | ~250 | Form utilities |
| `calendar_navigator.py` | ~230 | Calendar navigation |
| `cell_selection_verifier.py` | ~200 | Cell selection verification |
| `results_checker.py` | ~150 | Results checking |
| `slot_extractor.py` | ~500 | Slot extraction |
| `booking_handler.py` | ~400 | Booking flow |
| `search_handler.py` | ~400 | Search operations |
| **Total** | **~3030** | **Well-organized, maintainable code** |

**Reduction**: 4882 → ~600 lines in main file (87% reduction)
**Total**: Better organized across 10 focused modules

