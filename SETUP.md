# Setup Guide

## Quick Start

### 1. Backend Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Create .env file (copy from .env.example and edit)
# Edit USER_ID and PASSWORD in .env

# Run backend
python run.py
```

Backend will run on http://localhost:8000

### 2. Frontend Setup

```bash
# Navigate to frontend (in a new terminal)
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

Frontend will run on http://localhost:5173

## Usage

1. Open http://localhost:5173 in your browser
2. Click "空き状況をスキャン" on dashboard to scan for availability
3. View available slots in "空き状況" page
4. Click on any slot to book it
5. View your bookings in "予約一覧" page

## Troubleshooting

### Backend Issues

- **Playwright not found**: Run `playwright install chromium`
- **Database errors**: Delete `booking_system.db` and restart
- **Login fails**: Check credentials in `.env` file
- **Port 8000 in use**: Change port in `run.py`

### Frontend Issues

- **API connection fails**: Ensure backend is running on port 8000
- **Build errors**: Delete `node_modules` and run `npm install` again
- **Port 5173 in use**: Vite will automatically use next available port

## Production Build

### Backend
```bash
# No build needed, just run:
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm run build
# Serve dist/ folder with a web server
```

