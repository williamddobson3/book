# Project Structure

## Backend (Python/FastAPI)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application and routes
│   ├── config.py            # Configuration settings
│   ├── database.py          # SQLAlchemy models and database setup
│   ├── api_client.py        # API client for availability scraping
│   ├── browser_automation.py # Playwright browser automation
│   ├── booking_service.py   # Booking business logic
│   ├── monitoring_service.py # Availability monitoring service
│   └── utils.py             # Utility functions
├── requirements.txt         # Python dependencies
├── run.py                  # Entry point to run the server
└── .env                    # Environment variables (create from .env.example)
```

### Key Components

**API Client** (`api_client.py`)
- Handles HTTP requests to Shinagawa reservation API
- Two endpoints: date-based and facility-based availability
- Manages cookies and session
- Scans all target parks

**Browser Automation** (`browser_automation.py`)
- Playwright-based browser automation
- Handles login flow
- Executes booking flow through UI
- Extracts reservation numbers

**Monitoring Service** (`monitoring_service.py`)
- Scans for availability
- Detects new slots
- Stores data in database
- Logs activities

**Booking Service** (`booking_service.py`)
- Coordinates booking process
- Manages reservation records
- Error handling and retry logic

## Frontend (React/Vite)

```
frontend/
├── src/
│   ├── pages/
│   │   ├── Dashboard.jsx       # Main dashboard
│   │   ├── Availability.jsx    # Availability listing and booking
│   │   └── Reservations.jsx    # Reservation history
│   ├── components/
│   │   └── Layout.jsx          # Main layout with navigation
│   ├── api/
│   │   └── client.js           # Axios API client
│   ├── App.jsx                 # Root component with routing
│   ├── main.jsx                # Entry point
│   └── index.css               # Global styles with Tailwind
├── package.json
├── vite.config.js             # Vite configuration
├── tailwind.config.js         # Tailwind CSS configuration
└── postcss.config.js          # PostCSS configuration
```

### Key Pages

**Dashboard** (`Dashboard.jsx`)
- Overview statistics
- Recent reservations
- System logs
- Scan trigger button

**Availability** (`Availability.jsx`)
- Lists available slots
- Filtering by park, date
- Booking modal
- Real-time updates

**Reservations** (`Reservations.jsx`)
- Reservation history
- Status display
- Reservation details

## Database Schema

### availability_slots
- Stores detected available slots
- Tracks status (available, reserved, booked)
- Includes all slot metadata

### reservations
- Stores completed bookings
- Includes reservation numbers
- Links to original slots

### monitoring_logs
- Activity logs
- Error tracking
- System events

## Data Flow

1. **Monitoring Flow**
   - API Client → Scans parks via AJAX
   - Monitoring Service → Processes results
   - Database → Stores availability
   - Frontend → Displays slots

2. **Booking Flow**
   - Frontend → User selects slot
   - API → POST /api/book
   - Booking Service → Coordinates booking
   - Browser Automation → Executes booking
   - Database → Stores reservation
   - Frontend → Shows result

## API Endpoints

- `GET /` - Root
- `GET /api/health` - Health check
- `POST /api/scan` - Trigger availability scan
- `GET /api/availability` - Get available slots
- `POST /api/book` - Book a slot
- `GET /api/reservations` - Get reservations
- `GET /api/logs` - Get monitoring logs

