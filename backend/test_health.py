"""Quick health check test for the backend."""
import requests
import time
import sys

def test_backend():
    url = "http://localhost:8001/api/health"
    max_retries = 10
    retry_delay = 2
    
    print(f"Testing backend at {url}...")
    
    # Disable proxy to avoid CCProxy interference
    session = requests.Session()
    session.proxies = {
        'http': None,
        'https': None,
    }
    
    for i in range(max_retries):
        try:
            response = session.get(url, timeout=5)
            if response.status_code == 200:
                print(f"[OK] Backend is running!")
                print(f"Response: {response.json()}")
                return True
            else:
                print(f"[WARN] Backend responded with status {response.status_code}")
                print(f"Response: {response.text[:200]}")
        except requests.exceptions.ConnectionError:
            print(f"[WAIT] Waiting for backend to start... (attempt {i+1}/{max_retries})")
            if i < max_retries - 1:
                time.sleep(retry_delay)
        except Exception as e:
            print(f"[ERROR] Error: {e}")
            return False
    
    print("[ERROR] Backend did not start within expected time")
    return False

if __name__ == "__main__":
    success = test_backend()
    sys.exit(0 if success else 1)
