"""Booking service for handling reservations."""
import sys
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime

# Fix for Windows asyncio subprocess issues
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.browser_automation import BrowserAutomation
from app.database import AsyncSessionLocal, Reservation, AvailabilitySlot, MonitoringLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class BookingService:
    """Service for handling booking operations."""
    
    def __init__(self):
        self.browser = BrowserAutomation()
    
    async def initialize(self):
        """Initialize browser."""
        await self.browser.start()
        # Login and get cookies
        cookies = await self.browser.login()
        logger.info("Booking service initialized")
    
    async def book_available_slot(
        self,
        session: AsyncSession,
        slot_id: int,
        user_count: int = 2,
        event_name: Optional[str] = None
    ) -> Dict:
        """Book an available slot.
        
        Args:
            session: Database session
            slot_id: ID of availability slot to book
            user_count: Number of users
            event_name: Optional event name
            
        Returns:
            Reservation details
        """
        try:
            # Get slot from database
            stmt = select(AvailabilitySlot).where(AvailabilitySlot.id == slot_id)
            result = await session.execute(stmt)
            slot = result.scalar_one_or_none()
            
            if not slot:
                raise ValueError(f"Slot {slot_id} not found")
            
            if slot.status != 'available':
                raise ValueError(f"Slot {slot_id} is not available")
            
            # Prepare slot data for booking
            slot_data = {
                'use_ymd': slot.use_ymd,
                'bcd': slot.bcd,
                'icd': slot.icd,
                'start_time': slot.start_time,
                'end_time': slot.end_time,
                'area_code': self._get_area_code(slot.bcd),
            }
            
            # Attempt booking via browser
            booking_result = await self.browser.book_slot(slot_data)
            
            if booking_result['success']:
                # Check if a reservation with status='selected' already exists for this slot
                stmt = select(Reservation).where(
                    Reservation.use_ymd == slot.use_ymd,
                    Reservation.bcd == slot.bcd,
                    Reservation.icd == slot.icd,
                    Reservation.start_time == slot.start_time,
                    Reservation.end_time == slot.end_time,
                    Reservation.status == 'selected'
                )
                result = await session.execute(stmt)
                existing_reservation = result.scalar_one_or_none()
                
                if existing_reservation:
                    # Update existing reservation with booking details
                    existing_reservation.reservation_number = booking_result['reservation_number']
                    existing_reservation.user_count = user_count
                    existing_reservation.event_name = event_name
                    existing_reservation.status = 'confirmed'
                    existing_reservation.booking_data = booking_result
                    existing_reservation.updated_at = datetime.utcnow()
                    reservation = existing_reservation
                    logger.info(f"Updated existing selected reservation to confirmed: {booking_result['reservation_number']}")
                else:
                    # Create new reservation record
                    reservation = Reservation(
                        reservation_number=booking_result['reservation_number'],
                        use_ymd=slot.use_ymd,
                        bcd=slot.bcd,
                        icd=slot.icd,
                        bcd_name=slot.bcd_name,
                        icd_name=slot.icd_name,
                        start_time=slot.start_time,
                        end_time=slot.end_time,
                        start_time_display=slot.start_time_display,
                        end_time_display=slot.end_time_display,
                        user_count=user_count,
                        event_name=event_name,
                        status='confirmed',
                        booking_data=booking_result
                    )
                    session.add(reservation)
                    logger.info(f"Created new reservation record: {booking_result['reservation_number']}")
                
                # Update slot status
                slot.status = 'booked'
                slot.updated_at = datetime.utcnow()
                
                # Log booking
                log = MonitoringLog(
                    log_type='booking',
                    message=f'Successfully booked slot {slot_id}',
                    data={'slot_id': slot_id, 'reservation_number': booking_result['reservation_number']},
                    success=True
                )
                session.add(log)
                
                await session.commit()
                
                return {
                    'success': True,
                    'reservation_number': booking_result['reservation_number'],
                    'reservation': reservation
                }
            else:
                raise Exception("Booking failed")
                
        except Exception as e:
            logger.error(f"Booking error: {e}")
            
            # Log error
            log = MonitoringLog(
                log_type='booking',
                message=f'Booking failed for slot {slot_id}: {str(e)}',
                data={'slot_id': slot_id, 'error': str(e)},
                success=False
            )
            session.add(log)
            await session.commit()
            
            raise
    
    def _get_area_code(self, bcd: str) -> str:
        """Get area code from building code."""
        area_map = {
            '1040': '1200_1040',  # しながわ区民公園
            '1030': '1500_1030',  # 八潮北公園
            '1010': '1400_1010',  # しながわ中央公園
            '1020': '1400_1020',  # 東品川公園
        }
        return area_map.get(bcd, '1400_0')
    
    async def get_reservations(
        self,
        session: AsyncSession,
        limit: int = 100
    ) -> list[Reservation]:
        """Get recent reservations."""
        stmt = select(Reservation).order_by(Reservation.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    async def cleanup(self):
        """Cleanup browser resources."""
        await self.browser.stop()

