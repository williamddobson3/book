# How to Start Backend Successfully

## IMPORTANT: Start Backend Manually

The backend MUST be started in a **visible terminal window** so you can see startup errors.

### Step 1: Open a NEW PowerShell Window

Don't use the current one - open a fresh terminal.

### Step 2: Navigate and Activate

```powershell
cd D:\project\book\backend
.\venv\Scripts\Activate.ps1
```

### Step 3: Check Setup First

```powershell
python check_setup.py
```

If you see errors about missing packages, install them:
```powershell
pip install -r requirements.txt
playwright install chromium
```

### Step 4: Start Backend and WATCH for Errors

```powershell
python run.py
```

**WATCH THE OUTPUT!** You should see:
```
INFO:     Started server process [xxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.    <-- THIS IS CRITICAL!
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### If You See Errors:

1. **NotImplementedError**: Already fixed in run.py - restart backend
2. **Import errors**: Install missing packages with `pip install -r requirements.txt`
3. **Playwright errors**: Run `playwright install chromium`
4. **Port in use**: Kill the process: `netstat -ano | findstr :8001` then `taskkill /PID <PID> /F`

### Step 5: Keep This Window Open!

**DO NOT CLOSE** the terminal window where backend is running. If you close it, the backend stops!

### Step 6: Test

In a **different terminal window**:
```powershell
cd D:\project\book\backend
python test_ngrok.py
```

You should see `[OK] Request successful!` with Status Code 200 (not 503).

## Current Issue

Your backend is running but returning 503 errors, which means:
- Process is alive but backend may have crashed during startup
- Need to see the actual startup logs to diagnose

**Start it in a visible window and check for "Application startup complete" message!**
