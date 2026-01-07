"""Check backend setup and dependencies before starting."""
import sys
import os

print("=" * 60)
print("Backend Setup Check")
print("=" * 60)

# Check Python version
print(f"\n[OK] Python version: {sys.version}")

# Check if we're in the right directory
if os.path.exists("app"):
    print("[OK] App directory found")
else:
    print("[ERROR] App directory not found! Make sure you're in the backend directory.")
    sys.exit(1)

# Check critical files
required_files = [
    "app/main.py",
    "app/config.py",
    "app/database.py",
    "app/browser_automation.py",
]
for file in required_files:
    if os.path.exists(file):
        print(f"[OK] {file} exists")
    else:
        print(f"[ERROR] {file} missing!")

# Try importing key modules
print("\n" + "=" * 60)
print("Testing Imports")
print("=" * 60)

try:
    import fastapi
    print(f"[OK] FastAPI {fastapi.__version__}")
except ImportError as e:
    print(f"[ERROR] FastAPI not installed: {e}")
    sys.exit(1)

try:
    import uvicorn
    print(f"[OK] Uvicorn installed")
except ImportError as e:
    print(f"[ERROR] Uvicorn not installed: {e}")
    sys.exit(1)

try:
    import playwright
    print(f"[OK] Playwright installed")
except ImportError as e:
    print(f"[ERROR] Playwright not installed: {e}")
    print("   Run: playwright install chromium")

try:
    from app.main import app
    print("[OK] FastAPI app imported successfully")
except Exception as e:
    print(f"[ERROR] Failed to import app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("[OK] Setup check complete!")
print("=" * 60)
