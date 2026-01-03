"""Monitoring service for availability detection."""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional
import logging
from app.api_client import ShinagawaAPIClient
from app.database import AsyncSessionLocal, AvailabilitySlot, MonitoringLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MonitoringService:
    """Service for monitoring availability."""
    
    def __init__(self, api_client: ShinagawaAPIClient, browser_automation=None):
        self.api_client = api_client
        self.browser_automation = browser_automation
        self.previous_slot_keys: Set[str] = set()
        self.is_running = False
    
    def _slot_key(self, slot: Dict) -> str:
        """Create unique key for slot."""
        return f"{slot.get('use_ymd')}_{slot.get('bcd')}_{slot.get('icd')}_{slot.get('start_time')}_{slot.get('end_time')}"
    
    def _is_page_valid(self, page) -> bool:
        """Check if page is valid and not closed.
        
        Args:
            page: Playwright page object or None
            
        Returns:
            True if page is valid and can be used, False otherwise
        """
        if not page:
            return False
        try:
            # Check if page has is_closed method and if it's closed
            if hasattr(page, 'is_closed') and page.is_closed():
                return False
            # Try to access page.url to verify it's still connected
            # This will raise an exception if the context is closed
            _ = page.url
            return True
        except Exception:
            # Page or context is closed/invalid
            return False
    
    async def _get_valid_page(self, current_page=None, park_area: str = None, park_name: str = None, icd: str = None):
        """Get a valid page, creating a new one if current page is closed.
        
        Args:
            current_page: Current page object (may be None or closed)
            park_area: Area code for park (needed if creating new page)
            park_name: Park name (needed if creating new page)
            icd: Court ICD (optional, for specific court search)
            
        Returns:
            Tuple of (page, was_recreated) where was_recreated is True if a new page was created
        """
        if self._is_page_valid(current_page):
            return current_page, False
        
        # Page is invalid, need to get a new one
        logger.warning("Page is closed or invalid, getting fresh page...")
        
        # Check if browser context is also closed
        if not self.browser_automation or not self.browser_automation.context:
            logger.error("Browser context is not available - cannot get page")
            return None, False
        
        try:
            # Check if context is closed
            if hasattr(self.browser_automation.context, 'is_closed') and self.browser_automation.context.is_closed():
                logger.error("Browser context is closed - cannot get page")
                return None, False
        except Exception:
            logger.error("Browser context is invalid - cannot get page")
            return None, False
        
        # If we have park info, do a full search to get a valid page
        if park_area and park_name:
            try:
                logger.info(f"Performing full search to get valid page for {park_name}...")
                result = await self.browser_automation.search_availability_via_form(
                    area_code=park_area,
                    park_name=park_name,
                    icd=icd
                )
                new_page = result.get('page')
                if self._is_page_valid(new_page):
                    logger.info("Successfully obtained valid page from full search")
                    return new_page, True
                else:
                    logger.error("New page from search is also invalid")
                    return None, False
            except Exception as e:
                logger.error(f"Failed to get page via full search: {e}")
                return None, False
        else:
            # Try to get a new page from context
            try:
                new_page = await self.browser_automation.context.new_page()
                if self._is_page_valid(new_page):
                    logger.info("Successfully created new page from context")
                    return new_page, True
                else:
                    logger.error("New page from context is invalid")
                    return None, False
            except Exception as e:
                logger.error(f"Failed to create new page from context: {e}")
                return None, False
    
    async def scan_availability(self, session: AsyncSession) -> List[Dict]:
        """Scan all parks for current availability.
        
        Args:
            session: Database session
            
        Returns:
            List of available slots
        """
        try:
            from app.config import settings
            all_slots = []
            
            # Scan each park individually, iterating through all courts
            for park in settings.target_parks:
                try:
                    # Use browser automation to search and extract slots directly from page
                    # No API call needed - we extract data from the browser HTML
                    if self.browser_automation:
                        logger.info(f"Searching for availability at park: {park['name']}...")
                        
                        # First, search without specifying a court to get the list of available courts
                        try:
                            initial_result = await self.browser_automation.search_availability_via_form(
                                area_code=park['area'],
                                park_name=park['name']
                            )
                            
                            # Get available courts from the results page
                            page = initial_result.get('page')
                            courts = []
                            default_court_icd = None  # Track which court was shown in initial search
                            
                            if self._is_page_valid(page):
                                try:
                                    # First, detect which court is currently selected in the dropdown (default court)
                                    try:
                                        facility_select = await page.query_selector('#facility-select')
                                        if facility_select:
                                            default_court_icd = await facility_select.evaluate('el => el.value')
                                            if default_court_icd and default_court_icd != '0':
                                                logger.info(f"Detected default court from dropdown: ICD={default_court_icd}")
                                    except Exception as e:
                                        logger.debug(f"Could not detect default court from dropdown: {e}")
                                    
                                    courts = await self.browser_automation.get_available_courts_for_park(page, park['area'])
                                    logger.info(f"Found {len(courts)} courts for {park['name']}: {[c['name'] for c in courts]}")
                                except Exception as e:
                                    logger.warning(f"Failed to get courts from page: {e}, will use default")
                                    courts = []
                            else:
                                logger.warning("Initial page is invalid, will use default court")
                            
                            # If no courts found, try to get from initial search slots
                            if not courts and 'slots' in initial_result and initial_result['slots']:
                                # Extract unique courts from slots
                                court_dict = {}
                                for slot in initial_result['slots']:
                                    slot_icd = slot.get('icd')
                                    slot_icd_name = slot.get('icd_name', '')
                                    if slot_icd and slot_icd not in court_dict:
                                        court_dict[slot_icd] = slot_icd_name
                                courts = [{'icd': icd, 'name': name} for icd, name in court_dict.items()]
                                logger.info(f"Extracted {len(courts)} courts from initial search results")
                                
                                # If we extracted courts from slots and don't have default_court_icd yet, use first slot's ICD
                                if not default_court_icd and courts:
                                    default_court_icd = courts[0]['icd']
                                    logger.info(f"Using first slot's court as default: ICD={default_court_icd}")
                            
                            # If still no courts, create default court list based on park
                            if not courts:
                                # Default court pattern: {bcd}0010 for court A
                                bcd = park.get('bcd', '')
                                if bcd:
                                    default_court_icd = f"{bcd}0010"
                                    default_courts = [{'icd': default_court_icd, 'name': '庭球場Ａ'}]
                                    logger.info(f"No courts found, using default court for {park['name']}: ICD={default_court_icd}")
                                    courts = default_courts
                                else:
                                    logger.warning(f"Cannot determine default court for {park['name']} - no bcd available")
                            
                            # Store slots from initial search for the default court
                            initial_slots_for_default_court = []
                            if default_court_icd and 'slots' in initial_result:
                                for slot in initial_result['slots']:
                                    if slot.get('icd') == default_court_icd:
                                        slot['park_name'] = park['name']
                                        slot['park_priority'] = park['priority']
                                        initial_slots_for_default_court.append(slot)
                                if initial_slots_for_default_court:
                                    logger.info(f"Found {len(initial_slots_for_default_court)} slots from initial search for default court (ICD: {default_court_icd})")
                            
                            # Filter out the default court from the courts list (we already have its slots)
                            if default_court_icd:
                                courts_to_search = [c for c in courts if c['icd'] != default_court_icd]
                                logger.info(f"Skipping default court (ICD: {default_court_icd}) - already searched in initial search. Will search {len(courts_to_search)} remaining courts.")
                            else:
                                # If we couldn't detect the default court, search all courts
                                # (This should rarely happen, but handle gracefully)
                                courts_to_search = courts
                                logger.info(f"Could not detect default court from dropdown - will search all {len(courts_to_search)} courts")
                            
                            # Add initial slots for default court to all_slots
                            if initial_slots_for_default_court:
                                all_slots.extend(initial_slots_for_default_court)
                                logger.info(f"Added {len(initial_slots_for_default_court)} slots from default court to results")
                            
                            # Iterate through remaining courts (excluding the default court)
                            park_has_slots = len(initial_slots_for_default_court) > 0
                            page = initial_result.get('page')  # Keep page reference for court switching
                            
                            # Check if initial search already clicked "予約" (navigated away from search results)
                            # If so, we can't process other courts - the booking flow has already started
                            initial_search_clicked_reserve = False
                            try:
                                if page:
                                    current_url = page.url
                                    # If we're on reservation/Terms of Use/completion page, initial search already clicked "予約"
                                    if ('rsvWOpeReservedApplyAction' in current_url or 
                                        'rsvWInstUseruleRsvApplyAction' in current_url or 
                                        'rsvWInstRsvApplyAction' in current_url or
                                        '予約内容確認' in await page.title() or
                                        '予約完了' in await page.title()):
                                        initial_search_clicked_reserve = True
                                        logger.info(f"Initial search for {park['name']} already clicked '予約' - booking flow in progress, skipping other courts")
                            except Exception as e:
                                logger.debug(f"Error checking if initial search clicked '予約': {e}")
                            
                            # Track slots and flags across ALL courts for this park
                            # We will click "予約" only AFTER processing all courts (unless initial search already did)
                            park_all_slots = list(initial_slots_for_default_court) if initial_slots_for_default_court else []  # Start with default court slots
                            park_slots_clicked_flag = 0  # Track if ANY court had slots clicked
                            
                            # If initial search had slots clicked, we need to check if slots_clicked_flag was set
                            # Note: search_availability_via_form doesn't return slots_clicked_flag, but if it clicked "予約",
                            # that means slots were found and clicked. However, if we're still on search results page,
                            # slots might have been clicked but "予約" wasn't clicked yet (if flag was 0 or button wasn't found)
                            # For now, we'll assume that if we have slots from initial search, they were clicked
                            if initial_slots_for_default_court:
                                # If we have slots from initial search and we're still on search results page,
                                # it means slots were clicked but "予約" wasn't clicked (or wasn't found)
                                if not initial_search_clicked_reserve:
                                    park_slots_clicked_flag = 1
                                    logger.info(f"Initial search for {park['name']} found and clicked slots - will include in final '予約' click")
                            
                            # Only process other courts if initial search didn't already click "予約"
                            if not initial_search_clicked_reserve:
                                for court_index, court in enumerate(courts_to_search):
                                    court_icd = court['icd']
                                    court_name = court['name']
                                    logger.info(f"Searching court {court_name} (ICD: {court_icd}) at {park['name']}... (court {court_index + 1} of {len(courts_to_search)})")
                                    
                                    try:
                                        # Validate page before using it
                                        page, was_recreated = await self._get_valid_page(
                                            current_page=page,
                                            park_area=park['area'],
                                            park_name=park['name'],
                                            icd=court_icd if not self._is_page_valid(page) else None
                                        )
                                        
                                        if not page:
                                            logger.error(f"Cannot get valid page for court {court_name} - skipping")
                                            continue
                                        
                                        # Change court using dropdown (much faster than full search)
                                        if not self._is_page_valid(page):
                                            # Page lost, need to do full search
                                            logger.warning(f"Page lost, doing full search for court {court_name}...")
                                            result = await self.browser_automation.search_availability_via_form(
                                                area_code=park['area'],
                                                park_name=park['name'],
                                                icd=court_icd
                                            )
                                            page = result.get('page')
                                        else:
                                            # Change court using dropdown (much faster than full search)
                                            logger.info(f"Changing to court {court_name} (ICD: {court_icd}) using dropdown...")
                                            try:
                                                # Wait for facility dropdown in results page
                                                await page.wait_for_selector('#facility-select', state='visible', timeout=10000)
                                                await page.select_option('#facility-select', value=court_icd)
                                                await page.wait_for_timeout(2000)  # Wait for calendar to update
                                                
                                                # Wait for AJAX to reload calendar
                                                try:
                                                    loading_indicator = await page.query_selector('#loadingweek')
                                                    if loading_indicator:
                                                        await page.wait_for_function(
                                                            'document.getElementById("loadingweek") === null || window.getComputedStyle(document.getElementById("loadingweek")).display === "none"',
                                                            timeout=30000
                                                        )
                                                except:
                                                    pass
                                                
                                                await page.wait_for_load_state('networkidle', timeout=30000)
                                                await page.wait_for_timeout(2000)
                                                logger.info(f"Court {court_icd} selected in results page, calendar should be updated")
                                                
                                                # Extract slots for this court
                                                # _extract_slots_from_weekly_calendar returns (slots, slots_clicked_flag) tuple
                                                slots, slots_clicked_flag = await self.browser_automation._extract_slots_from_weekly_calendar(page)
                                                result = {'success': True, 'slots': slots, 'page': page, 'slots_clicked_flag': slots_clicked_flag}
                                                
                                                # Collect slots from this court (don't click "予約" yet)
                                                if 'slots' in result and result['slots']:
                                                    for slot in result['slots']:
                                                        slot['park_name'] = park['name']
                                                        slot['park_priority'] = park['priority']
                                                        park_all_slots.append(slot)
                                                    logger.info(f"Found {len(result['slots'])} available slots for {park['name']} - {court_name}")
                                                    park_has_slots = True
                                                
                                                # Track if any slots were clicked (but don't click "予約" yet - wait until all courts are processed)
                                                if slots_clicked_flag == 1:
                                                    park_slots_clicked_flag = 1
                                                    logger.info(f"Slots clicked for court {court_name} - will click '予約' after processing all courts in {park['name']}")
                                                
                                                # DO NOT click "予約" here - continue to next court
                                                
                                            except Exception as e:
                                                logger.error(f"Failed to change court using dropdown: {e}, trying full search instead...")
                                                import traceback
                                                logger.error(traceback.format_exc())
                                                # Fallback to full search if dropdown fails
                                                result = await self.browser_automation.search_availability_via_form(
                                                    area_code=park['area'],
                                                    park_name=park['name'],
                                                    icd=court_icd
                                                )
                                                page = result.get('page')
                                        
                                        # Extract slots from browser page (for fallback full search case)
                                        if 'slots' in result and result['slots']:
                                            for slot in result['slots']:
                                                slot['park_name'] = park['name']
                                                slot['park_priority'] = park['priority']
                                                if slot not in park_all_slots:  # Avoid duplicates
                                                    park_all_slots.append(slot)
                                            logger.info(f"Found {len(result['slots'])} available slots for {park['name']} - {court_name}")
                                            park_has_slots = True
                                        
                                        # Track slots_clicked_flag from result (for fallback full search case)
                                        if 'slots_clicked_flag' in result and result['slots_clicked_flag'] == 1:
                                            park_slots_clicked_flag = 1
                                            logger.info(f"Slots clicked for court {court_name} (from full search) - will click '予約' after processing all courts")
                                        
                                        # Update page reference from result if available
                                        if 'page' in result:
                                            page = result.get('page')
                                        
                                        # Continue to next court (don't break here)
                                        
                                    except Exception as e:
                                        logger.error(f"Error processing court {court_name}: {e}")
                                        import traceback
                                        logger.error(traceback.format_exc())
                                        continue  # Continue to next court even if this one fails
                            else:
                                logger.info(f"Skipping other courts for {park['name']} - initial search already started booking flow")
                            
                            # After processing ALL courts for this park, click "予約" if any slots were clicked
                            # (Only if initial search didn't already click it)
                            if park_slots_clicked_flag == 1:
                                logger.info(f"Finished processing all courts for {park['name']} - found {len(park_all_slots)} total slots. Clicking '予約' button for all selected slots...")
                                
                                # Ensure we're still on the search results page (not navigated away)
                                try:
                                    current_url = page.url
                                    if 'rsvWOpeInstSrchVacantAction' not in current_url and 'rsvWOpeUnreservedDailyAction' not in current_url:
                                        logger.warning(f"Not on search results page (URL: {current_url}) - cannot click '予約' button. May need to re-search.")
                                        # Try to get back to search results page
                                        # For now, just log and continue
                                    else:
                                        # We're on the search results page - click "予約" button
                                        button_clicked = await self.browser_automation.click_reservation_button_if_slots_found(
                                            page, park_slots_clicked_flag, park_all_slots
                                        )
                                        if button_clicked:
                                            logger.info(f"Successfully clicked '予約' button for {park['name']} after processing all courts")
                                            
                                            # Check if we're on reservation completion page or home page after booking - if so, move to next park
                                            try:
                                                await page.wait_for_load_state('networkidle', timeout=30000)
                                                await page.wait_for_timeout(2000)
                                                current_url = page.url
                                                page_title = await page.title()
                                                # Check for completion page, payment page, or home page (after clicking もどる)
                                                if ('rsvWInstRsvApplyAction' in current_url or 
                                                    '予約完了' in page_title or 
                                                    'rsvWCreditInitListAction' in current_url or
                                                    'rsvWRsvGetNotPaymentRsvDataListAction' in current_url or
                                                    'rsvWOpeHomeAction' in current_url or
                                                    'ホーム画面' in page_title):
                                                    logger.info(f"Reservation completed for {park['name']} - booking finished. Moving to next park.")
                                                    park_has_slots = True  # Mark park as having slots (booking was successful)
                                                else:
                                                    logger.info(f"Still on search/reservation page after clicking '予約' - continuing normally")
                                            except Exception as e:
                                                logger.warning(f"Error checking page state after booking: {e}, continuing...")
                                        else:
                                            logger.warning(f"Failed to click '予約' button for {park['name']}")
                                except Exception as e:
                                    logger.warning(f"Error checking page state before clicking '予約': {e}, continuing...")
                            
                            # Add all collected slots from this park to the overall results
                            for slot in park_all_slots:
                                if slot not in all_slots:  # Avoid duplicates
                                    all_slots.append(slot)
                            
                            logger.info(f"Completed processing all courts for {park['name']} - found {len(park_all_slots)} total slots across all courts")
                            
                            if not park_has_slots:
                                logger.info(f"No available slots found in any court for {park['name']}")
                            else:
                                logger.info(f"Found slots in at least one court for {park['name']}")
                                
                        except Exception as e:
                            logger.error(f"Failed to search availability for {park['name']}: {e}")
                            continue
                    else:
                        logger.warning("Browser automation not available - cannot search for availability")
                        continue
                                
                except Exception as e:
                    logger.error(f"Error scanning park {park['name']}: {e}")
                    continue
            
            # Normalize and filter available slots
            available_slots = []
            current_keys = set()
            
            for slot_raw in all_slots:
                # Only include slots with fieldCnt = 0 (available)
                if slot_raw.get('fieldCnt', -1) == 0:
                    slot = self.api_client.normalize_slot_data(slot_raw)
                    slot_key = self._slot_key(slot)
                    current_keys.add(slot_key)
                    available_slots.append(slot)
            
            # Store in database
            stored_slots = await self._store_availability(session, available_slots)
            
            # Log monitoring
            await self._log_scan(session, len(available_slots))
            
            self.previous_slot_keys = current_keys
            return stored_slots
            
        except Exception as e:
            logger.error(f"Error scanning availability: {e}")
            raise
    
    async def detect_new_availability(self, session: AsyncSession) -> List[Dict]:
        """Detect newly available slots.
        
        Args:
            session: Database session
            
        Returns:
            List of newly detected slots
        """
        current_slots = await self.scan_availability(session)
        current_keys = {self._slot_key(s) for s in current_slots}
        
        # Find new slots
        new_keys = current_keys - self.previous_slot_keys
        new_slots = [s for s in current_slots if self._slot_key(s) in new_keys]
        
        if new_slots:
            logger.info(f"Detected {len(new_slots)} new available slots")
            await self._log_new_slots(session, new_slots)
        
        return new_slots
    
    async def _store_availability(self, session: AsyncSession, slots: List[Dict]) -> List[Dict]:
        """Store availability slots in database."""
        stored_slots = []
        for slot_data in slots:
            # Check if slot already exists
            stmt = select(AvailabilitySlot).where(
                AvailabilitySlot.use_ymd == slot_data['use_ymd'],
                AvailabilitySlot.bcd == slot_data['bcd'],
                AvailabilitySlot.icd == slot_data['icd'],
                AvailabilitySlot.start_time == slot_data['start_time']
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing
                existing.status = 'available'
                existing.updated_at = datetime.utcnow()
                existing.detected_at = datetime.utcnow()
                slot_data['id'] = existing.id
            else:
                # Create new
                db_slot = AvailabilitySlot(
                    use_ymd=slot_data['use_ymd'],
                    bcd=slot_data['bcd'],
                    icd=slot_data['icd'],
                    bcd_name=slot_data['bcd_name'],
                    icd_name=slot_data['icd_name'],
                    start_time=slot_data['start_time'],
                    end_time=slot_data['end_time'],
                    start_time_display=slot_data['start_time_display'],
                    end_time_display=slot_data['end_time_display'],
                    pps_cd=slot_data['pps_cd'],
                    pps_cls_cd=slot_data['pps_cls_cd'],
                    week_flg=slot_data['week_flg'],
                    holiday_flg=slot_data['holiday_flg'],
                    field_cnt=slot_data['field_cnt'],
                    status='available'
                )
                session.add(db_slot)
                await session.flush()
                slot_data['id'] = db_slot.id
            
            stored_slots.append(slot_data)
        
        await session.commit()
        return stored_slots
    
    async def _log_scan(self, session: AsyncSession, slot_count: int):
        """Log scan activity."""
        log = MonitoringLog(
            log_type='scan',
            message=f'Scanned availability: {slot_count} slots found',
            data={'slot_count': slot_count},
            success=True
        )
        session.add(log)
        await session.commit()
    
    async def _log_new_slots(self, session: AsyncSession, slots: List[Dict]):
        """Log newly detected slots."""
        log = MonitoringLog(
            log_type='detection',
            message=f'Detected {len(slots)} new available slots',
            data={'slots': slots},
            success=True
        )
        session.add(log)
        await session.commit()
    
    async def get_available_slots_from_db(
        self,
        session: AsyncSession,
        park_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> List[AvailabilitySlot]:
        """Get available slots from database with filters."""
        stmt = select(AvailabilitySlot).where(AvailabilitySlot.status == 'available')
        
        if park_name:
            stmt = stmt.where(AvailabilitySlot.bcd_name.contains(park_name))
        
        if date_from:
            date_from_int = int(date_from.strftime('%Y%m%d'))
            stmt = stmt.where(AvailabilitySlot.use_ymd >= date_from_int)
        
        if date_to:
            date_to_int = int(date_to.strftime('%Y%m%d'))
            stmt = stmt.where(AvailabilitySlot.use_ymd <= date_to_int)
        
        stmt = stmt.order_by(AvailabilitySlot.use_ymd, AvailabilitySlot.start_time)
        
        result = await session.execute(stmt)
        return list(result.scalars().all())

