"""FastAPI main application."""
import sys
import asyncio

# Fix for Windows asyncio subprocess issues with Playwright
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import logging
import json
import asyncio
from collections import deque

from app.database import get_db, init_db, AsyncSessionLocal
from app.api_client import ShinagawaAPIClient
from app.monitoring_service import MonitoringService
from app.booking_service import BookingService
from app.database import AvailabilitySlot, Reservation, MonitoringLog, TakenSlot
from app.status_tracker import status_tracker, SystemStatus, AutomationStatus, LoginStatus, SessionStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Shinagawa Booking System", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://localhost:3000",
        "http://65.109.83.125:5173",  # VPS frontend
        "http://65.109.83.125",
        "https://65.109.83.125:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services
api_client: Optional[ShinagawaAPIClient] = None
monitoring_service: Optional[MonitoringService] = None
booking_service: Optional[BookingService] = None
monitoring_task: Optional[asyncio.Task] = None

# SSE event queue for real-time updates
sse_connections: deque = deque()

async def broadcast_reservation_event(reservation_data: dict):
    """Broadcast a new reservation event to all connected SSE clients."""
    event = {
        "type": "reservation",
        "data": reservation_data
    }
    message = f"data: {json.dumps(event)}\n\n"
    
    # Send to all connected clients
    disconnected = []
    for queue in sse_connections:
        try:
            await queue.put(message)
        except Exception as e:
            logger.warning(f"Error sending SSE message: {e}")
            disconnected.append(queue)
    
    # Remove disconnected clients
    for queue in disconnected:
        try:
            sse_connections.remove(queue)
        except ValueError:
            pass


async def broadcast_availability_update():
    """Broadcast availability update event to trigger frontend refresh."""
    event = {
        "type": "availability_update",
        "message": "New availability slots found - refreshing list"
    }
    message = f"data: {json.dumps(event)}\n\n"
    
    # Send to all connected clients
    disconnected = []
    for queue in sse_connections:
        try:
            await queue.put(message)
        except Exception as e:
            logger.warning(f"Error sending SSE message: {e}")
            disconnected.append(queue)
    
    # Remove disconnected clients
    for queue in disconnected:
        try:
            sse_connections.remove(queue)
        except ValueError:
            pass


async def background_monitoring():
    """Background task that continuously scans all parks for availability and auto-books slots.
    
    This function loops through all parks continuously:
    1. Scans all four parks in sequence
    2. After completing all parks, immediately starts over
    3. Continues this process indefinitely until manually stopped
    """
    from app.config import settings
    
    cycle_count = 0
    
    # Create a background task to periodically update activity time (heartbeat)
    async def heartbeat_task():
        """Periodically update activity time to show system is alive."""
        while True:
            try:
                await asyncio.sleep(30)  # Update every 30 seconds
                status_tracker.touch_activity_time()
                # Broadcast heartbeat update
                await broadcast_status_update()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error in heartbeat task: {e}")
    
    heartbeat = asyncio.create_task(heartbeat_task())
    
    try:
        while True:
            try:
                cycle_count += 1
                logger.info(f"=== Starting monitoring cycle #{cycle_count} ===")
                status_tracker.add_activity_log("system", f"Starting monitoring cycle #{cycle_count}")
                
                async with AsyncSessionLocal() as session:
                    # Update status: starting new cycle
                    status_tracker.set_current_task(
                        f"Scanning cycle #{cycle_count} - All parks",
                        {"cycle": cycle_count, "action": "scanning_all_parks"}
                    )
                    await broadcast_status_update()
                    
                    # Pattern 2: Intensive monitoring during 9:00-12:00
                    pattern2_slots = []
                    from datetime import datetime
                    current_hour = datetime.now().hour
                    if 9 <= current_hour < 12:
                        logger.info("Pattern 2 active: Intensive monitoring (9:00-12:00)")
                        status_tracker.set_current_task(
                            f"Pattern 2: Intensive monitoring (9:00-12:00)",
                            {"cycle": cycle_count, "pattern": "pattern2"}
                        )
                        await broadcast_status_update()
                        pattern2_slots = await monitoring_service.scan_pattern2_intensive(
                            session, on_status_update=broadcast_status_update
                        )
                    
                    # Pattern 3: Check for "取" → "⚫︎" transitions and attempt bookings at transition times
                    logger.info("Pattern 3: Checking for transitions and attempting bookings")
                    transitioned_slots = await monitoring_service._check_transitions(session)
                    scheduled_bookings = await monitoring_service.schedule_pattern3_bookings(session)
                    
                    # Attempt Pattern 3 bookings for slots at transition times
                    if scheduled_bookings:
                        logger.info(f"Pattern 3: Attempting {len(scheduled_bookings)} bookings at transition times")
                        for booking_info in scheduled_bookings:
                            try:
                                # Try to find the slot in availability_slots (it may have just become available)
                                from sqlalchemy import select
                                from app.database import AvailabilitySlot
                                
                                slot_stmt = select(AvailabilitySlot).where(
                                    AvailabilitySlot.use_ymd == booking_info["use_ymd"],
                                    AvailabilitySlot.bcd == booking_info["bcd"],
                                    AvailabilitySlot.icd == booking_info["icd"],
                                    AvailabilitySlot.start_time == booking_info["start_time"],
                                    AvailabilitySlot.status == "available"
                                )
                                slot_result = await session.execute(slot_stmt)
                                available_slot = slot_result.scalar_one_or_none()
                                
                                if available_slot:
                                    # Slot is available - attempt booking
                                    logger.info(f"Pattern 3: Attempting to book {booking_info['bcd_name']} - {booking_info['icd_name']} on {booking_info['use_ymd']}")
                                    
                                    result = await booking_service.book_available_slot(
                                        session,
                                        slot_id=available_slot.id,
                                        user_count=2,
                                        event_name="Pattern3自動予約"
                                    )
                                    
                                    logger.info(f"Pattern 3: Successfully booked! Reservation number: {result['reservation_number']}")
                                    
                                    # Update reservation result
                                    status_tracker.set_reservation_result(
                                        success=True,
                                        reservation_number=result['reservation_number'],
                                        details={"slot_id": available_slot.id, "pattern": "pattern3"}
                                    )
                                    
                                    # Broadcast reservation event
                                    reservation = result.get('reservation')
                                    if reservation:
                                        reservation_data = {
                                            "id": reservation.id,
                                            "reservation_number": reservation.reservation_number,
                                            "bcd_name": reservation.bcd_name,
                                            "icd_name": reservation.icd_name,
                                            "start_time_display": reservation.start_time_display,
                                            "end_time_display": reservation.end_time_display,
                                            "use_ymd": reservation.use_ymd,
                                            "user_count": reservation.user_count or 2,
                                            "event_name": reservation.event_name,
                                            "status": reservation.status,
                                            "created_at": reservation.created_at.isoformat() if reservation.created_at else None
                                        }
                                        await broadcast_reservation_event(reservation_data)
                                    
                                    # Mark taken slot as booked
                                    from app.database import TakenSlot
                                    taken_stmt = select(TakenSlot).where(TakenSlot.id == booking_info["taken_slot_id"])
                                    taken_result = await session.execute(taken_stmt)
                                    taken_slot = taken_result.scalar_one_or_none()
                                    if taken_slot:
                                        taken_slot.status = "booked"
                                        await session.commit()
                                    
                                    break  # Only book one at a time
                                else:
                                    logger.debug(f"Pattern 3: Slot not yet available, will retry at next cycle")
                            except Exception as e:
                                logger.warning(f"Pattern 3: Failed to book slot: {e}")
                                continue
                    
                    # Standard scan for new availability (this scans all parks)
                    # Pass broadcast callback for real-time status updates during scanning
                    new_slots = await monitoring_service.detect_new_availability(session, on_status_update=broadcast_status_update)
                    
                    # Combine Pattern 2 slots and newly detected slots
                    all_new_slots = new_slots + pattern2_slots + transitioned_slots
                    
                    # Update availability result
                    status_tracker.set_availability_result(
                        found=len(all_new_slots) > 0,
                        slots_count=len(all_new_slots)
                    )
                    await broadcast_status_update()
                    
                    if all_new_slots:
                        # Broadcast availability update to trigger frontend refresh
                        await broadcast_availability_update()
                        logger.info(f"Found {len(all_new_slots)} new available slots (Pattern 2: {len(pattern2_slots)}, Transitions: {len(transitioned_slots)}, Standard: {len(new_slots)}), attempting to book...")
                        status_tracker.add_activity_log("availability", f"Found {len(all_new_slots)} new available slots")
                        
                        # Sort by park priority (lower number = higher priority)
                        all_new_slots.sort(key=lambda x: x.get('park_priority', 999))
                        
                        # Attempt to book the first available slot (highest priority)
                        for slot in all_new_slots:
                            try:
                                slot_id = slot.get('id')
                                if not slot_id:
                                    continue
                                    
                                logger.info(f"Attempting to book slot {slot_id}: {slot.get('bcd_name')} - {slot.get('icd_name')} on {slot.get('use_ymd')}")
                                
                                # Update status: attempting reservation
                                status_tracker.set_current_task(
                                    f"Attempting reservation: {slot.get('bcd_name')} - {slot.get('icd_name')}",
                                    {"slot_id": slot_id, "park": slot.get('bcd_name'), "court": slot.get('icd_name')}
                                )
                                await broadcast_status_update()
                                
                                result = await booking_service.book_available_slot(
                                    session,
                                    slot_id=slot_id,
                                    user_count=2,
                                    event_name="自動予約"
                                )
                                
                                logger.info(f"Successfully booked slot! Reservation number: {result['reservation_number']}")
                                
                                # Update reservation result
                                status_tracker.set_reservation_result(
                                    success=True,
                                    reservation_number=result['reservation_number'],
                                    details={"slot_id": slot_id}
                                )
                                status_tracker.set_current_task(None)  # Clear task
                                await broadcast_status_update()
                                
                                # Broadcast reservation event to frontend
                                reservation = result.get('reservation')
                                if reservation:
                                    reservation_data = {
                                        "id": reservation.id,
                                        "reservation_number": reservation.reservation_number,
                                        "bcd_name": reservation.bcd_name,
                                        "icd_name": reservation.icd_name,
                                        "start_time_display": reservation.start_time_display,
                                        "end_time_display": reservation.end_time_display,
                                        "use_ymd": reservation.use_ymd,
                                        "user_count": reservation.user_count or 2,
                                        "event_name": reservation.event_name,
                                        "status": reservation.status,
                                        "created_at": reservation.created_at.isoformat() if reservation.created_at else None
                                    }
                                    await broadcast_reservation_event(reservation_data)
                                
                                # Only book one slot at a time
                                break
                                
                            except Exception as e:
                                error_msg = f"Failed to book slot {slot.get('id')}: {str(e)}"
                                logger.error(error_msg)
                                status_tracker.add_error(error_msg, {"slot_id": slot.get('id')})
                                status_tracker.set_reservation_result(
                                    success=False,
                                    error=error_msg,
                                    details={"slot_id": slot.get('id')}
                                )
                                status_tracker.set_current_task(None)  # Clear task
                                await broadcast_status_update()
                                continue
                    else:
                        logger.info(f"Cycle #{cycle_count} completed - no new slots found. Starting next cycle...")
                        status_tracker.add_activity_log("system", f"Cycle #{cycle_count} completed - no new slots found")
                        status_tracker.set_current_task(
                            f"Cycle #{cycle_count} completed - Starting next cycle...",
                            {"cycle": cycle_count, "action": "cycle_completed"}
                        )
                        await broadcast_status_update()
                
                # Cycle completed - log and immediately start next cycle
                logger.info(f"=== Cycle #{cycle_count} completed. Starting next cycle ===")
                
                # Use intensive polling interval during Pattern 2 time (9:00-12:00)
                from datetime import datetime
                current_hour = datetime.now().hour
                if 9 <= current_hour < 12:
                    # Pattern 2: Use intensive polling (0.5 seconds)
                    await asyncio.sleep(settings.intensive_poll_interval)
                else:
                    # Normal polling interval
                    await asyncio.sleep(1)  # 1 second delay between cycles
                
            except Exception as e:
                error_msg = f"Error in background monitoring cycle #{cycle_count}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                status_tracker.add_error(error_msg)
                status_tracker.set_current_task(None)
                await broadcast_status_update()
                # Wait a bit longer on error before retrying
                logger.info(f"Waiting {settings.poll_interval * 2} seconds before retrying after error...")
                await asyncio.sleep(settings.poll_interval * 2)
    finally:
        # Cancel heartbeat task on shutdown
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global api_client, monitoring_service, booking_service, monitoring_task
    
    # Initialize status tracker
    status_tracker.set_backend_status(SystemStatus.RUNNING)
    status_tracker.add_activity_log("system", "Backend starting up...")
    
    # Initialize database
    await init_db()
    status_tracker.add_activity_log("system", "Database initialized")
    
    # Initialize API client (will be updated with cookies after login)
    api_client = ShinagawaAPIClient()
    
    # Initialize services
    status_tracker.set_current_task("Initializing browser automation...")
    booking_service = BookingService()
    await booking_service.initialize()
    status_tracker.add_activity_log("system", "Browser automation initialized")
    
    # Initialize monitoring service with browser automation reference
    monitoring_service = MonitoringService(api_client, browser_automation=booking_service.browser)
    
    # Get cookies from login and update API client
    status_tracker.set_current_task("Logging in...")
    try:
        cookies = await booking_service.browser.context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}
        api_client.update_cookies(cookie_dict)
        logger.info("Updated API client with authentication cookies")
        
        # Update status tracker
        status_tracker.set_login_status(LoginStatus.LOGGED_IN)
        status_tracker.add_activity_log("login", "Login successful - session active")
    except Exception as e:
        status_tracker.set_login_status(LoginStatus.NOT_LOGGED_IN)
        status_tracker.add_error(f"Login check failed: {str(e)}")
        logger.error(f"Error checking login status: {e}")
    
    status_tracker.set_current_task(None)  # Clear task
    
    # Start background monitoring task for automatic booking
    monitoring_task = asyncio.create_task(background_monitoring())
    status_tracker.add_activity_log("system", "Background monitoring started")
    
    logger.info("Application started")
    status_tracker.add_activity_log("system", "Application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global booking_service, monitoring_task
    
    status_tracker.set_backend_status(SystemStatus.STOPPED)
    status_tracker.add_activity_log("system", "Backend shutting down...")
    
    # Cancel background monitoring task
    if monitoring_task:
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass
    
    if booking_service:
        await booking_service.cleanup()
    
    status_tracker.add_activity_log("system", "Application stopped")
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
        status_tracker.set_current_task("Scanning availability...", {"action": "manual_scan"})
        await broadcast_status_update()
        
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
        
        # Update status
        status_tracker.set_availability_result(
            found=len(slots) > 0,
            slots_count=len(slots)
        )
        status_tracker.set_current_task(None)
        await broadcast_status_update()
        
        # Broadcast availability update to trigger frontend refresh
        if slots:
            await broadcast_availability_update()
        
            return {
                "success": True,
                "slots_found": len(slots),
                "slots": slot_dicts
            }
    except Exception as e:
        error_msg = f"Scan error: {str(e)}"
        logger.error(error_msg)
        status_tracker.add_error(error_msg)
        status_tracker.set_current_task(None)
        await broadcast_status_update()
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
        reservation_data = {
            "id": reservation.id,
            "reservation_number": reservation.reservation_number,
            "bcd_name": reservation.bcd_name,
            "icd_name": reservation.icd_name,
            "start_time_display": reservation.start_time_display,
            "end_time_display": reservation.end_time_display,
            "use_ymd": reservation.use_ymd,
            "user_count": reservation.user_count or 2,
            "event_name": reservation.event_name,
            "status": reservation.status,
            "created_at": reservation.created_at.isoformat() if reservation.created_at else None
        }
        
        # Broadcast reservation event to frontend
        await broadcast_reservation_event(reservation_data)
        
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
    """Get recent reservations, grouped by date."""
    try:
        reservations = await booking_service.get_reservations(session, limit=limit)
        
        # Group reservations by date (use_ymd)
        reservations_by_date = {}
        for r in reservations:
            date_key = str(r.use_ymd)
            if date_key not in reservations_by_date:
                reservations_by_date[date_key] = []
            
            reservations_by_date[date_key].append({
                "id": r.id,
                "reservation_number": r.reservation_number,
                "bcd_name": r.bcd_name,
                "icd_name": r.icd_name,
                "start_time_display": r.start_time_display,
                "end_time_display": r.end_time_display,
                "use_ymd": r.use_ymd,
                "user_count": r.user_count,
                "event_name": r.event_name,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None
            })
        
        # Sort dates numerically (earliest first) and return as list
        sorted_dates = sorted(reservations_by_date.keys(), key=lambda x: int(x))
        grouped_reservations = [
            {
                "date": int(date_key),
                "reservations": reservations_by_date[date_key]
            }
            for date_key in sorted_dates
        ]
        
        return {
            "success": True,
            "count": len(reservations),
            "grouped_by_date": grouped_reservations,
            # Keep backward compatibility - flat list
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
                    "event_name": r.event_name,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None
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


@app.get("/api/status")
async def get_status():
    """Get comprehensive system status."""
    try:
        # Ensure status_tracker is available
        if status_tracker is None:
            logger.warning("Status tracker is None, returning default status")
            # Return a default status structure
            return {
                "success": True,
                "status": {
                    "system": {
                        "backend_status": "Unknown",
                        "automation_status": "Unknown",
                        "last_activity_time": None
                    },
                    "login": {
                        "login_status": "Unknown",
                        "session_status": "Unknown",
                        "last_login_time": None,
                        "session_valid_until": None
                    },
                    "current_task": {
                        "task": None,
                        "started_at": None,
                        "details": {}
                    },
                    "activity_log": [],
                    "results": {
                        "last_check_time": None,
                        "last_availability_result": None,
                        "last_reservation_result": None
                    },
                    "errors": {
                        "recent_errors": [],
                        "recent_warnings": []
                    }
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        
        status_data = status_tracker.get_status()
        return {
            "success": True,
            "status": status_data,
            "timestamp": datetime.utcnow().isoformat()
        }
    except AttributeError as e:
        logger.error(f"Status tracker attribute error: {e}", exc_info=True)
        # Return error status instead of raising exception
        return {
            "success": False,
            "status": {
                "system": {"backend_status": "Error", "automation_status": "Error", "last_activity_time": None},
                "login": {"login_status": "Unknown", "session_status": "Unknown", "last_login_time": None, "session_valid_until": None},
                "current_task": {"task": None, "started_at": None, "details": {}},
                "activity_log": [],
                "results": {"last_check_time": None, "last_availability_result": None, "last_reservation_result": None},
                "errors": {"recent_errors": [{"message": f"Status tracker error: {str(e)}", "timestamp": datetime.utcnow().isoformat()}], "recent_warnings": []}
            },
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}", exc_info=True)
        # Return error status instead of raising exception
        return {
            "success": False,
            "status": {
                "system": {"backend_status": "Error", "automation_status": "Error", "last_activity_time": None},
                "login": {"login_status": "Unknown", "session_status": "Unknown", "last_login_time": None, "session_valid_until": None},
                "current_task": {"task": None, "started_at": None, "details": {}},
                "activity_log": [],
                "results": {"last_check_time": None, "last_availability_result": None, "last_reservation_result": None},
                "errors": {"recent_errors": [{"message": f"Error getting status: {str(e)}", "timestamp": datetime.utcnow().isoformat()}], "recent_warnings": []}
            },
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


async def broadcast_status_update():
    """Broadcast status update to all SSE clients."""
    try:
        if status_tracker is None:
            return  # Skip if status tracker not initialized
        
        status_data = status_tracker.get_status()
        event = {
            "type": "status_update",
            "data": status_data
        }
        message = f"data: {json.dumps(event)}\n\n"
        
        disconnected = []
        for queue in sse_connections:
            try:
                await queue.put(message)
            except Exception as e:
                logger.warning(f"Error sending status update: {e}")
                disconnected.append(queue)
        
        for queue in disconnected:
            try:
                sse_connections.remove(queue)
            except ValueError:
                pass
    except Exception as e:
        logger.error(f"Error broadcasting status update: {e}", exc_info=True)


@app.get("/api/events")
async def stream_events():
    """Server-Sent Events endpoint for real-time updates."""
    async def event_generator():
        # Create a queue for this client
        queue = asyncio.Queue()
        sse_connections.append(queue)
        
        try:
            # Send initial connection message with current status
            try:
                if status_tracker is not None:
                    initial_status = status_tracker.get_status()
                    yield f"data: {json.dumps({'type': 'connected', 'message': 'Connected to event stream', 'status': initial_status})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'connected', 'message': 'Connected to event stream', 'status': None})}\n\n"
            except Exception as e:
                logger.error(f"Error getting initial status: {e}")
                yield f"data: {json.dumps({'type': 'connected', 'message': 'Connected to event stream', 'status': None, 'error': str(e)})}\n\n"
            
            # Keep connection alive and send events
            while True:
                try:
                    # Wait for message with timeout to send keepalive
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield message
                except asyncio.TimeoutError:
                    # Send keepalive ping with current status
                    try:
                        if status_tracker is not None:
                            current_status = status_tracker.get_status()
                            yield f"data: {json.dumps({'type': 'keepalive', 'status': current_status})}\n\n"
                        else:
                            yield f"data: {json.dumps({'type': 'keepalive', 'status': None})}\n\n"
                    except Exception as e:
                        logger.error(f"Error getting status for keepalive: {e}")
                        yield f"data: {json.dumps({'type': 'keepalive', 'status': None})}\n\n"
                except Exception as e:
                    logger.error(f"Error in event stream: {e}")
                    break
        finally:
            # Remove queue when client disconnects
            try:
                sse_connections.remove(queue)
            except ValueError:
                pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

