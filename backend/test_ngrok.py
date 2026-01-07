"""Test backend through ngrok with proper headers."""
import requests

ngrok_url = "https://tereasa-unanaemic-kaydence.ngrok-free.dev/api/health"

print(f"Testing backend through ngrok: {ngrok_url}")
print("=" * 60)

# Test with ngrok-skip-browser-warning header
headers = {
    'ngrok-skip-browser-warning': 'true'
}

# Disable proxy
proxies = {
    'http': None,
    'https': None,
}

try:
    response = requests.get(ngrok_url, headers=headers, proxies=proxies, timeout=10, verify=False)
    print(f"[OK] Request successful!")
    print(f"Status Code: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        print("\n[SUCCESS] Backend is accessible through ngrok!")
    else:
        print(f"\n[WARN] Backend responded with status {response.status_code}")
        
except requests.exceptions.SSLError as e:
    print(f"[ERROR] SSL Error: {e}")
    print("Trying without SSL verification...")
    try:
        response = requests.get(ngrok_url, headers=headers, proxies=proxies, timeout=10, verify=False)
        print(f"[OK] Request successful (no SSL verify)!")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:500]}")
    except Exception as e2:
        print(f"[ERROR] Still failed: {e2}")
except Exception as e:
    print(f"[ERROR] Request failed: {e}")
    import traceback
    traceback.print_exc()
