"""Quick test for backend."""
import socket
import sys

print("Testing backend connection...")

# Test if port is open
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('127.0.0.1', 8001))
    sock.close()
    
    if result == 0:
        print("[OK] Port 8001 is open and listening")
    else:
        print(f"[ERROR] Port 8001 is not accessible (error code: {result})")
        sys.exit(1)
except Exception as e:
    print(f"[ERROR] Socket test failed: {e}")
    sys.exit(1)

# Try HTTP request
try:
    import urllib.request
    import urllib.error
    
    req = urllib.request.Request('http://127.0.0.1:8001/api/health')
    # Disable proxy
    req.set_proxy('', 'http')
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            print(f"[OK] HTTP request successful!")
            print(f"Status: {response.getcode()}")
            print(f"Response: {response.read().decode()[:200]}")
    except urllib.error.HTTPError as e:
        print(f"[WARN] HTTP Error {e.code}: {e.reason}")
        print(f"Response: {e.read().decode()[:200]}")
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")
        
except ImportError:
    print("[INFO] urllib not available, skipping HTTP test")
