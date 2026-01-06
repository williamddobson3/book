"""Database setup and models."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, Text, text
from datetime import datetime
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    settings.database_url.replace("sqlite://", "sqlite+aiosqlite://"),
    echo=False,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


class AvailabilitySlot(Base):
    """Available time slot for booking."""
    __tablename__ = "availability_slots"
    
    id = Column(Integer, primary_key=True, index=True)
    use_ymd = Column(Integer, index=True)  # YYYYMMDD format
    bcd = Column(String, index=True)  # Building code
    icd = Column(String, index=True)  # Facility code
    bcd_name = Column(String)  # Building name
    icd_name = Column(String)  # Facility name
    start_time = Column(Integer)  # HHMM format
    end_time = Column(Integer)  # HHMM format
    start_time_display = Column(String)  # e.g., "08時30分"
    end_time_display = Column(String)  # e.g., "10時30分"
    pps_cd = Column(Integer)  # Purpose code
    pps_cls_cd = Column(Integer)  # Purpose class code
    week_flg = Column(Integer)  # Week flag
    holiday_flg = Column(Integer)  # Holiday flag
    field_cnt = Column(Integer)  # Field count
    status = Column(String, default="available")  # available, reserved, booked
    detected_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Reservation(Base):
    """Reservation record - can be a selected date or completed reservation."""
    __tablename__ = "reservations"
    
    id = Column(Integer, primary_key=True, index=True)
    reservation_number = Column(String, unique=True, nullable=True, index=True)  # NULL for selected dates, set when booked
    use_ymd = Column(Integer, index=True)  # Date in YYYYMMDD format
    bcd = Column(String, index=True)  # Building code
    icd = Column(String, index=True)  # Facility code
    bcd_name = Column(String)  # Building name
    icd_name = Column(String)  # Facility name
    start_time = Column(Integer)  # Start time in HHMM format
    end_time = Column(Integer)  # End time in HHMM format
    start_time_display = Column(String)  # Display format (e.g., "08時30分")
    end_time_display = Column(String)  # Display format (e.g., "10時30分")
    user_count = Column(Integer, nullable=True)  # May be NULL for selected dates
    event_name = Column(String, nullable=True)  # Event name (optional)
    usage_fee = Column(Integer, nullable=True)  # Usage fee (set after booking)
    cancel_deadline = Column(String, nullable=True)  # Cancellation deadline (set after booking)
    status = Column(String, default="selected", index=True)  # selected, pending, confirmed, cancelled
    booking_data = Column(JSON, nullable=True)  # Store full booking data
    cell_id = Column(String, nullable=True, index=True)  # Calendar cell ID (e.g., "20260104_10") - set when date is selected from table
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MonitoringLog(Base):
    """Log of monitoring activities."""
    __tablename__ = "monitoring_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    log_type = Column(String, index=True)  # scan, booking, error
    message = Column(Text)
    data = Column(JSON, nullable=True)
    success = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


async def init_db():
    """Initialize database tables and run migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Run migrations
        await _migrate_reservations_table(conn)


async def _migrate_reservations_table(conn):
    """Add missing columns to reservations table if needed."""
    def _check_and_add_column(sync_conn):
        """Synchronous function to check and add column."""
        try:
            # Check if reservations table exists
            result = sync_conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='reservations'"
            ))
            if result.scalar() is None:
                # Table doesn't exist yet, create_all will create it
                return
            
            # Check if cell_id column exists using PRAGMA
            result = sync_conn.execute(text("PRAGMA table_info(reservations)"))
            columns = [row[1] for row in result.fetchall()]  # Column name is at index 1
            
            if 'cell_id' not in columns:
                # Add cell_id column
                sync_conn.execute(text("ALTER TABLE reservations ADD COLUMN cell_id VARCHAR"))
                logger.info("Added cell_id column to reservations table")
                
                # Create index
                sync_conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reservations_cell_id ON reservations(cell_id)"))
                logger.info("Created index on cell_id column")
        except Exception as e:
            # Column might already exist, or other error - log and continue
            logger.debug(f"Migration check: {e}")
    
    # Run migration synchronously within the async context
    await conn.run_sync(lambda sync_conn: _check_and_add_column(sync_conn))


async def get_db():
    """Get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

