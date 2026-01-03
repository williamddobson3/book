"""FastAPI main application."""
import sys
import asyncio

# Fix for Windows asyncio subprocess issues with Playwright
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import logging

from app.database import get_db, init_db, AsyncSessionLocal
from app.api_client import ShinagawaAPIClient
from app.monitoring_service import MonitoringService
from app.booking_service import BookingService
from app.database import AvailabilitySlot, Reservation, MonitoringLog

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Shinagawa Booking System", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services
api_client: Optional[ShinagawaAPIClient] = None
monitoring_service: Optional[MonitoringService] = None
booking_service: Optional[BookingService] = None
monitoring_task: Optional[asyncio.Task] = None


async def background_monitoring():
    """Background task that periodically scans for availability and auto-books slots."""
    from app.config import settings
    
    while True:
        try:
            async with AsyncSessionLocal() as session:
                # Scan for new availability
                new_slots = await monitoring_service.detect_new_availability(session)
                
                if new_slots:
                    logger.info(f"Found {len(new_slots)} new available slots, attempting to book...")
                    
                    # Sort by park priority (lower number = higher priority)
                    new_slots.sort(key=lambda x: x.get('park_priority', 999))
                    
                    # Attempt to book the first available slot (highest priority)
                    for slot in new_slots:
                        try:
                            slot_id = slot.get('id')
                            if not slot_id:
                                continue
                                
                            logger.info(f"Attempting to book slot {slot_id}: {slot.get('bcd_name')} - {slot.get('icd_name')} on {slot.get('use_ymd')}")
                            
                            result = await booking_service.book_available_slot(
                                session,
                                slot_id=slot_id,
                                user_count=2,
                                event_name="自動予約"
                            )
                            
                            logger.info(f"Successfully booked slot! Reservation number: {result['reservation_number']}")
                            # Only book one slot at a time
                            break
                            
                        except Exception as e:
                            logger.error(f"Failed to book slot {slot.get('id')}: {e}")
                            continue
                
                # Wait before next scan
                await asyncio.sleep(settings.poll_interval)
                
        except Exception as e:
            logger.error(f"Error in background monitoring: {e}")
            # Wait a bit longer on error before retrying
            await asyncio.sleep(settings.poll_interval * 2)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global api_client, monitoring_service, booking_service, monitoring_task
    
    # Initialize database
    await init_db()
    
    # Initialize API client (will be updated with cookies after login)
    api_client = ShinagawaAPIClient()
    
    # Initialize services
    booking_service = BookingService()
    await booking_service.initialize()
    
    # Initialize monitoring service with browser automation reference
    monitoring_service = MonitoringService(api_client, browser_automation=booking_service.browser)
    
    # Get cookies from login and update API client
    cookies = await booking_service.browser.context.cookies()
    cookie_dict = {c['name']: c['value'] for c in cookies}
    api_client.update_cookies(cookie_dict)
    logger.info("Updated API client with authentication cookies")
    
    # Start background monitoring task for automatic booking
    monitoring_task = asyncio.create_task(background_monitoring())
    
    logger.info("Application started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global booking_service, monitoring_task
    
    # Cancel background monitoring task
    if monitoring_task:
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass
    
    if booking_service:
        await booking_service.cleanup()
    logger.info("Application stopped")


# Pydantic models
class SlotResponse(BaseModel):
    id: int
    use_ymd: int
    bcd_name: str
    icd_name: str
    start_time_display: str
    end_time_display: str
    status: str
    
    class Config:
        from_attributes = True


class BookingRequest(BaseModel):
    slot_id: int
    user_count: int = 2
    event_name: Optional[str] = None


class ReservationResponse(BaseModel):
    id: int
    reservation_number: str
    bcd_name: str
    icd_name: str
    start_time_display: str
    end_time_display: str
    use_ymd: int
    user_count: int
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# API Endpoints

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Shinagawa Booking System API", "status": "running"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/scan")
async def scan_availability(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db)
):
    """Trigger availability scan."""
    try:
            slots = await monitoring_service.scan_availability(session)
            # Convert to dict format for response
            slot_dicts = []
            for slot in slots:
                slot_dicts.append({
                    'id': slot.get('id', 0),
                    'use_ymd': slot['use_ymd'],
                    'bcd_name': slot['bcd_name'],
                    'icd_name': slot['icd_name'],
                    'start_time_display': slot['start_time_display'],
                    'end_time_display': slot['end_time_display'],
                    'status': slot.get('status', 'available')
                })
            return {
                "success": True,
                "slots_found": len(slots),
                "slots": slot_dicts
            }
    except Exception as e:
        logger.error(f"Scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/availability")
async def get_availability(
    park_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
):
    """Get available slots from database."""
    try:
        date_from_dt = datetime.fromisoformat(date_from) if date_from else None
        date_to_dt = datetime.fromisoformat(date_to) if date_to else None
        
        slots = await monitoring_service.get_available_slots_from_db(
            session,
            park_name=park_name,
            date_from=date_from_dt,
            date_to=date_to_dt
        )
        
        return {
            "success": True,
            "count": len(slots),
            "slots": [
                {
                    "id": s.id,
                    "use_ymd": s.use_ymd,
                    "bcd_name": s.bcd_name,
                    "icd_name": s.icd_name,
                    "start_time_display": s.start_time_display,
                    "end_time_display": s.end_time_display,
                    "status": s.status
                }
                for s in slots
            ]
        }
    except Exception as e:
        logger.error(f"Error getting availability: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/book")
async def book_slot(
    request: BookingRequest,
    session: AsyncSession = Depends(get_db)
):
    """Book an available slot."""
    try:
        result = await booking_service.book_available_slot(
            session,
            slot_id=request.slot_id,
            user_count=request.user_count,
            event_name=request.event_name
        )
        
        reservation = result['reservation']
        return {
            "success": True,
            "reservation_number": result['reservation_number'],
            "reservation": {
                "id": reservation.id,
                "reservation_number": reservation.reservation_number,
                "bcd_name": reservation.bcd_name,
                "icd_name": reservation.icd_name,
                "start_time_display": reservation.start_time_display,
                "end_time_display": reservation.end_time_display,
                "use_ymd": reservation.use_ymd,
                "user_count": reservation.user_count,
                "status": reservation.status,
                "created_at": reservation.created_at
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Booking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reservations")
async def get_reservations(
    limit: int = 100,
    session: AsyncSession = Depends(get_db)
):
    """Get recent reservations."""
    try:
        reservations = await booking_service.get_reservations(session, limit=limit)
        return {
            "success": True,
            "count": len(reservations),
            "reservations": [
                {
                    "id": r.id,
                    "reservation_number": r.reservation_number,
                    "bcd_name": r.bcd_name,
                    "icd_name": r.icd_name,
                    "start_time_display": r.start_time_display,
                    "end_time_display": r.end_time_display,
                    "use_ymd": r.use_ymd,
                    "user_count": r.user_count,
                    "status": r.status,
                    "created_at": r.created_at
                }
                for r in reservations
            ]
        }
    except Exception as e:
        logger.error(f"Error getting reservations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs")
async def get_logs(
    log_type: Optional[str] = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_db)
):
    """Get monitoring logs."""
    try:
        from sqlalchemy import select
        
        stmt = select(MonitoringLog)
        if log_type:
            stmt = stmt.where(MonitoringLog.log_type == log_type)
        stmt = stmt.order_by(MonitoringLog.created_at.desc()).limit(limit)
        
        result = await session.execute(stmt)
        logs = result.scalars().all()
        
        return {
            "success": True,
            "count": len(logs),
            "logs": [
                {
                    "id": log.id,
                    "log_type": log.log_type,
                    "message": log.message,
                    "success": log.success,
                    "created_at": log.created_at.isoformat()
                }
                for log in logs
            ]
        }
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

