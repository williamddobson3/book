"""Database setup and models."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, Text
from datetime import datetime
from app.config import settings

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
    """Completed reservation."""
    __tablename__ = "reservations"
    
    id = Column(Integer, primary_key=True, index=True)
    reservation_number = Column(String, unique=True, index=True)
    use_ymd = Column(Integer, index=True)
    bcd = Column(String)
    icd = Column(String)
    bcd_name = Column(String)
    icd_name = Column(String)
    start_time = Column(Integer)
    end_time = Column(Integer)
    start_time_display = Column(String)
    end_time_display = Column(String)
    user_count = Column(Integer)
    event_name = Column(String, nullable=True)
    usage_fee = Column(Integer, nullable=True)
    cancel_deadline = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, confirmed, cancelled
    booking_data = Column(JSON, nullable=True)  # Store full booking data
    created_at = Column(DateTime, default=datetime.utcnow)
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
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

