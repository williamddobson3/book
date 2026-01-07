# Network Capture Guide

This guide explains how to use the network capture feature to reverse-engineer API endpoints for direct API-based bookings.

## Overview

The network capture utility automatically captures all HTTP requests during the booking flow, allowing you to:
- Identify API endpoints used for reservations
- Extract request parameters and headers
- Understand the booking flow at the API level
- Generate code templates for direct API calls

## Quick Start

### Method 1: Enable via Config (Recommended)

1. Edit `backend/app/config.py` or set environment variable:
   ```python
   enable_network_capture = True
   ```

2. Run your normal booking flow - requests will be automatically captured

3. Check output files:
   - `booking_requests.json` - All captured requests
   - `booking_api_template.py` - Generated API code template

### Method 2: Use Test Script

Run the dedicated test script:

```bash
cd backend
python test_network_capture.py
```

This script will:
- Start browser and login
- Search for available slots
- Attempt a booking while capturing network requests
- Save all captured data to files

## Output Files

### booking_requests.json

Contains all captured network requests with:
- Request URLs
- HTTP methods (GET/POST)
- Request headers
- Form data/parameters
- Response status codes
- Response bodies

### booking_api_template.py

Auto-generated Python code template with:
- API client class structure
- Method stubs for each endpoint
- Captured form data (needs verification)
- Request headers
- Response handling

## How to Use Captured Data

### Step 1: Review Captured Requests

Open `booking_requests.json` and look for booking-related endpoints:

```json
{
  "url": "https://www.cm9.eprs.jp/shinagawa/web/rsvWOpeReservedApplyAction.do",
  "method": "POST",
  "post_data_parsed": {
    "slot_id": "20260107_10",
    "user_count": "2",
    ...
  },
  "response": {
    "status": 200,
    "body_json": {...}
  }
}
```

### Step 2: Identify Key Endpoints

Look for these patterns in URLs:
- `ReservedApply` - Initial reservation request
- `UseruleRsv` - Terms of Use agreement
- `RsvApply` - Final reservation submission
- `CreditInit` - Payment processing

### Step 3: Extract Required Parameters

For each endpoint, note:
1. **Required form fields** - Check `post_data_parsed`
2. **Required headers** - Check `headers` section
3. **Session cookies** - Must be maintained across requests
4. **CSRF tokens** - May be in hidden form fields

### Step 4: Update API Client

1. Review `booking_api_template.py`
2. Update form data with actual parameter names
3. Verify all required fields are included
4. Test each endpoint individually

## Example: Using Captured Data

```python
# Example based on captured request
import requests

session = requests.Session()
session.cookies.update(your_login_cookies)

# Endpoint 1: Start reservation
response1 = session.post(
    "https://www.cm9.eprs.jp/shinagawa/web/rsvWOpeReservedApplyAction.do",
    data={
        "cell_id": "20260107_10",
        "bcd": "1040",
        "icd": "10400010",
        # ... other parameters from capture
    },
    headers={
        "Referer": "https://www.cm9.eprs.jp/shinagawa/web/rsvWOpeInstSrchVacantAction.do",
        "X-Requested-With": "XMLHttpRequest",
        # ... other headers from capture
    }
)

# Endpoint 2: Accept terms
response2 = session.post(
    "https://www.cm9.eprs.jp/shinagawa/web/rsvWInstUseruleRsvApplyAction.do",
    data={
        "ruleFg": "1",  # Agree to terms
        # ... other parameters
    }
)

# Continue with other endpoints...
```

## Important Notes

⚠️ **Before Using API Calls:**

1. **Verify Parameters**: The captured data may need adjustment - some values might be dynamic
2. **Test Incrementally**: Test each endpoint one at a time to understand the flow
3. **Check Session State**: Ensure cookies/session tokens are maintained between requests
4. **Handle Errors**: API responses may differ from browser behavior
5. **Respect Rate Limits**: Don't make excessive requests that could get you blocked

## Troubleshooting

### No Requests Captured

- Ensure `enable_network_capture = True` is set
- Verify booking flow actually executed (check logs)
- Make sure slots were selected before booking

### Missing Form Data

- Some requests might be GET instead of POST
- Check response bodies for redirect information
- Form data might be in JavaScript variables (check page source)

### Template Not Generated

- Ensure booking-related requests were captured
- Check that `get_booking_requests()` found matching endpoints
- Review console output for errors

## Next Steps

After capturing and analyzing the network requests:

1. ✅ Implement API methods in `ShinagawaAPIClient`
2. ✅ Test API calls directly (without browser)
3. ✅ Update `BookingService` to use API instead of browser automation
4. ✅ Monitor for changes in API structure (they may update endpoints)

## Benefits of API-Based Booking

Once implemented, API-based booking will be:
- **10-100x faster** - No DOM interactions or page loads
- **More reliable** - Fewer timing issues
- **Resource efficient** - No browser process needed
- **Easier to scale** - Can run multiple bookings in parallel
- **Better error handling** - Direct access to API responses

## Support

If you encounter issues:
1. Check the console logs for detailed request/response information
2. Review `booking_requests.json` manually
3. Compare multiple capture sessions to identify patterns
4. Use browser DevTools Network tab as a reference
