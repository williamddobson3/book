# 品川区施設予約システム (Shinagawa Facility Booking System)

A complete automated booking system for Shinagawa Ward facilities with Python backend and React frontend.

## Features

- ✅ Real-time availability monitoring using AJAX APIs
- ✅ Automated slot detection and scanning
- ✅ Browser automation for booking flow
- ✅ Beautiful, modern React frontend
- ✅ Reservation management and history
- ✅ Multi-park support
- ✅ SQLite database for data persistence

## Project Structure

```
booking-system/
├── backend/           # Python FastAPI backend
│   ├── app/
│   │   ├── api_client.py          # API client for availability scraping
│   │   ├── browser_automation.py  # Playwright browser automation
│   │   ├── booking_service.py     # Booking service logic
│   │   ├── monitoring_service.py  # Availability monitoring
│   │   ├── database.py            # SQLAlchemy models
│   │   ├── main.py                # FastAPI application
│   │   └── config.py              # Configuration settings
│   ├── requirements.txt
│   └── .env.example
├── frontend/          # React + Vite frontend
│   ├── src/
│   │   ├── pages/     # Page components
│   │   ├── components/ # Reusable components
│   │   ├── api/       # API client
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## Setup Instructions

### Backend Setup

1. Navigate to backend directory:
```bash
cd backend
```

2. Create virtual environment:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Playwright browsers:
```bash
playwright install chromium
```

5. Copy environment file:
```bash
copy .env.example .env
# Edit .env with your credentials
```

6. Run the backend:
```bash
python -m app.main
# Or
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Run development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Configuration

### Backend Configuration (.env)

```env
DATABASE_URL=sqlite:///./booking_system.db
USER_ID=84005565
PASSWORD=Bb1234567890
BASE_URL=https://www.cm9.eprs.jp/shinagawa/web
HEADLESS=true
POLL_INTERVAL=30
```

### Target Parks

The system monitors these parks by default:
- しながわ区民公園 (Priority 1)
- 八潮北公園 (Priority 2)
- しながわ中央公園 (Priority 3)
- 東品川公園 (Priority 4)

## API Endpoints

### Availability
- `POST /api/scan` - Trigger availability scan
- `GET /api/availability` - Get available slots (with filters)

### Booking
- `POST /api/book` - Book an available slot

### Reservations
- `GET /api/reservations` - Get reservation history

### Monitoring
- `GET /api/logs` - Get monitoring logs
- `GET /api/health` - Health check

## Usage

1. Start the backend server
2. Start the frontend development server
3. Open `http://localhost:5173` in your browser
4. Navigate to "空き状況" (Availability) page
5. Click "スキャン" to scan for available slots
6. Click on any available slot to book it
7. Fill in booking details and confirm
8. View your reservations in "予約一覧" (Reservations) page

## Technical Details

### Backend
- **FastAPI**: Modern, fast web framework
- **Playwright**: Browser automation for booking
- **SQLAlchemy**: Database ORM
- **SQLite**: Lightweight database
- **AJAX API Client**: Direct API access for availability monitoring

### Frontend
- **React 18**: UI library
- **Vite**: Build tool and dev server
- **Tailwind CSS**: Styling
- **React Router**: Navigation
- **Axios**: HTTP client
- **Lucide React**: Icons
- **date-fns**: Date formatting

## Development Notes

- The system uses AJAX endpoints for fast availability detection
- Browser automation is only used for the actual booking flow
- Session cookies are managed automatically
- Database stores availability, reservations, and monitoring logs
- Frontend provides real-time updates and beautiful UI

## License

Private project for Shinagawa facility booking automation.

