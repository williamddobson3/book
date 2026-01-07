# How to Start the Backend

## Quick Start (PowerShell)

```powershell
cd D:\project\book\backend
.\start_backend.ps1
```

## Manual Start

1. **Activate virtual environment:**
   ```powershell
   cd D:\project\book\backend
   .\venv\Scripts\Activate.ps1
   ```

2. **If you get execution policy error:**
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

3. **Check setup:**
   ```powershell
   python check_setup.py
   ```

4. **If dependencies are missing:**
   ```powershell
   pip install -r requirements.txt
   playwright install chromium
   ```

5. **Start backend:**
   ```powershell
   python run.py
   ```

## Troubleshooting

### "No module named 'xxx'"
- Make sure virtual environment is activated
- Run: `pip install -r requirements.txt`

### "Playwright not found"
- Run: `playwright install chromium`

### "Execution policy" error
- Run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### Backend won't start
- Check if port 8001 is already in use: `netstat -ano | findstr :8001`
- Check backend logs for errors
- Make sure you're in the `backend` directory

## Success Indicators

When backend starts successfully, you should see:
```
INFO:     Started server process [xxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

Then test with:
```powershell
python test_health.py
```
