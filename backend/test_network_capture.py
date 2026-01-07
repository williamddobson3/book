"""Test script for network capture functionality.

This script helps you capture network requests during the booking flow
to reverse-engineer API endpoints for direct API-based reservations.

It will automatically keep trying different parks and slots until it finds
one that can be successfully reserved, ensuring complete API capture.

Usage:
    python test_network_capture.py
"""

import asyncio
import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.browser_automation import BrowserAutomation
from app.config import settings

async def main():
    """Test network capture during a booking."""
    print("=" * 80)
    print("NETWORK CAPTURE TEST - PERSISTENT MODE")
    print("=" * 80)
    print("This script will:")
    print("1. Start browser and login")
    print("2. Search ALL parks for available slots")
    print("3. Keep trying different slots until one successfully books")
    print("4. Capture ALL network requests during successful booking")
    print("5. Save captured requests to 'booking_requests.json'")
    print("6. Generate API template in 'booking_api_template.py'")
    print("\n⚡ Will keep retrying until successful booking is captured!")
    print("=" * 80)
    print()
    
    # Enable network capture
    settings.enable_network_capture = True
    print("✓ Network capture enabled")
    
    browser = BrowserAutomation()
    
    try:
        print("\n[1/5] Starting browser...")
        await browser.start()
        print("✓ Browser started")
        
        print("\n[2/5] Logging in...")
        cookies = await browser.login()
        print(f"✓ Logged in successfully (got {len(cookies)} cookies)")
        
        print("\n[3/5] Searching ALL parks and ALL courts for available slots...")
        print("   Will systematically search every park and every court...")
        print("   Will keep trying until we find a bookable slot...")
        
        booking_success = False
        attempts = 0
        max_attempts = 100  # Increased limit since we're checking all courts
        
        if not settings.target_parks:
            print("⚠️  No target parks configured")
            return
        
        total_parks = len(settings.target_parks)
        
        # Try each park in priority order
        for park_index, park in enumerate(settings.target_parks, 1):
            if booking_success:
                break
                
            print(f"\n{'='*80}")
            print(f"PARK {park_index}/{total_parks}: {park['name']}")
            print(f"{'='*80}")
            
            try:
                # Initial search to get page and court list
                print(f"   Searching park: {park['name']}...")
                result = await browser.search_availability_via_form(
                    area_code=park['area'],
                    park_name=park['name'],
                    click_reserve_button=False  # Don't auto-click, we'll do it manually
                )
                
                page = result.get('page')
                if not page:
                    print(f"   ⚠️  Could not get page for {park['name']}, trying next park...")
                    continue
                
                # Save initial search results (already scanned default court - usually Court A)
                initial_slots = result.get('slots', [])
                initial_slots_clicked_flag = result.get('slots_clicked_flag', 0)
                
                # Detect which court was shown by default in the initial search
                default_court_icd = None
                try:
                    facility_select = await page.query_selector("#facility-select")
                    if facility_select:
                        default_court_icd = await facility_select.evaluate("el => el.value")
                        if default_court_icd and default_court_icd != "0":
                            print(f"   Initial search showed default court: ICD={default_court_icd} ({len(initial_slots)} slots found)")
                except Exception as e:
                    print(f"   ⚠️  Could not detect default court: {e}")
                
                # Get all courts for this park
                print(f"   Getting list of courts for {park['name']}...")
                courts = await browser.get_available_courts_for_park(page, park['area'])
                
                if not courts:
                    print(f"   ⚠️  No courts found at {park['name']}, trying next park...")
                    continue
                
                print(f"   Found {len(courts)} courts: {[c['name'] for c in courts]}")
                
                # Try each court in the park
                for court_index, court in enumerate(courts, 1):
                    if booking_success:
                        break
                    
                    court_name = court['name']
                    court_icd = court['icd']
                    print(f"\n   {'-'*76}")
                    print(f"   COURT {court_index}/{len(courts)}: {court_name} (ICD: {court_icd})")
                    print(f"   {'-'*76}")
                    
                    try:
                        # Check if this is the default court from initial search
                        if court_icd == default_court_icd:
                            # Use initial search results - don't search again!
                            print(f"      ⏭️  Using initial search results (already scanned 6 weeks)")
                            slots = initial_slots
                            slots_clicked_flag = initial_slots_clicked_flag
                            court_page = page
                            print(f"      Found {len(slots)} available slots at {court_name} (from initial search)")
                        else:
                            # Search for this specific court (not the default one)
                            print(f"      Searching court: {court_name}...")
                            # Since we're already on the results page from the initial search,
                            # use skip_form_expansion=True (just change dropdown, no form expansion)
                            court_result = await browser.search_availability_via_form(
                                area_code=park['area'],
                                park_name=park['name'],
                                icd=court_icd,
                                click_reserve_button=False,
                                skip_form_expansion=True  # Skip form expansion - we're already on results page
                            )
                            
                            slots = court_result.get('slots', [])
                            slots_clicked_flag = court_result.get('slots_clicked_flag', 0)
                            court_page = court_result.get('page', page)
                            print(f"      Found {len(slots)} available slots at {court_name}")
                        
                        if not slots:
                            print(f"      No slots found at {court_name}, trying next court...")
                            continue
                        
                        if slots_clicked_flag != 1:
                            print(f"      Slots found but none were clicked at {court_name}, trying next court...")
                            continue
                        
                        # Try each slot from this court
                        for slot_index, slot in enumerate(slots, 1):  # Try ALL slots, not just first 5
                            if booking_success:
                                break
                                
                            attempts += 1
                            if attempts > max_attempts:
                                print(f"\n      ⚠️  Reached maximum attempts ({max_attempts}), stopping...")
                                break
                            
                            print(f"\n      [{attempts}] Attempting slot {slot_index}/{len(slots)}:")
                            print(f"         Park: {slot.get('bcd_name')} - {slot.get('icd_name')}")
                            print(f"         Date: {slot.get('use_ymd')}")
                            print(f"         Time: {slot.get('start_time_display')} ~ {slot.get('end_time_display')}")
                            print(f"\n         🎯 Network capture is active - all requests will be logged...")
                            
                            if court_page and slots_clicked_flag == 1:
                                try:
                                    # Booking handler will capture network requests
                                    success = await browser.click_reservation_button_if_slots_found(
                                        court_page, slots_clicked_flag, [slot]  # Try just this slot
                                    )
                                    
                                    if success:
                                        print(f"\n         ✓✓✓ BOOKING COMPLETED SUCCESSFULLY! ✓✓✓")
                                        booking_success = True
                                        
                                        # Wait a bit to ensure all network requests are captured
                                        await asyncio.sleep(3)
                                        break
                                    else:
                                        print(f"         ⚠️  Booking attempt failed, trying next slot...")
                                        # Re-search this court to get fresh page
                                        # Use skip_form_expansion=True since we're already on results page
                                        await asyncio.sleep(2)
                                        court_result = await browser.search_availability_via_form(
                                            area_code=park['area'],
                                            park_name=park['name'],
                                            icd=court_icd,
                                            click_reserve_button=False,
                                            skip_form_expansion=True
                                        )
                                        court_page = court_result.get('page', court_page)
                                        slots_clicked_flag = court_result.get('slots_clicked_flag', 0)
                                        
                                except Exception as e:
                                    print(f"         ❌ Error during booking: {e}")
                                    print(f"            Trying next slot...")
                                    # Re-search this court to get fresh page
                                    # Use skip_form_expansion=True since we're already on results page
                                    await asyncio.sleep(2)
                                    try:
                                        court_result = await browser.search_availability_via_form(
                                            area_code=park['area'],
                                            park_name=park['name'],
                                            icd=court_icd,
                                            click_reserve_button=False,
                                            skip_form_expansion=True
                                        )
                                        court_page = court_result.get('page', court_page)
                                        slots_clicked_flag = court_result.get('slots_clicked_flag', 0)
                                    except Exception as retry_error:
                                        print(f"            Could not re-search: {retry_error}")
                                        continue
                            
                            # Small delay between slot attempts
                            await asyncio.sleep(1)
                        
                        if booking_success:
                            break
                    
                    except Exception as e:
                        print(f"      ❌ Error searching court {court_name}: {e}")
                        print(f"         Trying next court...")
                        continue
                
                if booking_success:
                    break
                    
            except Exception as e:
                print(f"   ❌ Error searching park {park['name']}: {e}")
                print(f"      Trying next park...")
                import traceback
                logger.debug(traceback.format_exc())
                continue
        
        print(f"\n[4/5] Booking attempt summary:")
        if booking_success:
            print("   ✓ Successfully completed a booking flow")
            print("   ✓ Network requests should be captured")
        else:
            print("   ⚠️  Could not complete a booking flow")
            print("   ⚠️  This might mean:")
            print("      - No slots are currently available")
            print("      - All slots were already taken")
            print("      - Booking flow encountered errors")
            print("   ⚠️  Network capture may still have partial data")
        
        print("\n[5/5] Analyzing captured data...")
        if os.path.exists('booking_requests.json'):
            import json
            with open('booking_requests.json', 'r', encoding='utf-8') as f:
                captured = json.load(f)
            
            booking_keywords = ['ReservedApply', 'UseruleRsv', 'RsvApply', 'CreditInit', 'RsvGet']
            booking_requests = [r for r in captured if any(
                keyword.lower() in r['url'].lower() for keyword in booking_keywords
            )]
            
            print(f"✓ Captured {len(captured)} total requests")
            print(f"✓ Found {len(booking_requests)} booking-related requests")
            
            if booking_requests:
                print("\n📋 Booking-related endpoints captured:")
                for i, req in enumerate(booking_requests, 1):
                    status = req.get('response', {}).get('status', 'N/A')
                    method = req.get('method', 'GET')
                    print(f"   {i}. {method} {req['url']} → Status: {status}")
                
                # Check if we have all the key endpoints
                endpoint_names = [req['url'].split('/')[-1] for req in booking_requests]
                key_endpoints = {
                    'rsvWOpeReservedApplyAction.do': 'Initial reservation',
                    'rsvWInstUseruleRsvApplyAction.do': 'Terms agreement',
                    'rsvWInstRsvApplyAction.do': 'Final reservation',
                }
                
                print("\n📊 Endpoint coverage:")
                for endpoint, description in key_endpoints.items():
                    found = any(endpoint in url for url in [r['url'] for r in booking_requests])
                    status = "✓" if found else "✗"
                    print(f"   {status} {description}: {endpoint}")
                
                if os.path.exists('booking_api_template.py'):
                    print("\n✓ API template generated: booking_api_template.py")
                    print("   Review and update the template with correct parameters")
                    
                    # Check template quality
                    with open('booking_api_template.py', 'r', encoding='utf-8') as f:
                        template_content = f.read()
                    method_count = template_content.count('def ')
                    print(f"   Template contains {method_count} API method stubs")
            else:
                print("\n⚠️  No booking-related requests found")
                print("   This means the booking flow didn't complete")
                print("   The script will keep retrying...")
                print("\n   Possible reasons:")
                print("   - All slots were already booked")
                print("   - Network issues")
                print("   - Server errors")
                print("\n   Consider:")
                print("   - Running at different times (slots may be released at specific times)")
                print("   - Checking if there are actually available slots")
        else:
            print("⚠️  No capture file found")
            print("   Network capture may not have been triggered")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\n[Cleanup] Stopping browser...")
        await browser.stop()
        print("✓ Done")
        
    print("\n" + "=" * 80)
    print("NETWORK CAPTURE TEST COMPLETE")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Review 'booking_requests.json' for all captured requests")
    print("2. Check 'booking_api_template.py' for generated API code template")
    print("3. Update the template with actual parameter values")
    print("4. Test the API calls directly using the captured information")
    print("=" * 80)

if __name__ == "__main__":
    # Fix for Windows asyncio
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())
