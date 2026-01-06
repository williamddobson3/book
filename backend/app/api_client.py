"""API client for Shinagawa reservation system."""
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class ShinagawaAPIClient:
    """Client for interacting with Shinagawa reservation API."""
    
    def __init__(self, cookies: Optional[Dict[str, str]] = None):
        self.base_url = settings.base_url
        self.session = requests.Session()
        self.session.headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://www.cm9.eprs.jp',
            'Referer': f'{self.base_url}/rsvWOpeUnreservedDailyAction.do',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en,en-US;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        if cookies:
            self.session.cookies.update(cookies)
    
    def update_cookies(self, cookies: Dict[str, str]):
        """Update session cookies."""
        self.session.cookies.update(cookies)
    
    def get_date_based_availability(
        self,
        area_code: str = "1400_0",
        purpose_code: str = "31000000_31011700",
        start_date: Optional[str] = None,
        days: int = 31,
        offset: int = 0,
        limit: int = 100
    ) -> Dict:
        """Get availability using date-based API endpoint.
        
        Args:
            area_code: Area and building code (e.g., "1400_0" for 品川地区すべて)
            purpose_code: Purpose code (e.g., "31000000_31011700" for テニス)
            start_date: Start date in YYYY-MM-DD format
            days: Number of days to search
            offset: Pagination offset
            limit: Maximum results to return
            
        Returns:
            JSON response with availability data
        """
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        
        url = f"{self.base_url}/rsvWOpeUnreservedSearchAjaxAction.do"
        
        data = {
            'date': 4,  # 1か月
            'daystart': start_date,
            'days': days,
            'selectAreaBcd': area_code,
            'selectIcd': '',  # Empty for all facilities
            'selectPpsClPpscd': purpose_code,
            'dayofweek': [],
            'timezone': [],
            'offset': offset,
            'limit': limit,
            'displayNo': 'prwrc2000',
            'dayofweekClearFlg': 0,
            'timezoneClearFlg': 0
        }
        
        try:
            response = self.session.post(url, data=data, timeout=settings.api_timeout)
            response.raise_for_status()
            
            # Check if response is empty
            if not response.text or not response.text.strip():
                logger.warning(f"Empty response from API for area {area_code}")
                return {'results': [], 'next': 0}
            
            # Try to parse JSON
            try:
                return response.json()
            except ValueError as e:
                logger.error(f"Invalid JSON response: {response.text[:200]}")
                return {'results': [], 'next': 0}
        except Exception as e:
            logger.error(f"Error fetching date-based availability: {e}")
            raise
    
    def get_facility_based_availability(
        self,
        bcd: str,
        icd: str,
        start_day: Optional[int] = None
    ) -> Dict:
        """Get availability using facility-based API endpoint.
        
        Args:
            bcd: Building code (e.g., "1020" for 東品川公園)
            icd: Facility code (e.g., "10200010" for 庭球場Ａ)
            start_day: Start day in YYYYMMDD format
            
        Returns:
            JSON response with calendar-style availability data
        """
        if not start_day:
            start_day = int(datetime.now().strftime("%Y%m%d"))
        
        url = f"{self.base_url}/rsvWOpeInstSrchVacantAjaxAction.do"
        
        # Note: Need to discover exact parameters from actual requests
        data = {
            'bcd': bcd,
            'icd': icd,
            'startDay': start_day,
        }
        
        try:
            response = self.session.post(url, data=data, timeout=settings.api_timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching facility-based availability: {e}")
            raise
    
    def scan_all_parks(self) -> List[Dict]:
        """Scan all target parks for availability.
        
        Returns:
            List of all available slots across all parks
        """
        all_slots = []
        
        for park in settings.target_parks:
            try:
                response = self.get_date_based_availability(
                    area_code=park['area'],
                    purpose_code="31000000_31011700"
                )
                
                if 'results' in response:
                    for slot in response['results']:
                        slot['park_name'] = park['name']
                        slot['park_priority'] = park['priority']
                        all_slots.append(slot)
                
                # Handle pagination if needed
                if 'next' in response and response['next'] > 0:
                    offset = limit = 100
                    while response.get('next', 0) > 0:
                        response = self.get_date_based_availability(
                            area_code=park['area'],
                            offset=offset,
                            limit=limit
                        )
                        if 'results' in response:
                            for slot in response['results']:
                                slot['park_name'] = park['name']
                                slot['park_priority'] = park['priority']
                                all_slots.append(slot)
                        offset += limit
                        if 'next' not in response or response['next'] == 0:
                            break
                            
            except Exception as e:
                logger.error(f"Error scanning park {park['name']}: {e}")
                continue
        
        return all_slots
    
    def normalize_slot_data(self, slot: Dict) -> Dict:
        """Normalize slot data from API response or calendar extraction to standard format.
        
        Handles both formats:
        - API format: camelCase keys (useYmd, bcdNm, sTime, etc.)
        - Calendar extraction format: snake_case keys (use_ymd, bcd_name, start_time, etc.)
        """
        # Helper to get value from either format
        def get_value(camel_key, snake_key, default=None):
            if camel_key in slot:
                return slot[camel_key]
            return slot.get(snake_key, default)
        
        # Helper to convert to int safely
        def to_int(value, default=0):
            if value is None:
                return default
            try:
                return int(value)
            except (ValueError, TypeError):
                return default
        
        return {
            'use_ymd': get_value('useYmd', 'use_ymd'),
            'bcd': slot.get('bcd'),
            'icd': slot.get('icd'),
            'bcd_name': get_value('bcdNm', 'bcd_name'),
            'icd_name': get_value('icdNm', 'icd_name'),
            'start_time': to_int(get_value('sTime', 'start_time')),
            'end_time': to_int(get_value('eTime', 'end_time')),
            'start_time_display': get_value('sJTime', 'start_time_display'),
            'end_time_display': get_value('eJTime', 'end_time_display'),
            'pps_cd': to_int(get_value('ppsCd', 'pps_cd'), 0),
            'pps_cls_cd': to_int(get_value('ppsClsCd', 'pps_cls_cd'), 0),
            'week_flg': to_int(get_value('weekFlg', 'week_flg'), 0),
            'holiday_flg': to_int(get_value('holidayFlg', 'holiday_flg'), 0),
            'field_cnt': to_int(get_value('fieldCnt', 'field_cnt'), 0),
            'park_name': slot.get('park_name'),
            'park_priority': slot.get('park_priority'),
            'raw_data': slot
        }

