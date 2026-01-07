"""Network capture utility for API reverse engineering."""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from playwright.async_api import Page
from urllib.parse import parse_qs, unquote

logger = logging.getLogger(__name__)


class NetworkCapture:
    """Capture and log network requests for API reverse engineering.
    
    This utility captures all network requests during the booking flow
    to help identify API endpoints, parameters, and headers needed for
    direct API-based reservations.
    """
    
    def __init__(self):
        self.captured_requests: List[Dict] = []
        self.capture_enabled = False
        self.page: Optional[Page] = None
        self._request_handler = None
        self._response_handler = None
    
    async def start_capture(self, page: Page):
        """Start capturing network requests from a Playwright page.
        
        Args:
            page: Playwright page object to monitor
        """
        self.page = page
        self.capture_enabled = True
        self.captured_requests = []
        
        async def on_request(request):
            """Handle request events."""
            if not self.capture_enabled:
                return
                
            # Only capture requests to the booking domain
            if 'cm9.eprs.jp' not in request.url:
                return
            
            try:
                request_info = {
                    'timestamp': datetime.now().isoformat(),
                    'url': request.url,
                    'method': request.method,
                    'headers': dict(request.headers),
                    'post_data': None,
                    'post_data_parsed': None,
                }
                
                # Capture POST data
                if request.method == 'POST':
                    try:
                        request_info['post_data'] = request.post_data
                        
                        # Parse form data if available
                        if request.post_data:
                            try:
                                # Try to parse as URL-encoded form data
                                parsed = parse_qs(request.post_data, keep_blank_values=True)
                                request_info['post_data_parsed'] = {
                                    k: v[0] if len(v) == 1 else v 
                                    for k, v in parsed.items()
                                }
                            except Exception as parse_error:
                                logger.debug(f"Could not parse POST data as URL-encoded: {parse_error}")
                                # If not URL-encoded, might be JSON
                                try:
                                    request_info['post_data_parsed'] = json.loads(request.post_data)
                                except:
                                    pass
                    except Exception as e:
                        logger.debug(f"Could not capture POST data: {e}")
                
                self.captured_requests.append(request_info)
                
                # Log to console with detailed information
                if request.method == 'POST':
                    logger.info(f"📡 {request.method} {request.url}")
                    if request_info.get('post_data_parsed'):
                        # Log form data in a readable format
                        data_str = json.dumps(
                            request_info['post_data_parsed'], 
                            indent=2, 
                            ensure_ascii=False
                        )
                        logger.info(f"   Form Data:\n{data_str}")
                    elif request_info.get('post_data'):
                        logger.info(f"   Raw Data: {request_info['post_data'][:200]}")
                else:
                    logger.debug(f"📡 {request.method} {request.url}")
                    
            except Exception as e:
                logger.error(f"Error capturing request: {e}")
        
        async def on_response(response):
            """Handle response events."""
            if not self.capture_enabled:
                return
                
            # Only capture responses from booking domain
            if 'cm9.eprs.jp' not in response.url:
                return
                
            # Only capture POST responses (they're the important ones)
            if response.request.method != 'POST':
                return
            
            try:
                response_text = await response.text()
                response_info = {
                    'url': response.url,
                    'status': response.status,
                    'headers': dict(response.headers),
                    'body': response_text[:5000],  # First 5000 chars
                    'body_preview': response_text[:500] if len(response_text) > 500 else response_text,
                }
                
                # Try to parse JSON response
                try:
                    response_info['body_json'] = json.loads(response_text)
                except:
                    pass
                
                # Update the corresponding request with response info
                for req in self.captured_requests:
                    if req['url'] == response.url and req['timestamp']:
                        # Match by URL and approximate timestamp
                        req['response'] = response_info
                        break
                
                logger.info(f"📥 Response {response.status} from {response.url}")
                if response.status == 200:
                    if response_info.get('body_json'):
                        logger.info(f"   JSON Response: {json.dumps(response_info['body_json'], indent=2, ensure_ascii=False)[:300]}")
                    else:
                        logger.info(f"   Body preview: {response_info['body_preview']}")
                elif response.status != 200:
                    logger.warning(f"   Status {response.status}: {response_info['body_preview']}")
                    
            except Exception as e:
                logger.debug(f"Could not capture response: {e}")
        
        # Set up event listeners
        self._request_handler = on_request
        self._response_handler = on_response
        page.on('request', on_request)
        page.on('response', on_response)
        
        logger.info("🎯 Network capture started - monitoring all requests to cm9.eprs.jp")
    
    def stop_capture(self):
        """Stop capturing network requests."""
        if self.capture_enabled:
            self.capture_enabled = False
            
            # Remove event listeners
            if self.page and self._request_handler:
                try:
                    self.page.remove_listener('request', self._request_handler)
                except:
                    pass
            if self.page and self._response_handler:
                try:
                    self.page.remove_listener('response', self._response_handler)
                except:
                    pass
            
            logger.info(f"🛑 Network capture stopped. Captured {len(self.captured_requests)} requests")
        else:
            logger.info("Network capture was not active")
    
    def save_to_file(self, filename: str = 'network_capture.json'):
        """Save captured requests to JSON file.
        
        Args:
            filename: Output filename (default: 'network_capture.json')
        """
        if not self.captured_requests:
            logger.warning("No requests captured - nothing to save")
            return
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.captured_requests, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Saved {len(self.captured_requests)} requests to {filename}")
        except Exception as e:
            logger.error(f"Error saving capture to file: {e}")
    
    def get_booking_requests(self) -> List[Dict]:
        """Get only requests related to booking/reservation flow.
        
        Returns:
            List of captured requests that match booking-related patterns
        """
        booking_keywords = [
            'ReservedApply',  # rsvWOpeReservedApplyAction
            'UseruleRsv',     # rsvWInstUseruleRsvApplyAction
            'RsvApply',       # rsvWInstRsvApplyAction
            'CreditInit',     # Payment-related
            'RsvGet',         # Reservation retrieval
        ]
        
        booking_requests = []
        for req in self.captured_requests:
            url_lower = req['url'].lower()
            if any(keyword.lower() in url_lower for keyword in booking_keywords):
                booking_requests.append(req)
        
        return booking_requests
    
    def print_summary(self):
        """Print a summary of captured requests."""
        if not self.captured_requests:
            logger.info("No requests captured")
            return
        
        booking_requests = self.get_booking_requests()
        
        print(f"\n{'='*80}")
        print(f"NETWORK CAPTURE SUMMARY")
        print(f"{'='*80}")
        print(f"Total requests captured: {len(self.captured_requests)}")
        print(f"Booking-related requests: {len(booking_requests)}")
        print(f"{'='*80}\n")
        
        if booking_requests:
            print("BOOKING-RELATED REQUESTS:")
            print("-" * 80)
            for i, req in enumerate(booking_requests, 1):
                print(f"\n[{i}] {req['method']} {req['url']}")
                print(f"    Timestamp: {req.get('timestamp', 'N/A')}")
                
                if req.get('post_data_parsed'):
                    print(f"    Form Data:")
                    for key, value in req['post_data_parsed'].items():
                        # Truncate long values for readability
                        value_str = str(value)
                        if len(value_str) > 100:
                            value_str = value_str[:100] + "..."
                        print(f"      {key}: {value_str}")
                elif req.get('post_data'):
                    print(f"    Raw Data: {req['post_data'][:200]}")
                
                if req.get('response'):
                    resp = req['response']
                    print(f"    Response: {resp['status']}")
                    if resp.get('body_json'):
                        print(f"    Response Body (JSON): {json.dumps(resp['body_json'], indent=6, ensure_ascii=False)[:300]}")
                    elif resp.get('body_preview'):
                        print(f"    Response Body: {resp['body_preview'][:200]}")
                
                print("-" * 80)
        else:
            print("No booking-related requests found. Try performing a booking operation.")
        
        print(f"\n{'='*80}\n")
    
    def get_api_endpoint_info(self) -> Dict[str, Dict]:
        """Extract API endpoint information for direct API calls.
        
        Returns:
            Dictionary mapping endpoint URLs to their request/response details
        """
        booking_requests = self.get_booking_requests()
        
        endpoints = {}
        for req in booking_requests:
            url = req['url']
            endpoints[url] = {
                'method': req['method'],
                'headers': req.get('headers', {}),
                'form_data': req.get('post_data_parsed', {}),
                'raw_post_data': req.get('post_data'),
                'response_status': req.get('response', {}).get('status'),
                'response_body': req.get('response', {}).get('body'),
                'response_json': req.get('response', {}).get('body_json'),
            }
        
        return endpoints
    
    def save_api_template(self, filename: str = 'api_template.py'):
        """Generate a Python code template for API calls based on captured requests.
        
        Args:
            filename: Output filename for the template
        """
        endpoints = self.get_api_endpoint_info()
        
        if not endpoints:
            logger.warning("No booking endpoints found - cannot generate template")
            return
        
        template = '''"""
Auto-generated API template for Shinagawa booking system.
Generated from network capture on {timestamp}.

WARNING: This is a template - review and test carefully before production use.
"""

import requests
from typing import Dict, Optional


class ShinagawaBookingAPI:
    """API client for booking operations (reverse-engineered)."""
    
    def __init__(self, session_cookies: Dict[str, str], base_url: str = "https://www.cm9.eprs.jp/shinagawa/web"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.cookies.update(session_cookies)
        # Set default headers based on captured requests
        self.session.headers.update({{
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://www.cm9.eprs.jp',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        }})

'''.format(timestamp=datetime.now().isoformat())
        
        for url, info in endpoints.items():
            # Extract endpoint name from URL
            endpoint_name = url.split('/')[-1].replace('.do', '').replace('Action', '')
            method_name = endpoint_name[0].lower() + endpoint_name[1:] if endpoint_name else 'unknown_endpoint'
            
            template += f'''
    def {method_name}(self, **kwargs) -> Dict:
        """
        {info['method']} {url}
        
        Args:
            **kwargs: Form data parameters (update based on captured data)
        
        Returns:
            Response data
        """
        url = f"{{self.base_url}}/{url.split('/')[-1]}"
        
        # TODO: Update form_data with actual parameters from captured request
        form_data = {{
            {json.dumps(info.get('form_data', {}), indent=12, ensure_ascii=False)}
        }}
        
        # Update with provided kwargs
        form_data.update(kwargs)
        
        # Set Referer header if available
        headers = {{}}
        if 'Referer' in {json.dumps(info.get('headers', {}), indent=12)}:
            headers['Referer'] = {json.dumps(info.get('headers', {}).get('Referer', ''))}
        
        response = self.session.{info['method'].lower()}(url, data=form_data, headers=headers)
        response.raise_for_status()
        
        try:
            return response.json()
        except:
            return {{'text': response.text}}

'''
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(template)
            logger.info(f"💾 Generated API template: {filename}")
            logger.info("   Review and update the template with correct parameters before use")
        except Exception as e:
            logger.error(f"Error saving API template: {e}")
