# Quick Start Guide

## 🚀 Start in 3 Steps

### Step 1: Start Backend
```bash
# Double-click start_backend.bat
# OR manually:
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python run.py
```

Backend runs on: **http://localhost:8000**

### Step 2: Start Frontend
```bash
# In a new terminal, double-click start_frontend.bat
# OR manually:
cd frontend
npm install
npm run dev
```

Frontend runs on: **http://localhost:5173**

### Step 3: Use the System
1. Open **http://localhost:5173** in your browser
2. Click **"空き状況をスキャン"** to scan for available slots
3. Browse available slots in **"空き状況"** page
4. Click any slot and fill the form to book
5. View your bookings in **"予約一覧"** page

## 📋 First Time Setup Checklist

- [ ] Python 3.8+ installed
- [ ] Node.js 16+ installed
- [ ] Backend dependencies installed
- [ ] Frontend dependencies installed
- [ ] Playwright browsers installed
- [ ] `.env` file created with credentials
- [ ] Backend server running
- [ ] Frontend server running

## ⚙️ Configuration

Edit `backend/.env`:
```env
USER_ID=84005565
PASSWORD=Bb1234567890
HEADLESS=true  # Set false to see browser
```

## 🎯 Key Features

✅ **Availability Scanning** - Fast AJAX-based detection
✅ **Automated Booking** - Playwright browser automation
✅ **Beautiful UI** - Modern React interface
✅ **Reservation History** - Track all bookings
✅ **Multi-Park Support** - Monitor all target parks

## 🔧 Troubleshooting

**Backend won't start?**
- Check Python version: `python --version`
- Install dependencies: `pip install -r requirements.txt`
- Install Playwright: `playwright install chromium`

**Frontend won't start?**
- Check Node version: `node --version`
- Install dependencies: `npm install`
- Clear cache: `rm -rf node_modules && npm install`

**Can't connect to API?**
- Ensure backend is running on port 8000
- Check CORS settings in `backend/app/main.py`
- Check browser console for errors

**Login fails?**
- Verify credentials in `.env`
- Check network connectivity
- Try headless=false to see browser

## 📚 Documentation

- **README.md** - Full documentation
- **SETUP.md** - Detailed setup guide
- **PROJECT_STRUCTURE.md** - Code organization
- **FEATURES.md** - Feature list

## 🎉 You're Ready!

The system is now ready to:
1. Monitor availability
2. Book slots automatically
3. Track reservations
4. View booking history

Happy booking! 🎾

