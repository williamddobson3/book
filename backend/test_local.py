"""Test backend locally without proxy."""
import socket
import sys

def test_socket():
    """Test if port is accepting connections."""
    print("Testing socket connection to backend...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex(('127.0.0.1', 8001))
        sock.close()
        
        if result == 0:
            print("[OK] Socket connection successful - port is accepting connections")
            return True
        else:
            print(f"[ERROR] Socket connection failed (error code: {result})")
            return False
    except Exception as e:
        print(f"[ERROR] Socket test failed: {e}")
        return False

def test_http():
    """Test HTTP response."""
    print("\nTesting HTTP response...")
    try:
        import http.client
        
        conn = http.client.HTTPConnection('127.0.0.1', 8001, timeout=5)
        conn.request('GET', '/api/health')
        response = conn.getresponse()
        
        print(f"[OK] HTTP Response received!")
        print(f"Status: {response.status} {response.reason}")
        print(f"Headers: {dict(response.getheaders())}")
        
        data = response.read()
        print(f"Response body (first 200 chars): {data.decode()[:200]}")
        
        conn.close()
        
        if response.status == 200:
            print("\n[SUCCESS] Backend is working correctly!")
            return True
        else:
            print(f"\n[WARN] Backend returned status {response.status}")
            return False
            
    except Exception as e:
        print(f"[ERROR] HTTP test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Local Backend Test")
    print("=" * 60)
    
    socket_ok = test_socket()
    
    if socket_ok:
        http_ok = test_http()
        
        if not http_ok:
            print("\n" + "=" * 60)
            print("DIAGNOSIS:")
            print("Port is open but backend is not responding to HTTP requests.")
            print("This means:")
            print("1. Backend process is running but crashed during startup")
            print("2. Backend is not properly initialized")
            print("3. Need to restart backend and check startup logs")
            print("=" * 60)
    else:
        print("\n[ERROR] Backend is not listening on port 8001")
        print("Make sure backend is running: python run.py")
